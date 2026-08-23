import React from 'react';
import { GraphQLSchema, GraphQLQueryBuilderProps } from './types';

export * from './types';

export declare const GraphQLQueryBuilder: React.FC<GraphQLQueryBuilderProps>;

export declare const SchemaLoader: React.FC<{ 
  onSchemaLoad?: (schema: GraphQLSchema) => void;
  onError?: (error: string) => void;
}>;

export declare const QueryBuilderPane: React.FC<{
  schema?: GraphQLSchema;
  query?: string;
  onQueryChange?: (query: string) => void;
}>;

export declare const VariablesPane: React.FC<{
  variables?: Record<string, any>;
  onVariablesChange?: (variables: Record<string, any>) => void;
}>;