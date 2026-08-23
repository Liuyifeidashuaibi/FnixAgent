# Bruno Components

This directory contains reusable UI components for the Bruno application.

## SelectionList

A flexible selection list component designed for import workflows including:

- Git import
- Bulk import paths
- GitHub import (future)

See [SelectionList.README.md](./SelectionList.README.md) for detailed documentation.

## Usage

Import the component:

```tsx
import { SelectionList } from './components';
// or
import SelectionList from './components/SelectionList';
```

## Development

- Run Storybook to preview components: `npm run storybook`
- Run tests: `npm test`
- Build for production: `npm run build:components`

## Contribution Guidelines

- Follow Bruno's coding standards and accessibility guidelines
- Ensure all components support both light and dark modes
- Include TypeScript definitions for all public APIs
- Write unit tests for component logic
- Document props and usage examples
