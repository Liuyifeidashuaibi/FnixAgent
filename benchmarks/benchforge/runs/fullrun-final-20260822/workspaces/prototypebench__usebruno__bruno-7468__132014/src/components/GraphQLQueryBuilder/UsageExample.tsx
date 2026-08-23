import React, { useState } from 'react';
import { GraphQLQueryBuilder } from './index';

const UsageExample: React.FC = () => {
  const [query, setQuery] = useState<string>(`query {
  users(first: 10) {
    id
    name
    email
  }
}`);
  
  const [variables, setVariables] = useState<Record<string, any>>({
    first: 10
  });

  return (
    <div className="usage-example">
      <h2>GraphQL Query Builder Example</h2>
      <div className="builder-container">
        <GraphQLQueryBuilder
          query={query}
          variables={variables}
          onQueryChange={setQuery}
          onVariablesChange={setVariables}
        />
      </div>
      
      <div className="current-query">
        <h3>Generated Query:</h3>
        <pre>{query}</pre>
      </div>
      
      <div className="current-variables">
        <h3>Current Variables:</h3>
        <pre>{JSON.stringify(variables, null, 2)}</pre>
      </div>
    </div>
  );
};

export default UsageExample;