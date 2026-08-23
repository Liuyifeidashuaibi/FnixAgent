import { scrollPositionManager } from '../ScrollPositionManager';

// Mock localStorage for testing
const mockLocalStorage = {
  store: {},
  getItem: jest.fn((key) => mockLocalStorage.store[key]),
  setItem: jest.fn((key, value) => {
    mockLocalStorage.store[key] = value;
  }),
  removeItem: jest.fn((key) => {
    delete mockLocalStorage.store[key];
  })
};

beforeEach(() => {
  mockLocalStorage.store = {};
  global.localStorage = mockLocalStorage;
});

describe('ScrollPositionManager', () => {
  test('should save and retrieve scroll position', () => {
    // Save position
    scrollPositionManager.saveScrollPosition('headers', 150);
    
    // Retrieve position
    const position = scrollPositionManager.getScrollPosition('headers');
    
    expect(position).toBe(150);
  });

  test('should persist to localStorage', () => {
    scrollPositionManager.saveScrollPosition('body', 200);
    
    expect(mockLocalStorage.setItem).toHaveBeenCalledWith('bruno-scroll-body', '200');
  });

  test('should handle invalid localStorage access gracefully', () => {
    // Simulate localStorage error
    global.localStorage.setItem = jest.fn(() => {
      throw new Error('localStorage not available');
    });
    
    // This should not throw an error
    expect(() => {
      scrollPositionManager.saveScrollPosition('assertions', 100);
    }).not.toThrow();
  });

  test('should clear scroll position', () => {
    scrollPositionManager.saveScrollPosition('headers', 150);
    scrollPositionManager.clearScrollPosition('headers');
    
    const position = scrollPositionManager.getScrollPosition('headers');
    expect(position).toBe(0);
    expect(mockLocalStorage.removeItem).toHaveBeenCalledWith('bruno-scroll-headers');
  });
});
