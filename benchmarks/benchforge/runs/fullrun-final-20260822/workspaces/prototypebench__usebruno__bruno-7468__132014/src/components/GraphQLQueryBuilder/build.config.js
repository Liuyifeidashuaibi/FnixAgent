module.exports = {
  // Build configuration for GraphQL Query Builder
  
  // Entry points
  entry: {
    'index': './index.tsx',
    'schema-loader': './SchemaLoader.tsx',
    'query-builder-pane': './QueryBuilderPane.tsx',
    'variables-pane': './VariablesPane.tsx'
  },
  
  // Output configuration
  output: {
    path: './dist',
    filename: '[name].js',
    library: '@bruno/graphql-query-builder',
    libraryTarget: 'umd'
  },
  
  // Module resolution
  resolve: {
    extensions: ['.ts', '.tsx', '.js', '.jsx']
  },
  
  // Module rules
  module: {
    rules: [
      {
        test: /\.(ts|tsx)$/,
        exclude: /node_modules/,
        use: {
          loader: 'ts-loader'
        }
      },
      {
        test: /\.(css|scss)$/,
        use: ['style-loader', 'css-loader']
      }
    ]
  },
  
  // External dependencies
  externals: {
    'react': {
      root: 'React',
      commonjs2: 'react',
      commonjs: 'react',
      amd: 'react'
    },
    'react-dom': {
      root: 'ReactDOM',
      commonjs2: 'react-dom',
      commonjs: 'react-dom',
      amd: 'react-dom'
    }
  }
};