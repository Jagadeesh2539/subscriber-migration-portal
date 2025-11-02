FROM node:18.20.8-alpine AS base

WORKDIR /app

# Install system dependencies for native modules
RUN apk add --no-cache \
    python3 \
    make \
    g++ \
    git \
    && npm install -g npm@10.8.2 \
    && npm config set fund false \
    && npm config set audit false

# Copy package files for dependency installation
COPY package*.json ./

# ==============================================================================
# STAGE 1: Builder - Creates consistent build environment  
# ==============================================================================
FROM base AS builder

# Install dependencies with legacy peer deps support
RUN npm install --legacy-peer-deps --no-progress --ignore-scripts

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

# Build the application with OpenSSL legacy provider
RUN CI=true \
    GENERATE_SOURCEMAP=false \
    NODE_OPTIONS="--max-old-space-size=4096 --openssl-legacy-provider" \
    npm run build

# Verify build output integrity
RUN if [ ! -f build/index.html ]; then \
        echo "❌ CRITICAL FAILURE: build/index.html not found"; \
        echo "🔍 Directory structure:"; \
        find build -type f | head -20; \
        exit 1; \
    fi && \
    if [ -z "$(find build/static/js -name 'main.*.js' -print -quit 2>/dev/null)" ]; then \
        echo "❌ CRITICAL FAILURE: Main JavaScript bundle not found"; \
        echo "🔍 Contents of build/static/js/:"; \
        ls -la build/static/js/ 2>/dev/null || echo "Directory not found"; \
        exit 1; \
    fi && \
    echo "✅ Build validation successful:" && \
    echo "📦 Build statistics:" && \
    du -sh build/ && \
    echo "   File count: $(find build -type f | wc -l)"

# ==============================================================================
# STAGE 2: Artifact - Minimal output for deployment
# ==============================================================================
FROM scratch AS artifact
COPY --from=builder /app/build /build
