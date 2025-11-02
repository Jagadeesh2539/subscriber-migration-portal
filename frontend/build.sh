#!/usr/bin/env bash
set -euo pipefail  # Exit on error, undefined vars, pipe failures

echo "🏗️ ============================================"
echo "🏗️  BUILDING REACT APPLICATION WITH CRACO"
echo "🏗️ ============================================"
echo ""

# Configurable vars (from your env)
API_ENDPOINT="${REACT_APP_API_URL:-https://bhgplw8pyk.execute-api.us-east-1.amazonaws.com/prod}"
STAGE="${REACT_APP_STAGE:-prod}"

echo "✅ API Endpoint: $API_ENDPOINT"
echo "✅ Stage: $STAGE"

# Create .env.production (dynamic version/build time)
cat > .env.production << EOF
REACT_APP_API_URL=$API_ENDPOINT
REACT_APP_STAGE=$STAGE
REACT_APP_VERSION=$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d-%H%M%S)
REACT_APP_BUILD_TIME=$(date -u '+%Y-%m-%d %H:%M:%S UTC')
EOF

echo "📝 Environment:"
cat .env.production
echo ""

# Robust pre-build cleanup
echo "🧹 Cleaning caches and locks..."
rm -rf node_modules package-lock.json .craco yarn.lock  # Cover npm/yarn
npm cache clean --force || true
rm -f build.log  # Clear old log

# Update npm globally (fixes version warning)
echo "🔄 Updating npm to latest..."
npm install -g npm@latest --silent || echo "⚠️ npm update skipped (permissions?)"

# Install dependencies strictly (CI-friendly)
echo "📦 Installing dependencies..."
npm ci --no-audit --prefer-offline --no-fund || {
  echo "❌ npm ci failed. Falling back to npm install..."
  npm install --no-audit --prefer-offline
}

# Optimize node_modules
npm dedupe --silent || true

# Verify key versions (debug)
echo "🔍 Verifying dependency versions:"
npm ls schema-utils ajv terser-webpack-plugin --depth=0 || true
echo ""

# Build with timing and logging
echo "🔨 Building with CRACO..."
BUILD_START=$(date +%s)
export CI=true  # Force CRA prod mode
export SKIP_PREFLIGHT_CHECK=true
export NODE_OPTIONS="--max_old_space_size=4096"  # Memory for large apps

if npm run build 2>&1 | tee build.log; then
  BUILD_END=$(date +%s)
  BUILD_DURATION=$((BUILD_END - BUILD_START))
  
  echo ""
  echo "✅ ============================================"
  echo "✅  BUILD COMPLETED IN ${BUILD_DURATION}s"
  echo "✅ ============================================"
else
  echo ""
  echo "❌ Build failed:"
  echo "--------------------------------------------"
  tail -n 50 build.log  # Last 50 lines for brevity
  echo "--------------------------------------------"
  
  echo ""
  echo "🔍 Full dependency tree for debugging:"
  npm ls schema-utils --all || true
  npm ls ajv --all || true
  
  echo ""
  echo "🔍 Installed webpack plugin versions:"
  npm ls schema-utils fork-ts-checker-webpack-plugin terser-webpack-plugin --depth=0 || true
  
  exit 1
fi

# Validate output
if [[ ! -f build/index.html ]]; then
  echo "❌ Build output missing: build/index.html not found"
  exit 1
fi

echo ""
echo "📊 Build Statistics:"
echo "  Total size: $(du -sh build | cut -f1)"
echo "  File count: $(find build -type f | wc -l)"

if [[ -d build/static ]]; then
  echo "  Static size: $(du -sh build/static | cut -f1)"
  echo "  JS files: $(find build/static -name "*.js" -not -name "*.map" | wc -l)"
  echo "  CSS files: $(find build/static -name "*.css" -not -name "*.map" | wc -l)"
fi

echo ""
echo "✅ Build validation complete"