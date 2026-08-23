# Bruno Multipart Form Fixes

This repository contains fixes for Bruno API client's multipart form handling as specified in JIRA ticket [BRU-2869](https://usebruno.atlassian.net/browse/BRU-2869).

## Fixes Implemented

- ✅ Handle empty row file selection
- ✅ Move clear file (X) icon to the right side of the file name
- ✅ Fix upload button hover color

## Files Modified

- `src/components/requests/MultipartForm.tsx` - Main component with logic fixes
- `src/components/requests/MultipartForm.module.css` - CSS styling with positioning and hover fixes
- `src/components/requests/MultipartForm.test.tsx` - Unit tests verifying the fixes
- `src/components/requests/README.md` - Documentation

## Installation

```bash
npm install
```

## Running Tests

```bash
npm test
```

## Contribution Checklist

- [x] Addresses one issue (BRU-2869)
- [x] No breaking changes
- [x] Includes tests
- [x] Follows contribution guidelines
- [x] Linked to JIRA ticket

## License

MIT