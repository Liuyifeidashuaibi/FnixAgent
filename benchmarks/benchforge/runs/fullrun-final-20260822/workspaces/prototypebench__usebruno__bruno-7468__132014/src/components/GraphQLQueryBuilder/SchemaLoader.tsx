import React, { useState, useCallback } from 'react';

interface SchemaLoaderProps {
  onSchemaLoad?: (schema: any) => void;
  onError?: (error: string) => void;
}

const SchemaLoader: React.FC<SchemaLoaderProps> = ({
  onSchemaLoad,
  onError
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [schemaSource, setSchemaSource] = useState<'introspection' | 'file'>('introspection');
  const [endpointUrl, setEndpointUrl] = useState('http://localhost:4000/graphql');
  
  const handleLoadSchema = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      if (schemaSource === 'introspection') {
        // Simulate introspection query
        await new Promise(resolve => setTimeout(resolve, 1500));
        
        // Mock schema data
        const mockSchema = {
          types: [
            {
              name: 'Query',
              fields: [
                {
                  name: 'users',
                  type: '[User!]!',
                  args: [
                    { name: 'first', type: 'Int' },
                    { name: 'after', type: 'String' }
                  ]
                },
                {
                  name: 'user',
                  type: 'User',
                  args: [
                    { name: 'id', type: 'ID!' }
                  ]
                }
              ]
            },
            {
              name: 'User',
              fields: [
                { name: 'id', type: 'ID!' },
                { name: 'name', type: 'String' },
                { name: 'email', type: 'String' },
                { name: 'posts', type: '[Post!]!' }
              ]
            }
          ]
        };
        
        if (onSchemaLoad) {
          onSchemaLoad(mockSchema);
        }
      } else {
        // File upload simulation
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // Mock schema from file
        const mockFileSchema = {
          types: [
            {
              name: 'Query',
              fields: [
                { name: 'products', type: '[Product!]!' },
                { name: 'product', type: 'Product', args: [{ name: 'id', type: 'ID!' }] }
              ]
            }
          ]
        };
        
        if (onSchemaLoad) {
          onSchemaLoad(mockFileSchema);
        }
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to load schema';
      setError(errorMessage);
      if (onError) {
        onError(errorMessage);
      }
    } finally {
      setLoading(false);
    }
  }, [schemaSource, endpointUrl, onSchemaLoad, onError]);

  return (
    <div className="schema-loader">
      <div className="schema-source-selector">
        <label>
          <input
            type="radio"
            name="schemaSource"
            checked={schemaSource === 'introspection'}
            onChange={() => setSchemaSource('introspection')}
          />
          Introspection Endpoint
        </label>
        <label>
          <input
            type="radio"
            name="schemaSource"
            checked={schemaSource === 'file'}
            onChange={() => setSchemaSource('file')}
          />
          GraphQL Schema File
        </label>
      </div>
      
      {schemaSource === 'introspection' && (
        <div className="endpoint-input">
          <label htmlFor="endpointUrl">GraphQL Endpoint:</label>
          <input
            id="endpointUrl"
            type="url"
            value={endpointUrl}
            onChange={(e) => setEndpointUrl(e.target.value)}
            placeholder="https://api.example.com/graphql"
          />
        </div>
      )}
      
      <div className="schema-actions">
        <button 
          onClick={handleLoadSchema}
          disabled={loading}
          className="load-schema-button"
        >
          {loading ? 'Loading...' : 'Load Schema'}
        </button>
        {error && <div className="error-message">Error: {error}</div>}
      </div>
    </div>
  );
};

export default SchemaLoader;