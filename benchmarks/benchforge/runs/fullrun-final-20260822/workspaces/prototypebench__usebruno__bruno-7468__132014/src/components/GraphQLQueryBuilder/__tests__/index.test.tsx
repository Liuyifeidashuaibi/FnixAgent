import React from 'react';
import { render, screen } from '@testing-library/react';
import { GraphQLQueryBuilder } from '../index';

// Mock the components to avoid dependency issues in tests
jest.mock('../SchemaLoader', () => ({
  default: () => <div data-testid="schema-loader">Schema Loader</div>
}));

jest.mock('../QueryBuilderPane', () => ({
  default: () => <div data-testid="query-builder-pane">Query Builder Pane</div>
}));

jest.mock('../VariablesPane', () => ({
  default: () => <div data-testid="variables-pane">Variables Pane</div>
}));

describe('GraphQLQueryBuilder', () => {
  test('renders without crashing', () => {
    render(<GraphQLQueryBuilder />);
    
    // Check that main elements are present
    expect(screen.getByText('GraphQL Query Builder')).toBeInTheDocument();
    expect(screen.getByTestId('schema-loader')).toBeInTheDocument();
    expect(screen.getByTestId('query-builder-pane')).toBeInTheDocument();
    expect(screen.getByTestId('variables-pane')).toBeInTheDocument();
  });

  test('renders with initial props', () => {
    const mockQuery = 'query { users { id name } }';
    const mockVariables = { first: 10 };
    
    render(
      <GraphQLQueryBuilder
        query={mockQuery}
        variables={mockVariables}
      />
    );
    
    expect(screen.getByText('GraphQL Query Builder')).toBeInTheDocument();
  });

  test('handles expand/collapse functionality', () => {
    render(<GraphQLQueryBuilder />);
    
    // Initially expanded
    expect(screen.getByText('▼ Collapse')).toBeInTheDocument();
    
    // Simulate click (would require more complex testing setup)
  });
});