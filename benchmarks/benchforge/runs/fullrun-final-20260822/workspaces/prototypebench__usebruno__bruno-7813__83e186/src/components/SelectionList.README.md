# SelectionList Component

A reusable selection list component for Bruno, designed for import workflows (git import, bulk import paths, github import).

## Features

- Select all functionality with checkbox
- Individual item selection
- Configurable visible rows (for scrollable viewport)
- Customizable spacing between items
- Empty state handling
- Header support
- TypeScript support
- Dark mode compatible

## Props

| Prop | Type | Description |
|------|------|-------------|
| `items` | `T[]` | Array of items to display |
| `renderItem` | `(item: T, isSelected: boolean, toggleItem: () => void) => React.ReactNode` | Function to render each item |
| `renderHeader` | `() => React.ReactNode` | Optional function to render header |
| `onSelectAll` | `(selectAll: boolean) => void` | Callback when select all is toggled |
| `selectedItems` | `Set<T> \| null` | External selected items state (if controlled) |
| `onSelectionChange` | `(selectedItems: Set<T>) => void` | Callback when selection changes |
| `visibleRows` | `number` | Number of visible rows before scrolling (default: 5) |
| `spacing` | `'sm' \| 'md' \| 'lg'` | Spacing between items (default: 'md') |
| `emptyStateMessage` | `string` | Message to show when no items (default: 'No items available') |

## Usage Example

```tsx
import SelectionList from './SelectionList';

const MyComponent = () => {
  const [selectedItems, setSelectedItems] = useState<Set<MyItemType>>(new Set());
  
  const items: MyItemType[] = [
    { id: '1', name: 'Item 1' },
    { id: '2', name: 'Item 2' },
  ];
  
  const renderItem = (item, isSelected, toggleItem) => (
    <div>
      <input type="checkbox" checked={isSelected} onChange={toggleItem} />
      <span>{item.name}</span>
    </div>
  );
  
  return (
    <SelectionList
      items={items}
      renderItem={renderItem}
      selectedItems={selectedItems}
      onSelectionChange={setSelectedItems}
      visibleRows={5}
    />
  );
};
```

## Integration Points

- Git import workflow
- Bulk import paths dialog
- GitHub import (future implementation)
