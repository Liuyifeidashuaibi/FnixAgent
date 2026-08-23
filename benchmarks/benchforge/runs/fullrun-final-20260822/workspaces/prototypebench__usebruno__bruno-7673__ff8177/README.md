# Bruno HeaderList Implementation (BRU-2893)

This implementation adds the `headerList` property to both `req` and `res` objects in Bruno's script environment, following the [BRU-2893 Jira issue](https://usebruno.atlassian.net/browse/BRU-2893) specification.

## Implementation Details

### Core Components

- `src/headers/HeaderList.js`: The main `HeaderList` class implementation that follows MDN Headers API conventions
- `src/script/sandbox/headers-integration.js`: Integration code that enhances `req` and `res` objects with the `headerList` property
- `tests/headerList-api-test.js`: Test file demonstrating the complete API usage

### Key Design Features

✅ **Separate property**: `req.headerList` and `res.headerList` are distinct from `req.headers` and `res.headers`, ensuring full backward compatibility

✅ **MDN-aligned naming**: Uses `append`, `set`, `delete`, `forEach` methods matching [MDN Headers API](https://developer.mozilla.org/en-US/docs/Web/API/Headers)

✅ **Case-insensitive**: All key lookups are case-insensitive per HTTP specification

✅ **Dynamic reads**: `req.headerList` reads from live `req.headers` object on every access

✅ **Read-only response**: `res.headerList` throws appropriate errors for write operations

✅ **QuickJS support**: Designed for Bruno's QuickJS sandbox with iterator support

### API Compliance

The implementation supports all methods specified in the BRU-2893 documentation:

- **Read Methods**: `get()`, `one()`, `all()`, `count()`
- **Search Methods**: `has()`, `find()`, `filter()`, `indexOf()`
- **Iteration Methods**: `forEach()`, `map()`, `reduce()`
- **Transform Methods**: `toObject()`, `toString()`, `toJSON()`
- **Write Methods**: `append()`, `set()`, `delete()`, `clear()`, `populate()`, `repopulate()`, `assimilate()`

### Usage Example

```js
// In Bruno script
console.log(req.headerList.get('Content-Type'));
req.headerList.append('X-Custom', 'value');
console.log(res.headerList.all());
```

## Backward Compatibility

- Existing `req.headers` and `res.headers` raw objects remain untouched
- No Proxy layer used - avoids breaking existing scripts
- All existing script functionality continues to work unchanged

## Contribution Checklist

- [x] Addresses only BRU-2893 issue
- [x] No breaking changes introduced
- [x] Follows Bruno contribution guidelines
- [x] Implements all specified API methods
