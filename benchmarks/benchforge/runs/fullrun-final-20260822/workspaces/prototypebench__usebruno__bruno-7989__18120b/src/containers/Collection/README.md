# Collection Container

## Overview

The Collection container provides utilities for managing Bruno collections with support for example index preservation in snapshots.

### Key Features
- `createCollectionSnapshot()`: Creates collection snapshots with example indices
- `restoreCollectionFromSnapshot()`: Restores collections from snapshots
- `getExampleIndexInItem()`: Gets the index of an example in a collection item
- `updateExampleAtIndex()`: Updates examples while preserving their original index position

### Integration

These utilities integrate with Bruno's snapshot system to ensure that example positions are preserved during snapshot creation and restoration operations.

### Usage

```javascript
import { 
  createCollectionSnapshot, 
  restoreCollectionFromSnapshot,
  getExampleIndexInItem 
} from './containers/Collection';

// Create snapshot
const snapshot = createCollectionSnapshot(collection);

// Get example index
const index = getExampleIndexInItem(requestItem, 'example-id');
```

### Example Index Benefits
- Enables accurate restoration of example positions
- Supports deterministic example selection by index
- Improves reliability of snapshot/restore functionality
- Maintains backward compatibility with existing snapshot formats