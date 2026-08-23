export interface GraphQLSchema {
  types: GraphQLType[];
}

export interface GraphQLType {
  name: string;
  fields?: GraphQLField[];
  args?: GraphQLArgument[];
}

export interface GraphQLField {
  name: string;
  type: string;
  args?: GraphQLArgument[];
  fields?: GraphQLField[];
}

export interface GraphQLArgument {
  name: string;
  type: string;
  defaultValue?: string;
}

export interface GraphQLQueryBuilderProps {
  schema?: GraphQLSchema;
  query?: string;
  variables?: Record<string, any>;
  onQueryChange?: (query: string) => void;
  onVariablesChange?: (variables: Record<string, any>) => void;
  onSchemaLoad?: (schema: GraphQLSchema) => void;
}

export interface QueryNode {
  type: string;
  name: string;
  fields: QueryNode[];
  args?: { name: string; value: string }[];
  isSelected?: boolean;
}