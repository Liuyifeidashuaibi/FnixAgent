# GraphQL Query Builder Tests

## Test Strategy

The GraphQL Query Builder is tested using a multi-layered approach:

### Unit Tests
- Individual component functionality
- State management and event handling
- Prop validation and edge cases

### Integration Tests
- Component interactions (builder ↔ variables ↔ schema loader)
- Two-way data binding
- Schema loading workflows

### End-to-End Tests
- Complete user flows
- Realistic scenarios with mock API responses
- Cross-browser compatibility

## Test Structure

- `index.test.tsx`: Main component integration tests
- `schema-loader.test.tsx`: Schema loading functionality
- `query-builder-pane.test.tsx`: Query building logic
- `variables-pane.test.tsx`: Variable management
- `utils.test.ts`: Helper function tests

## Test Fixtures

- `schema-fixtures.ts`: Mock GraphQL schemas for different scenarios
- `query-fixtures.ts`: Sample queries for testing
- `variable-fixtures.ts`: Common variable patterns

## Testing Utilities

- `test-config.ts`: Shared test configuration and helpers
- `mocks/`: Jest mocks for external dependencies
- `setupTests.ts`: Test environment setup

## Running Tests

```bash
# Run all tests
npm test

# Run specific test file
npm test -- src/components/GraphQLQueryBuilder/__tests__/index.test.tsx

# Watch mode
npm test -- --watch
```

## Coverage Goals

- 80%+ statement coverage
- 75%+ branch coverage
- 90%+ function coverage
- 100% critical path coverage