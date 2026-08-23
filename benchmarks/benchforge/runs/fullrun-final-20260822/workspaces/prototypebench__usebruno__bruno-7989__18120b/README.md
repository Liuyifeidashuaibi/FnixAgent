# Bruno Snapshot Example Index Refactor

## Overview

This refactor implements JIRA ticket BRU-3385: "Minor refactor to allow example's index to be stored in the snapshot to allow restores".

The changes enable Bruno to store example indices in collection snapshots, which allows for accurate restoration of example positions and proper handling of example-based requests during snapshot restore operations.

## Changes

### 1. Snapshot Utility (`src/utils/snapshot.js`)
- Added `__exampleIndex` property to examples when creating snapshots
- Enhanced `createSnapshot()` to preserve example indices
- Updated `restoreFromSnapshot()` to remove internal `__exampleIndex` properties during restore
- Added `getExampleIndex()` utility to retrieve example indices from snapshot items

### 2. Collection Utilities (`src/containers/Collection/utils.js`)
- Created collection-specific utilities that integrate with the snapshot system
- Added `createCollectionSnapshot()` and `restoreCollectionFromSnapshot()` wrappers
- Implemented `getExampleIndexInItem()` and `updateExampleAtIndex()` for example index management

### 3. Collection Container (`src/containers/Collection/index.js`)
- Exported the new collection utilities for use throughout the application
- Provides a clean interface for snapshot and example index operations

## Usage

### Creating Snapshots with Example Indices
```javascript
import { createCollectionSnapshot } from './containers/Collection';

const collection = {
  items: [
    {
      type: 'request',
      id: 'req-1',
      examples: [
        { id: 'ex-1', name: 'GET Users' },
        { id: 'ex-2', name: 'POST User' }
      ]
    }
  ]
};

const snapshot = createCollectionSnapshot(collection);
// snapshot.items[0].examples[0].__exampleIndex === 0
// snapshot.items[0].examples[1].__exampleIndex === 1
```

### Restoring Collections
```javascript
import { restoreCollectionFromSnapshot } from './containers/Collection';

const restoredCollection = restoreCollectionFromSnapshot(snapshot);
// __exampleIndex properties are removed from restored examples
```

### Getting Example Index
```javascript
import { getExampleIndexInItem } from './containers/Collection';

const exampleIndex = getExampleIndexInItem(requestItem, 'ex-1'); // returns 0
```

## Benefits
- Enables accurate restoration of example positions in collections
- Supports deterministic example selection by index rather than just by name
- Improves reliability of snapshot/restore functionality for collections with multiple examples
- Maintains backward compatibility with existing snapshot formats

## Testing
- Comprehensive unit tests included in `src/utils/snapshot.test.js`
- Tests cover edge cases including collections without examples, missing examples, and index preservation

## Related Issues
- JIRA: [BRU-3385](https://usebruno.atlassian.net/browse/BRU-3385)