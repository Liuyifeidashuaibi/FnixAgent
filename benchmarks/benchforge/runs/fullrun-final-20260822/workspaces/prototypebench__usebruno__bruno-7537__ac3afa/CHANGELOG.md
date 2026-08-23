# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-08-22

### Added

- New `getSourceContextFromContent` utility function to extract context lines from in-memory scripts
- Enhanced error formatter that utilizes in-memory script content for error context
- Playwright e2e tests for draft script error handling across pre-request, post-response, and test scripts
- Unit tests for error formatting with draft script support

### Changed

- Error formatter now prioritizes in-memory script content over saved file content for better accuracy with unsaved changes
- Improved context extraction to handle edge cases (first/last lines, invalid line numbers)

### Fixed

- Ensures users see the most relevant code context during debugging of draft scripts
- Better stack trace handling for draft script errors

## [0.1.0] - 2026-08-21

### Added

- Initial project setup with core utility functions
- Basic test infrastructure
