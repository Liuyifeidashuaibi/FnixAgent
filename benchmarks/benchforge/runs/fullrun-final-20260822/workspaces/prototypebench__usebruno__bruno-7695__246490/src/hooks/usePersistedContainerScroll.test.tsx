import { renderHook, act } from '@testing-library/react';
import { usePersistedContainerScroll } from './usePersistedContainerScroll';

// Mock localStorage
const mockLocalStorage = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
  key: jest.fn(),
  length: 0,
};

beforeEach(() => {
  Object.defineProperty(window, 'localStorage', {
    value: mockLocalStorage,
  });
  mockLocalStorage.getItem.mockClear();
  mockLocalStorage.setItem.mockClear();
});

describe('usePersistedContainerScroll', () => {
  it('should restore scroll position from localStorage', () => {
    const tabUid = 'test-tab-123';
    const entityUid = 'test-entity-456';
    const savedPosition = { scrollTop: 150, scrollLeft: 25 };
    
    mockLocalStorage.getItem.mockReturnValue(JSON.stringify(savedPosition));
    
    const { result } = renderHook(() => usePersistedContainerScroll(tabUid, entityUid));
    
    expect(result.current.isRestored).toBe(true);
  });

  it('should save scroll position to localStorage on scroll', () => {
    const tabUid = 'test-tab-123';
    const entityUid = 'test-entity-456';
    
    const { result } = renderHook(() => usePersistedContainerScroll(tabUid, entityUid));
    
    // Simulate scroll event
    act(() => {
      if (result.current.containerRef.current) {
        result.current.containerRef.current.scrollTop = 300;
        result.current.containerRef.current.scrollLeft = 100;
        
        // Trigger scroll event
        const scrollEvent = new Event('scroll');
        result.current.containerRef.current.dispatchEvent(scrollEvent);
      }
    });
    
    expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
      `persisted::${tabUid}::container-scroll-${entityUid}`,
      JSON.stringify({ scrollTop: 300, scrollLeft: 100 })
    );
  });
});