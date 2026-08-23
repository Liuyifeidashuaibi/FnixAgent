import React, { useState, useEffect } from 'react';
import { GraphQLQueryBuilder } from '../components/GraphQLQueryBuilder';

interface BrunoRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string;
  variables: Record<string, any>;
}

const GraphQLQueryBuilderIntegration: React.FC = () => {
  const [request, setRequest] = useState<Partial<BrunoRequest>>({
    url: 'http://localhost:4000/graphql',
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: `query {
  users(first: 10) {
    id
    name
    email
  }
}`,
    variables: {
      first: 10
    }
  });

  const handleQueryChange = (query: string) => {
    setRequest(prev => ({
      ...prev,
      body: query
    }));
  };

  const handleVariablesChange = (variables: Record<string, any>) => {
    setRequest(prev => ({
      ...prev,
      variables
    }));
  };

  // Simulate loading schema when URL changes
  useEffect(() => {
    if (request.url) {
      // In real app, this would trigger schema loading
      console.log('Schema loading triggered for:', request.url);
    }
  }, [request.url]);

  return (
    <div className="bruno-integration">
      <h2>GraphQL Query Builder Integration</h2>
      
      <div className="request-config">
        <div className="url-input">
          <label htmlFor="graphql-url">GraphQL Endpoint:</label>
          <input
            id="graphql-url"
            type="url"
            value={request.url || ''}
            onChange={(e) => setRequest(prev => ({ ...prev, url: e.target.value }))}
            placeholder="https://api.example.com/graphql"
          />
        </div>
      </div>
      
      <div className="query-builder-section">
        <GraphQLQueryBuilder
          query={request.body || ''}
          variables={request.variables || {}}
          onQueryChange={handleQueryChange}
          onVariablesChange={handleVariablesChange}
        />
      </div>
      
      <div className="request-actions">
        <button onClick={() => console.log('Sending request:', request)}>
          Send Request
        </button>
        <button onClick={() => console.log('Current state:', request)}>
          Debug State
        </button>
      </div>
    </div>
  );
};

export default GraphQLQueryBuilderIntegration;