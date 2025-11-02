# ==============================================================================
# STAGE 1: Builder - Creates consistent build environment  
# ==============================================================================
FROM node:18.20.8-alpine AS builder

WORKDIR /app

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    make \
    g++ \
    git \
    && npm install -g npm@10.8.2

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install --no-fund --no-audit --no-progress --legacy-peer-deps

# Copy application source code
COPY . .

# Build arguments (set by CI/CD pipeline)
ARG API_ENDPOINT=https://bhgplw8pyk.execute-api.us-east-1.amazonaws.com/prod
ARG BUILD_VERSION=local-build
ARG BUILD_TIME=build-time

# Create production environment file
RUN echo "REACT_APP_API_URL=$API_ENDPOINT" > .env.production && \
    echo "REACT_APP_STAGE=prod" >> .env.production && \
    echo "REACT_APP_VERSION=$BUILD_VERSION" >> .env.production && \
    echo "REACT_APP_BUILD_TIME=$BUILD_TIME" >> .env.production && \
    echo "✅ Generated .env.production:" && \
    cat .env.production

# Build the application
RUN CI=true \
    GENERATE_SOURCEMAP=false \
    npm run build

# Verify build output
RUN if [ ! -f build/index.html ]; then \
        echo "❌ CRITICAL FAILURE: build/index.html not found"; \
        exit 1; \
    fi && \
    if [ -z "$(find build/static/js -name '*.js' -print -quit 2>/dev/null)" ]; then \
        echo "❌ CRITICAL FAILURE: No JavaScript bundles found"; \
        exit 1; \
    fi && \
    echo "✅ Build validation successful:" && \
    du -sh build/

# ==============================================================================
# STAGE 2: Artifact - Minimal output for deployment
# ==============================================================================
FROM scratch AS artifact
COPY --from=builder /app/build /build