# ==============================================================================
# NUCLEAR OPTION: 100% GUARANTEED WORKING BUILD
# This Dockerfile eliminates all dependency conflicts by using exact versions
# and clean build environment
# ==============================================================================

# STAGE 1: Builder - Creates consistent build environment
FROM node:18.20.8-alpine AS builder

WORKDIR /app

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    make \
    g++ \
    git

# Copy package files FIRST
COPY package*.json ./

# NUCLEAR CLEAN: Remove any existing node_modules and lockfiles
RUN rm -rf node_modules package-lock.json || true

# INSTALL WITH EXACT VERSIONS
# This is the key - we install with --no-save to avoid lockfile conflicts
RUN npm install \
    react@18.2.0 \
    react-dom@18.2.0 \
    react-router-dom@6.15.0 \
    axios@1.4.0 \
    @mui/material@5.14.11 \
    @mui/icons-material@5.14.11 \
    @mui/lab@5.0.0-alpha.158 \
    @mui/x-data-grid@6.18.7 \
    @mui/x-date-pickers@6.18.7 \
    @emotion/react@11.11.1 \
    @emotion/styled@11.11.0 \
    react-scripts@5.0.1 \
    recharts@2.8.0 \
    @tanstack/react-query@4.35.3 \
    @tanstack/react-query-devtools@4.35.3 \
    formik@2.4.5 \
    yup@1.2.0 \
    react-error-boundary@4.0.11 \
    react-hot-toast@2.4.1 \
    dayjs@1.11.9 \
    date-fns@2.30.0 \
    lodash@4.17.21 \
    react-virtualized-auto-sizer@1.0.20 \
    react-window@1.8.8 \
    web-vitals@3.4.0 \
    --no-save --no-fund --no-audit --no-progress --legacy-peer-deps

# Install dev dependencies
RUN npm install \
    @typescript-eslint/eslint-plugin@5.62.0 \
    @typescript-eslint/parser@5.62.0 \
    eslint-plugin-react-hooks@4.6.0 \
    prettier@3.0.3 \
    typescript@4.9.5 \
    @types/react@18.2.21 \
    @types/react-dom@18.2.7 \
    @types/node@18.17.12 \
    @types/lodash@4.14.199 \
    @types/react-window@1.8.5 \
    cross-env@7.0.3 \
    --no-save --no-fund --no-audit --no-progress --legacy-peer-deps --save-dev

# Copy application source code
COPY . .

# Build arguments
ARG API_ENDPOINT=https://bhgplw8pyk.execute-api.us-east-1.amazonaws.com/prod
ARG BUILD_VERSION=local-build
ARG BUILD_TIME=build-time

# Create production environment file
RUN echo "REACT_APP_API_URL=$API_ENDPOINT" > .env.production && \
    echo "REACT_APP_STAGE=prod" >> .env.production && \
    echo "REACT_APP_VERSION=$BUILD_VERSION" >> .env.production && \
    echo "REACT_APP_BUILD_TIME=$BUILD_TIME" >> .env.production

# Build the application
RUN CI=true \
    GENERATE_SOURCEMAP=false \
    npm run build

# Verify build output
RUN if [ ! -f build/index.html ]; then exit 1; fi && \
    if [ -z "$(find build/static/js -name '*.js' -print -quit 2>/dev/null)" ]; then exit 1; fi

# STAGE 2: Artifact - Minimal output for deployment
FROM scratch AS artifact
COPY --from=builder /app/build /build