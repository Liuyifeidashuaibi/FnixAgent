# Bruno Selection List Component

A reusable selection list component for Bruno's import workflows.

## Features

- ✅ Select all functionality
- ✅ Individual item selection
- ✅ Configurable visible rows (scrollable viewport)
- ✅ Customizable spacing between items
- ✅ Empty state handling
- ✅ Header support
- ✅ TypeScript support
- ✅ Dark mode compatible
- ✅ Accessibility compliant

## Integration Points

- Git import workflow
- Bulk import paths dialog
- GitHub import (future implementation)

## Installation

```bash
npm install @bruno/selection-list
# or
yarn add @bruno/selection-list
```

## Usage

```tsx
import SelectionList from '@bruno/selection-list';

const MyImportComponent = () => {
  const [selectedItems, setSelectedItems] = useState<Set<MyItemType>>(new Set());
  
  return (
    <SelectionList
      items={importItems}
      renderItem={(item, isSelected, toggleItem) => (
        <div>
          <input type="checkbox" checked={isSelected} onChange={toggleItem} />
          <span>{item.name}</span>
        </div>
      )}
      selectedItems={selectedItems}
      onSelectionChange={setSelectedItems}
      visibleRows={5}
    />
  );
};
```

## Development

1. Clone the repository
2. Install dependencies: `npm install`
3. Start Storybook: `npm run storybook`
4. Run tests: `npm test`

## License

MIT
