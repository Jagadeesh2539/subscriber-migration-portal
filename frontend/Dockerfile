# ==============================================================================
# STAGE 1: Builder - Creates consistent build environment with global Yarn
# ==============================================================================
FROM node:18.20.8-alpine AS builder

WORKDIR /app

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    make \
    g++ \
    git

# Install Yarn globally (bypasses Corepack issues)
RUN npm install -g yarn@3.6.4

# Copy ALL source code first
COPY . .

# Install dependencies including TypeScript
RUN yarn install --no-immutable --no-immutable-cache

# Force resolve critical ajv versions
RUN yarn add ajv@6.12.6 ajv-keywords@3.5.2 --exact

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
    yarn build

# Verify build output
RUN if [ ! -f build/index.html ]; then exit 1; fi && \
    if [ -z "$(find build/static/js -name '*.js' -print -quit 2>/dev/null)" ]; then exit 1; fi

# ==============================================================================
# STAGE 2: Artifact - Minimal output for deployment
# ==============================================================================
FROM scratch AS artifact
COPY --from=builder /app/build /build