# ============================================================================
# Multi-stage Dockerfile for React Application
# ============================================================================

FROM node:18.20.8-alpine AS base

WORKDIR /app

RUN apk add --no-cache python3 make g++ git && \
    npm install -g npm@10.8.2 && \
    npm config set fund false && \
    npm config set audit false

COPY package*.json ./

# -----------------------------------------------------------------------------
# Builder Stage
# -----------------------------------------------------------------------------
FROM base AS builder

# Install dependencies (resolutions/overrides handle version locking)
RUN npm install --legacy-peer-deps --no-progress

# Verify critical packages
RUN node -e "const pkgs=['schema-utils','ajv','fork-ts-checker-webpack-plugin','terser-webpack-plugin'];pkgs.forEach(p=>{const v=require(p+'/package.json').version;console.log('✅',p+':',v);})"

COPY . .

# Create production environment
ARG REACT_APP_API_URL
ARG REACT_APP_STAGE=prod
ARG REACT_APP_VERSION
ARG REACT_APP_BUILD_TIME

RUN echo "REACT_APP_API_URL=${REACT_APP_API_URL}" > .env.production && \
    echo "REACT_APP_STAGE=${REACT_APP_STAGE}" >> .env.production && \
    echo "REACT_APP_VERSION=${REACT_APP_VERSION}" >> .env.production && \
    echo "REACT_APP_BUILD_TIME=${REACT_APP_BUILD_TIME}" >> .env.production

# Build
ENV CI=true
ENV GENERATE_SOURCEMAP=false
ENV NODE_OPTIONS="--max-old-space-size=4096"
ENV SKIP_PREFLIGHT_CHECK=true

RUN npm run build && \
    test -f build/index.html && \
    echo "✅ Build successful"

# -----------------------------------------------------------------------------
# Production Stage
# -----------------------------------------------------------------------------
FROM nginx:1.27-alpine AS production

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/build /usr/share/nginx/html

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:80/ || exit 1

RUN addgroup -g 101 -S nginx-app && \
    adduser -S -D -H -u 101 -h /var/cache/nginx -s /sbin/nologin -G nginx-app nginx-app && \
    chown -R nginx-app:nginx-app /usr/share/nginx/html /var/cache/nginx /var/log/nginx && \
    touch /var/run/nginx.pid && \
    chown nginx-app:nginx-app /var/run/nginx.pid

EXPOSE 80
USER nginx-app
CMD ["nginx", "-g", "daemon off;"]