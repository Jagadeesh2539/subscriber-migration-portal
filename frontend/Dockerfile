# ==============================================================================
# STAGE 1: Builder - Creates consistent build environment with Yarn
# ==============================================================================
FROM node:18.20.8-alpine AS builder

WORKDIR /app

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    make \
    g++ \
    git \
    corepack

# Enable corepack for Yarn
RUN corepack enable

# Copy package files and Yarn configuration
COPY package.json yarn.lock .yarnrc.yml ./
COPY .yarn/ .yarn/

# Install dependencies with Yarn (deterministic)
RUN yarn install --immutable --immutable-cache --check-cache

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
    echo "REACT_APP_BUILD_TIME=$BUILD_TIME" >> .env.production

# Build the application
RUN CI=true \
    GENERATE_SOURCEMAP=false \
    yarn build

# Verify build output
RUN if [ ! -f build/index.html ]; then exit 1; fi && \
    if [ -z "$(find build/static/js -name '*.js' -print -quit 2>/dev/null)" ]; then exit 1; fi

# ==============================================================================
# STAGE 2: Artifact - Minimal output for deployment
# ==============================================================================
FROM scratch AS artifact
COPY --from=builder /app/build /build