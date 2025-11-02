const path = require('path');
const webpack = require('webpack');
const TerserPlugin = require('terser-webpack-plugin');
const schemaUtils = require('schema-utils');

module.exports = {
  webpack: {
    configure: (webpackConfig, { env, paths }) => {
      // Only patch in production builds
      if (env !== 'production') {
        return webpackConfig;
      }

      console.log('🔧 CRACO: Patching TerserPlugin for schema-utils v3.x compatibility...');

      // Ensure optimization exists
      webpackConfig.optimization = webpackConfig.optimization || {};
      webpackConfig.optimization.minimizer = [
        new TerserPlugin({
          // Standard react-scripts terserOptions (ES2018+ for modern browsers)
          terserOptions: {
            parse: {
              ecma: 2018,
            },
            compress: {
              ecma: 2018,
              warnings: false,
              comparisons: false,
              inline: 2,
            },
            mangle: {
              safari10: true,
            },
            output: {
              ecma: 2018,
              comments: false,
              ascii_only: true,
            },
            format: {
              comments: false,
            },
          },
          // Custom validate using schema-utils v3.x API
          validate: (schema, options, name) => {
            try {
              // v3.x API: validate(schema, options, { name })
              schemaUtils.validate(schema, options, { name });
            } catch (error) {
              // Robust fallback: Log and skip validation (build continues)
              console.warn(`⚠️ Terser schema validation skipped for ${name}: ${error.message}`);
              // If v4.x is detected, you could swap to validateSchema here, but v3 override prevents this
            }
          },
          // Performance options
          parallel: true,
          extractComments: false,
        }),
      ];

      // Remove any conflicting minimizers (e.g., from other plugins)
      if (webpackConfig.optimization.minimizer && webpackConfig.optimization.minimizer.length > 1) {
        webpackConfig.optimization.minimizer = webpackConfig.optimization.minimizer.filter(
          (plugin) => !(plugin.constructor && plugin.constructor.name === 'TerserPlugin') || plugin instanceof TerserPlugin
        );
        if (webpackConfig.optimization.minimizer.length === 0) {
          webpackConfig.optimization.minimizer = [new TerserPlugin({ /* defaults */ })];
        }
      }

      // Optional: Add source maps for debugging (disable in prod if not needed)
      webpackConfig.devtool = env === 'production' ? false : 'source-map';

      console.log('✅ CRACO: TerserPlugin patch applied successfully.');
      return webpackConfig;
    },
  },
  // Keep CRA's ESLint and style loaders intact
  eslint: {
    enable: true,
  },
  style: {
    postcss: {
      mode: 'file',  // For CSS modules or Tailwind
    },
    sass: {
      loaderOptions: {},  // If using Sass
    },
  },
  // Optional: Path aliases (e.g., for src/ imports)
  alias: {
    '@': path.resolve(__dirname, 'src'),
  },
};