# GraphQL Query Builder

A visual, recursive GraphQL query builder that syncs with the editor and variables panes.

## Features

- **Visual Query Building**: Drag-and-drop or click-to-add fields for building GraphQL queries
- **Recursive Structure**: Supports nested objects and complex types
- **Real-time Sync**: Changes in builder automatically update the editor and vice versa
- **Draggable & Resizable**: Query Builder and Variables panes can be resized
- **Schema Integration**: Load GraphQL schema via introspection or from files
- **Variable Management**: Add, edit, and remove variables with type support
- **Prettify Functionality**: Format generated queries for readability

## Props

| Prop | Type | Description |
|------|------|-------------|
| `schema` | `GraphQLSchema` | GraphQL schema object for auto-completion and validation |
| `query` | `string` | Current GraphQL query string |
| `variables` | `Record<string, any>` | Current variables object |
| `onQueryChange` | `(query: string) => void` | Callback when query changes |
| `onVariablesChange` | `(variables: Record<string, any>) => void` | Callback when variables change |

## Usage

```tsx
import { GraphQLQueryBuilder } from './components/GraphQLQueryBuilder';

<GraphQLQueryBuilder
  query={currentQuery}
  variables={currentVariables}
  onQueryChange={setQuery}
  onVariablesChange={setVariables}
/>
```

## Schema Loading

The component supports loading schemas via:
- GraphQL Introspection (default)
- Local GraphQL schema files
- Custom schema objects

## Styling

The component uses CSS variables for theme compatibility:
- `--brand`: Primary brand color
- `--surface`: Background surface color
- `--surface-hover`: Hover surface color
- `--border`: Border color
- `--text-primary`: Primary text color
- `--text-secondary`: Secondary text color

## Responsive Design

The component adapts to different screen sizes, switching to vertical layout on mobile devices.