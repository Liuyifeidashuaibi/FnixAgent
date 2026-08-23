# Bruno Multipart Boundary Preservation Fix

## Issue
Fixes https://github.com/usebruno/bruno/issues/7523
[JIRA](https://usebruno.atlassian.net/browse/BRU-2905)

When users specify a boundary parameter in their Content-Type header for multipart/mixed requests with TEXT body mode, Bruno now preserves the user-defined boundary instead of generating a new one.

## Changes Made

### 1. New Utility Module: `src/utils/multipart-boundary.js`
- Added `getBoundaryFromContentType()` to extract boundary from Content-Type header
- Added `generateRandomBoundary()` for fallback boundary generation
- Added `getMultipartBoundary()` that prioritizes user-defined boundaries

### 2. HTTP Client Update: `src/requests/http-client.js`
- Modified multipart request processing to preserve user-specified boundaries
- Updated logic to check for existing boundary parameter before generating new one
- Ensures Content-Type header maintains user-defined boundary

### 3. Test Coverage: `src/tests/multipart-boundary.test.js`
- Comprehensive tests for boundary extraction from various Content-Type formats
- Tests for preserving user boundaries vs generating random ones
- Edge case handling for different boundary parameter formats

## Usage

The fix automatically applies when:
- Request has Content-Type header containing 'multipart/'
- Content-Type includes 'boundary=' parameter (quoted or unquoted)
- TEXT body mode is used

The user-defined boundary will be preserved in both the Content-Type header and multipart body processing.

## Verification

To verify the fix works correctly:
1. Create a multipart/mixed request with Content-Type: `multipart/mixed; boundary="my-custom-boundary"`
2. Use TEXT body mode with appropriate multipart formatting
3. The request should use `my-custom-boundary` instead of generating a new random boundary

## Compatibility
- Maintains backward compatibility
- No breaking changes to existing API
- Works with all existing multipart content types (mixed, form-data, etc.)