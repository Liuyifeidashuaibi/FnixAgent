# Multipart Form Component

This component handles multipart form data editing in Bruno API client.

## Features

- Handles empty row file selection (ensures at least one row is always present)
- Clear file (X) icon positioned to the right side of the file name
- Upload button with fixed hover color styling
- Responsive design for different screen sizes

## Usage

```tsx
import MultipartForm from './MultipartForm';

const MyComponent = () => {
  const [multipartItems, setMultipartItems] = useState<MultipartFormItem[]>([]);
  
  return (
    <MultipartForm 
      items={multipartItems} 
      onChange={setMultipartItems} 
    />
  );
};
```

## JIRA Ticket

- [BRU-2869](https://usebruno.atlassian.net/browse/BRU-2869): Handle empty row file selection, move clear file icon, fix upload button hover color

## Contribution Checklist

- [x] Handles empty row file selection
- [x] Moves clear file (X) icon to the right side of the file name
- [x] Fixes upload button hover color
- [x] Includes unit tests
- [x] Follows Bruno contribution guidelines