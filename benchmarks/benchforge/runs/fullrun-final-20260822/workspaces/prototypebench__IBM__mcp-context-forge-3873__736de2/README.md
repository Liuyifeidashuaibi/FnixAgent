# MCP Context Forge - REST Tool Enhancements

This repository contains enhancements to the REST tool implementation, addressing issues #3855 and #3857.

## Backend Improvements

### Non-JSON Response Handling (#3855)
- New `_handle_json_parse_error()` helper function for graceful fallback when JSON parsing fails
- Handles multiple exception types: `json.JSONDecodeError`, `orjson.JSONDecodeError`, `UnicodeDecodeError`, `AttributeError`
- Supports REST APIs returning HTML error pages, plain text, XML, or responses with encoding issues
- Returns raw text as `{"response_text": <truncated>}` instead of crashing

### Response Truncation (Security Enhancement)
- Configurable setting: `REST_RESPONSE_TEXT_MAX_LENGTH` (default: 5000 chars, range: 1000-100000)
- Truncates non-JSON response text to prevent exposing excessive sensitive data in error responses
- Applies to both success and error responses
- Logs warning when truncation occurs with original and truncated lengths

### Query Parameter Handling (#3857)
- GET requests: URL query params merged with input arguments (URL params take precedence on conflicts)
- POST/PUT/PATCH/DELETE: Query params preserved in URL to support signed URLs (Azure SAS, AWS presigned URLs, webhook signatures)
- Added conflict warning when URL query params override input arguments for better debugging

### jq Filter Validation
- Added validation to detect simple email addresses mistakenly used as jq filters (e.g., `user@example.com`)
- Uses regex pattern `^[^.\[\]|]+@[^.\[\]|]+\.[^.\[\]|]+$` to catch basic email patterns without false positives
- Logs warning and treats invalid filters as empty (returns unfiltered data)

## Frontend Enhancements

### Admin UI Tool Testing Workflow
- New `invokeTool(toolName)` function called by "Invoke" buttons in Tools table
- Fetches tool details via API (`fetchToolDetails`) and populates modal dynamically
- Dynamic form generation from tool input schema (`createFormInput`, `generateToolFormFields`)
- Refactored `runToolTest()` and `runToolValidation()` to use consistent tools/call method structure:
  ```json
  {
    "method": "tools/call",
    "params": { "name": toolName, "arguments": {...} }
  }
  ```
- Enhanced error logging for better debugging

## Test Coverage

Comprehensive test suite added:
- `TestJqFilterEmailValidation`: Email address detection and valid filter preservation
- `TestRestToolQueryParamHandling`: GET/POST/PUT/PATCH/DELETE param handling, conflict warnings
- `TestRestToolNonJsonResponses`: HTML, plain text, XML, encoding errors, empty responses
- `TestRestToolResponseTruncation`: Large responses, small responses, custom config values

## Usage

### Backend
```python
from rest_tool import make_rest_request, validate_jq_filter

# Make a REST request
result = make_rest_request(
    method="GET",
    url="https://api.example.com/data",
    params={"page": 1},
    jq_filter=".data[]"
)

# Validate jq filter
if validate_jq_filter(".users[]"):
    print("Valid jq filter")
```

### Frontend
```javascript
// Initialize admin tool test system
const adminToolTest = new AdminUIToolTest();

// Invoke a tool
adminToolTest.invokeTool('my-tool');
```

## Configuration

The `config.py` file contains configurable settings including:
- `REST_RESPONSE_TEXT_MAX_LENGTH`: Controls response truncation length
- `REST_DEFAULT_TIMEOUT`: Default timeout for REST requests
- `REST_MAX_RETRIES`: Maximum number of retries for failed requests

## License

MIT License
