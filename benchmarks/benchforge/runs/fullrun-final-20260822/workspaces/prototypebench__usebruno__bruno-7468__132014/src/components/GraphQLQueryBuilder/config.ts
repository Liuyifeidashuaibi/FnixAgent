export const GRAPHQL_BUILDER_CONFIG = {
  // Default builder width in pixels
  defaultWidth: 400,
  
  // Default variables pane height in pixels
  defaultHeight: 200,
  
  // Minimum and maximum dimensions
  minWidth: 300,
  maxWidth: 800,
  minHeight: 150,
  maxHeight: 400,
  
  // Schema loading defaults
  defaultEndpoint: 'http://localhost:4000/graphql',
  
  // Timeout for schema loading (ms)
  schemaLoadTimeout: 10000,
  
  // Auto-save settings
  autoSaveDelay: 500,
  
  // Feature flags
  features: {
    introspection: true,
    fileUpload: true,
    prettify: true,
    dragResize: true,
    variableValidation: true
  }
};

export type GraphQLBuilderConfig = typeof GRAPHQL_BUILDER_CONFIG;