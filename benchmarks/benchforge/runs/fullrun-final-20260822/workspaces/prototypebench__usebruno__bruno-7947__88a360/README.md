# Bruno Scroll Position Persistence

Implementation of scroll position persistence for Bruno's request editor panes (Headers, Assertions, Body).

## Features

- ✅ Cross-tab scroll position persistence
- ✅ Cross-session (localStorage) persistence
- ✅ React hook integration (`useScrollPosition`)
- ✅ Error-resilient localStorage handling
- ✅ Memory-efficient caching
- ✅ Comprehensive unit tests
- ✅ TypeScript type definitions

## Installation

```bash
npm install
```

## Usage

Import and use the scroll position manager in your Bruno components:

```javascript
import { useScrollPosition } from './components/RequestEditor/ScrollPositionManager';

const HeadersPane = () => {
  const { ref } = useScrollPosition('headers');
  
  return <div ref={ref}>/* headers content */</div>;
};
```

## Testing

```bash
npm run test:scroll
```

## Development

The implementation follows Bruno's architecture patterns and is designed to be easily integrated into the existing codebase.

## License

MIT