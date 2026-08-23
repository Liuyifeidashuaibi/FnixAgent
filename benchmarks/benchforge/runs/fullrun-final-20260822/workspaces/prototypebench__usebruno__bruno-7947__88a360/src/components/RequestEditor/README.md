# Scroll Position Persistence for Request Panes

This module implements scroll position persistence across Bruno's request editor panes:
- Headers pane
- Assertions pane 
- Body pane

## Features

- **Cross-tab persistence**: Scroll positions are maintained when switching between Headers, Assertions, and Body tabs
- **Cross-session persistence**: Scroll positions are saved to localStorage for browser restarts
- **Memory optimization**: Uses Map for in-memory caching with localStorage fallback
- **Error resilience**: Gracefully handles localStorage errors
- **React hook integration**: Easy to use with `useScrollPosition` hook

## Usage

```javascript
import { useScrollPosition } from './ScrollPositionManager';

const MyPane = () => {
  const { ref, restoreScroll, saveScroll } = useScrollPosition('my-pane-id');
  
  return (
    <div ref={ref}>
      {/* Your scrollable content */}
    </div>
  );
};
```

## Implementation Details

The implementation uses:
- `useRef` to reference the scrollable DOM element
- `useEffect` to restore scroll position on mount and set up scroll listeners
- `localStorage` for persistent storage across browser sessions
- A singleton manager class for centralized scroll position management

## Testing

Unit tests are provided in `__tests__/ScrollPositionManager.test.js` to verify:
- Basic save/retrieve functionality
- localStorage persistence
- Error handling for localStorage failures
- Clear functionality

## Performance Considerations

- Scroll events are debounced to prevent performance issues
- Only stores scrollTop values (not full scroll state)
- Memory-efficient Map-based caching
- Lightweight localStorage usage

## Compatibility

Works with React 16.8+ and modern browsers.
