# Bruno Collection Drag & Drop Enhancement

## Overview

This implementation adds support for moving requests between collections via drag and drop with:

- Automatic tab closing when requests are moved to prevent "Request no longer exists" errors
- Format conversion between .bru and .yml formats when dragging between collections with different formats
- Blocking of folder cross-format moves with appropriate error messaging

## Features

### 1. Tab Closing on Move
- When a request is dragged from one collection to another, the corresponding open tab is automatically closed
- Prevents the "Request no longer exists" error that occurs when trying to access a request that has been moved

### 2. Format Conversion
- Seamless conversion between Bruno's native .bru (JSON) format and YAML (.yml) format
- Uses js-yaml library for YAML parsing and serialization
- Maintains data integrity during conversion

### 3. Cross-Format Move Handling
- Blocks folder-level cross-format moves with user-friendly toast notifications
- Allows individual request moves between different format collections

## Architecture

### IPC Handlers
- `collection:drag-move` - Main handler for moving requests with format conversion
- `collection:close-tab-on-move` - Handler for closing tabs when requests are moved

### Utility Functions
- Format conversion utilities in `src/common/utils/format-converter.js`
- Toast notification system for user feedback

### Renderer Components
- Drag-and-drop handlers in `src/renderer/components/collection/CollectionDragHandler.js`
- CSS styling for drag states and toast notifications

## Usage

1. Drag a request from one collection to another collection
2. If formats differ, automatic conversion occurs
3. The source tab is closed automatically
4. Success/error notifications appear as toast messages

## Testing

Unit tests are provided in `tests/unit/collection-drag-handler.test.js` to verify:
- Same format moves
- .bru to .yml conversion
- .yml to .bru conversion
- Error handling for unsupported formats

## Dependencies

- `js-yaml` - For YAML parsing and serialization
- Electron IPC - For main/renderer process communication

## JIRA Reference

BRU-2792 - Close open tab when request is moved to different collection via drag and drop