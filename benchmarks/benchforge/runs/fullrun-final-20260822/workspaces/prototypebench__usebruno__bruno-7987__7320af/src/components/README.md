# Error Boundaries

This directory contains React error boundary components designed to handle mount issues in Bruno's collection and tab components.

## Components

### `ErrorBoundary`
A general-purpose error boundary component that can wrap any React component.

### `TabErrorBoundary`
A specialized error boundary for tab components with tab-specific fallback UI and actions (Reload Tab, Close Tab).

### `CollectionErrorBoundary`
A specialized error boundary for collection components with collection-specific fallback UI and actions (Reload Collection, Try Again).

## Usage

### With Class Components
```jsx
import { TabErrorBoundary } from './components';

function MyTabComponent() {
  return (
    <TabErrorBoundary onClose={() => console.log('Tab closed')}>
      <div>My tab content</div>
    </TabErrorBoundary>
  );
}
```

### With Functional Components
```jsx
import TabErrorBoundary from './components/TabErrorBoundary';

const MyTab = () => {
  return (
    <TabErrorBoundary onClose={handleClose}>
      <div>My tab content</div>
    </TabErrorBoundary>
  );
};
```

### Using the HOC
```jsx
import { withErrorBoundary } from './components';

const MyComponent = () => {
  return <div>My component content</div>;
};

export default withErrorBoundary(MyComponent, {
  fallback: <div>Custom fallback UI</div>,
  onError: (error, errorInfo) => console.error(error, errorInfo)
});
```

## Purpose

These error boundaries prevent mount issues from crashing the entire Bruno application by:
- Isolating errors to specific tabs or collections
- Providing user-friendly fallback UI
- Offering recovery options (reload, close, retry)
- Logging errors for debugging
- Maintaining application stability

The boundaries handle React lifecycle errors during mounting, updating, and unmounting phases.