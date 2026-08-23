# US-2 Implementation Plan: MIME Type Restrictions for Resources

## Overview

This document outlines the implementation plan for User Story US-2: "MIME Type Restrictions for Resources" as part of issue #538. The goal is to implement comprehensive content security validation for the MCP Context Forge gateway, adding MIME type restrictions and content size limits.

## Requirements

### Functional Requirements
- **US-2.1**: Implement MIME type allowlist validation for resources
- **US-2.2**: Support vendor MIME types and suffixes (+json, +xml)
- **US-2.3**: Support flexible enforcement modes (strict reject or log-only)
- **US-2.4**: Provide HTTP 415 error responses with detailed context in strict mode
- **US-2.5**: Log violations in log-only mode with PII-safe logging
- **US-2.6**: Integrate with Prometheus metrics for security violations

### Non-Functional Requirements
- **US-2.7**: Content size validation (100KB for resources, 10KB for prompts)
- **US-2.8**: Thread-safe implementation
- **US-2.9**: Singleton pattern for validator instance
- **US-2.10**: Performance impact < 5ms per request

## Architecture Design

### Component Diagram

```
+----------------+     +---------------------+     +-------------------+
|   HTTP Client  |---->|   Content Security    |---->|   Resource/Prompt |
| (Browser/App)  |     |     Validator         |     |     Services      |
+----------------+     +---------------------+     +-------------------+
          |                      |                          |
          |                      |                          |
          v                      v                          v
+----------------+     +---------------------+     +-------------------+
|   FastAPI App  |<----|   Exception Handlers|<----|   Database/Storage|
|   Middleware   |     |   (413/415)         |     |                   |
+----------------+     +---------------------+     +-------------------+
```

### Data Flow

1. Client sends HTTP request with content
2. FastAPI middleware intercepts request
3. Content Security Validator performs size and MIME validation
4. If validation fails:
   - Strict mode: Return HTTP 413/415 with detailed error
   - Log-only mode: Log violation and continue processing
5. If validation passes: Forward to appropriate service
6. Service processes request and returns response

## Implementation Details

### Core Validation Logic

The `ContentSecurityValidator` class implements the core validation logic:

- **Size Validation**: Compares content length against configured maximums
- **MIME Validation**: Checks against allowlist with support for:
  - Base MIME types (text/plain, application/json)
  - Vendor MIME types (application/ld+json)
  - Wildcard patterns (text/*, application/*)
  - Case-insensitive matching
  - Parameter handling (text/plain; charset=utf-8)

### Configuration Management

Four new configuration settings are introduced:

| Setting | Default | Description |
|---------|---------|-------------|
| `CONTENT_MAX_RESOURCE_SIZE` | 102400 (100KB) | Maximum allowed size for resources |
| `CONTENT_MAX_PROMPT_SIZE` | 10240 (10KB) | Maximum allowed size for prompts |
| `CONTENT_STRICT_MIME_VALIDATION` | false | Enable strict rejection mode |
| `CONTENT_ALLOWED_RESOURCE_MIMETYPES` | 18 safe types | Comma-separated list of allowed MIME types |

### Error Handling Strategy

| Error Code | Condition | Response Body |
|------------|-----------|---------------|
| 413 | Content size exceeds limit | `{"error": "Request entity too large", "detail": "...", "documentation_url": "..."}` |
| 415 | MIME type not in allowlist | `{"error": "Unsupported media type", "detail": "...", "allowed_types": [...], "documentation_url": "..."}` |

## Security Considerations

### PII-Safe Logging

- Email addresses are hashed using SHA-256 (first 16 chars)
- IP addresses are masked (192.168.xxx.xxx)
- No sensitive data is logged in violation messages

### Metrics Collection

Prometheus metrics track security violations:

- `content_security_size_violations_total{entity_type="resource|prompt"}`
- `content_security_mime_violations_total`

## Testing Strategy

### Unit Tests

- 526 lines of unit tests covering all validation scenarios
- Size validation edge cases (exactly at limit, 1 byte over, etc.)
- MIME type validation (valid types, invalid types, vendor types, wildcards)
- Strict vs log-only mode testing
- PII-safe logging verification
- Thread safety testing

### Integration Tests

- End-to-end testing of resource creation with various MIME types
- Prompt creation with size limits
- HTTP status code verification (413, 415)
- Metrics collection verification

## Deployment Strategy

### Phase 1: Monitoring Mode (Recommended)

- Deploy with `CONTENT_STRICT_MIME_VALIDATION=false`
- Monitor Prometheus metrics for 1-2 weeks
- Analyze violation patterns to identify legitimate use cases
- Adjust MIME allowlist if needed

### Phase 2: Enforcement Mode

- Enable strict mode with `CONTENT_STRICT_MIME_VALIDATION=true`
- Monitor error rates and user feedback
- Have rollback plan ready

## Rollback Plan

- Revert configuration to `CONTENT_STRICT_MIME_VALIDATION=false`
- Monitor metrics to ensure no impact on legitimate traffic
- Analyze logs to identify root cause of issues

## Documentation

- Architecture documentation: `docs/docs/architecture/security-features.md`
- Operational guide: `docs/docs/manage/content-security.md`
- API reference: Updated OpenAPI specification

## Timeline

| Milestone | Estimated Time |
|-----------|----------------|
| Design & Implementation | 3 days |
| Unit Testing | 2 days |
| Integration Testing | 2 days |
| Documentation | 1 day |
| Deployment Preparation | 1 day |
| Total | 9 days |

## Success Criteria

- ✅ All unit tests pass (526 lines)
- ✅ Integration tests pass
- ✅ Prometheus metrics are collected correctly
- ✅ PII-safe logging is implemented
- ✅ Documentation is complete and accurate
- ✅ Performance impact is < 5ms per request
- ✅ Zero critical security vulnerabilities

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| False positives blocking legitimate traffic | Start with log-only mode, analyze patterns before enabling strict mode |
| Performance impact on high-volume endpoints | Optimize validation logic, add caching where appropriate |
| Configuration complexity | Provide clear documentation and default values |
| MIME type detection errors | Implement fallback detection and logging |

## Dependencies

- FastAPI framework
- Prometheus client library
- Python standard library

## Approval

This implementation plan requires approval from:
- Security Team
- Architecture Review Board
- Product Owner

---

*Document Version: 1.0*
*Last Updated: 2024-01-01*
*Author: MCP Context Forge Team*