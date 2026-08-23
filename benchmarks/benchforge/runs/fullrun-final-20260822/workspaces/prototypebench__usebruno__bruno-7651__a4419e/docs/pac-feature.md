# PAC Proxy Feature Implementation

This document describes the implementation of the PAC (Proxy Auto-Configuration) proxy feature for Bruno.

## Overview

The PAC proxy feature allows Bruno to automatically determine the appropriate proxy server for each HTTP request based on JavaScript functions defined in a PAC file. This enables intelligent routing decisions such as:

- Direct connections for internal networks
- Proxy connections for external websites
- Different proxies for different domains
- Fallback behavior when primary proxy is unavailable

## Implementation Details

### Components

1. **PacProxySettings.jsx** - React component for configuring PAC settings with URL and file upload options
2. **pacResolver.js** - Utility for resolving proxy configuration from PAC scripts
3. **ProxyConfiguration.jsx** - Main proxy configuration component integrating PAC mode

### Key Features

- **URL-based PAC**: Fetch PAC files from remote URLs (HTTP/HTTPS)
- **File-based PAC**: Upload local PAC files (.pac extension)
- **Real-time validation**: Validate PAC configuration before use
- **Error handling**: Graceful fallback to direct connection on errors
- **Security**: Sandboxed execution environment for PAC scripts

## Usage

### Configuration

1. Navigate to Bruno's proxy settings
2. Select "PAC File" mode
3. Choose between:
   - **URL**: Enter the URL to your PAC file
   - **File Upload**: Browse and select a local .pac file

### PAC Script Requirements

PAC files must contain a `FindProxyForURL(url, host)` function that returns one of:

- `"DIRECT"` - Connect directly without proxy
- `"PROXY host:port"` - Use specified HTTP proxy
- `"SOCKS host:port"` - Use specified SOCKS proxy
- Combinations like `"PROXY proxy1:8080; PROXY proxy2:8080; DIRECT"`

## Technical Notes

- The implementation uses a simplified PAC script evaluator for demonstration
- In production, consider using established libraries like `pac-resolver`
- PAC scripts are executed in a sandboxed environment for security
- Network requests respect Bruno's existing authentication and timeout configurations

## Future Enhancements

- Support for PAC script caching
- PAC script debugging tools
- Integration with Bruno's environment variables
- Advanced PAC function support (DNS resolution, etc.)

## Related Issues

- PR #7633: Initial PAC URL fetch implementation
- Issue #7651: PAC file upload extension