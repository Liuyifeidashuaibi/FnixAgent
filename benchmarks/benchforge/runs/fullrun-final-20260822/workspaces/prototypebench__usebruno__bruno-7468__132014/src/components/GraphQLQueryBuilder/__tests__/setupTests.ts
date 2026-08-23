import '@testing-library/jest-dom';
import { configure } from '@testing-library/react';

// Configure React Testing Library
configure({ testIdAttribute: 'data-testid' });

// Mock console.error to prevent test noise
const originalConsoleError = console.error;
beforeAll(() => {
  console.error = (...args) => {
    // Suppress specific warnings that are expected in tests
    if (typeof args[0] === 'string' && 
        (args[0].includes('Warning:') || 
         args[0].includes('act()') || 
         args[0].includes('ReactDOM.render'))) {
      return;
    }
    originalConsoleError(...args);
  };
});

afterAll(() => {
  console.error = originalConsoleError;
});

// Mock ResizeObserver since it's not available in JSDOM
const mockResizeObserver = jest.fn();
mockResizeObserver.mockImplementation(() => ({
  observe: jest.fn(),
  unobserve: jest.fn(),
  disconnect: jest.fn()
}));

global.ResizeObserver = mockResizeObserver as any;