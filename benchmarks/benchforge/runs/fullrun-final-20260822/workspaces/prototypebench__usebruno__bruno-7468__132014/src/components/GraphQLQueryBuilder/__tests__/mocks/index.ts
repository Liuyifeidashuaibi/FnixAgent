// Mocks for GraphQL Query Builder tests

// Mock GraphQL client
export const mockGraphQLClient = {
  query: jest.fn(),
  introspect: jest.fn()
};

// Mock file system API
export const mockFileSystem = {
  readFile: jest.fn(),
  writeFile: jest.fn()
};

// Mock browser APIs
export const mockWindow = {
  addEventListener: jest.fn(),
  removeEventListener: jest.fn()
};

// Mock localStorage
export const mockLocalStorage = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn()
};

// Mock fetch API
export const mockFetch = jest.fn();

// Setup mocks
export const setupMocks = () => {
  global.fetch = mockFetch;
  global.window = mockWindow as any;
  global.localStorage = mockLocalStorage;
};