import { renderHook, act } from '@testing-library/react';
import { usePersistedEditorScroll } from './usePersistedEditorScroll';

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

describe('usePersistedEditorScroll', () => {
  it('should restore scroll position from localStorage', () => {
    const tabUid = 'test-tab-123';
    const entityUid = 'test-entity-456';
    const savedPosition = { scrollTop: 100, scrollLeft: 50 };
    
    mockLocalStorage.getItem.mockReturnValue(JSON.stringify(savedPosition));
    
    const { result } = renderHook(() => usePersistedEditorScroll(tabUid, entityUid));
    
    expect(result.current.isRestored).toBe(true);
  });

  it('should save scroll position to localStorage on scroll', () => {
    const tabUid = 'test-tab-123';
    const entityUid = 'test-entity-456';
    
    const { result } = renderHook(() => usePersistedEditorScroll(tabUid, entityUid));
    
    // Simulate scroll event
    act(() => {
      if (result.current.editorRef.current) {
        result.current.editorRef.current.scrollTop = 200;
        result.current.editorRef.current.scrollLeft = 75;
        
        // Trigger scroll event
        const scrollEvent = new Event('scroll');
        result.current.editorRef.current.dispatchEvent(scrollEvent);
      }
    });
    
    expect(mockLocalStorage.setItem).toHaveBeenCalledWith(
      `persisted::${tabUid}::editor-scroll-${entityUid}`,
      JSON.stringify({ scrollTop: 200, scrollLeft: 75 })
    );
  });
});