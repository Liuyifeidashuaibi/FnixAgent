import { render, screen } from '@testing-library/react';
import { GraphQLQueryBuilder } from '../index';

// Test configuration for GraphQL Query Builder
export const TEST_CONFIG = {
  // Mock schema for testing
  mockSchema: {
    types: [
      {
        name: 'Query',
        fields: [
          { name: 'users', type: '[User!]!' },
          { name: 'user', type: 'User' }
        ]
      }
    ]
  },
  
  // Default test props
  defaultProps: {
    query: `query { users { id name } }`,
    variables: { first: 10 },
    onQueryChange: jest.fn(),
    onVariablesChange: jest.fn()
  },
  
  // Test utilities
  renderWithProvider: (ui: React.ReactElement) => {
    return render(ui);
  },
  
  waitForElement: async (selector: string) => {
    await screen.findByText(selector);
  }
};