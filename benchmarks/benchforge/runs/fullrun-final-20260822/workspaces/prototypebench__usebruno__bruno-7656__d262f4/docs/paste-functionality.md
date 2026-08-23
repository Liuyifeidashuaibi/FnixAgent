# Paste Functionality Implementation

## Overview

This document describes the implementation of the enhanced paste functionality for Bruno's collection sidebar.

## Problem Statement

Previously, the paste functionality had two issues:
- Paste always placed items as siblings, regardless of the focused item type
- The "Paste" menu option only appeared on folders, not on requests

## Solution

The solution implements intelligent paste behavior based on the context:

### 1. Context-Aware Pasting
- When focused on a **folder**: paste items **inside** the folder
- When focused on a **request**: paste items as **siblings** (next to the focused request)

### 2. Universal Paste Menu
- The "Paste" menu option now appears on **both folders and requests**
- The menu label changes contextually:
  - "Paste Inside" when focused on a folder
  - "Paste" when focused on a request

## Technical Implementation

### Key Files

- `src/utils/collections/pasteHandler.js` - Core paste logic and utilities
- `src/components/collections/SidebarContextMenu.js` - Context menu component with paste option
- `src/components/collections/CollectionSidebar.js` - Main sidebar component

### Core Functions

#### `handlePasteItem(focusedItem, onPaste)`
- Reads clipboard content using Electron's clipboard API
- Parses clipboard content to determine item type
- Determines paste location based on focused item type
- Calls the provided `onPaste` callback with appropriate parameters

#### `shouldShowPasteMenu(item)`
- Returns `true` for both folders and requests
- Enables paste menu visibility on all collection items

#### `getPasteMenuLabel(focusedItem)`
- Returns "Paste Inside" for folders
- Returns "Paste" for requests

## Usage Example

```javascript
import { handlePasteItem } from '../utils/collections/pasteHandler';

// In your component
const handlePaste = (itemData, options) => {
  if (options.target === 'inside') {
    // Add item to folder
    addRequestToFolder(options.folderId, itemData);
  } else {
    // Add item as sibling
    addRequestAsSibling(options.parentId, itemData);
  }
};

// Handle paste action
handlePasteItem(focusedItem, handlePaste);
```

## Testing

Unit tests are available in `src/utils/collections/pasteHandler.test.js` covering:
- Menu visibility logic
- Label generation
- Paste behavior for different focused item types
- Error handling and fallbacks

## Future Improvements

- Support for pasting multiple items
- Visual feedback during paste operations
- Undo/redo support for paste actions
- Enhanced clipboard format detection (JSON, plain text, HTML)
