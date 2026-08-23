# Multipart Form Body Components

This directory contains components for handling multipart form data with multi-file uploads in Bruno.

## Components

### `MultipartFormBody.tsx`
Main component that combines form fields and file selection for multipart requests.

### `MultipartFileSelector.tsx`
File selector component supporting drag & drop and multiple file selection.

### `FileChip.tsx`
Individual file display component with remove functionality.

### `multipartFormBody.css`
Styling for the multipart form components.

## Features

- ✅ Multi-file upload support
- ✅ Drag & drop file selection
- ✅ File chips with name, size, and remove button
- ✅ Form field management (key/value pairs)
- ✅ Responsive design
- ✅ Disabled/read-only mode support
- ✅ File path normalization
- ✅ Content type auto-detection

## Usage

```tsx
import MultipartFormBody from './MultipartFormBody';

<MultipartFormBody 
  value={{ 'field1': 'value1', 'field2': 'value2' }}
  files={[{ id: '1', name: 'file.txt', path: 'file.txt', size: 1024, type: 'text/plain' }]}
  onChange={(formData, files) => {
    // Handle form data and files changes
  }}
/>
```

## Testing

Unit tests are available in `MultipartFormBody.test.tsx`.

## Dependencies

- React
- TypeScript
- Bruno's utility functions for multipart handling

## Future Improvements

- File preview thumbnails
- Progress indicators for large file uploads
- File validation (size limits, allowed types)
- Batch file operations
- Integration with Bruno's collection path resolution