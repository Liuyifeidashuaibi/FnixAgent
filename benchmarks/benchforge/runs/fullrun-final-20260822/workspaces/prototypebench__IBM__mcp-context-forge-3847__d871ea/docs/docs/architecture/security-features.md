# Security Features Architecture

## Overview

This document describes the security architecture of the MCP Context Forge gateway, focusing on the content security features implemented for US-1 and US-2 (Content Size Limits and MIME Type Restrictions).

## Security Threat Model

The content security features address the following threats:

- **Denial of Service (DoS)**: Large file uploads consuming server resources
- **Malicious Content Injection**: Upload of executable or dangerous content types
- **Data Exfiltration**: Use of allowed content types to bypass security controls
- **Information Disclosure**: Logging of sensitive information in violation messages

## Component Architecture

### Core Security Components

| Component | Responsibility | Location |
|-----------|----------------|----------|
| `ContentSecurityValidator` | Central validation logic for size and MIME types | `mcpgateway/services/content_security.py` |
| `ResourceService` | Resource management with integrated security validation | `mcpgateway/services/resource_service.py` |
| `PromptService` | Prompt management with integrated security validation | `mcpgateway/services/prompt_service.py` |
| Exception Handlers | HTTP 413/415 error responses | `mcpgateway/main.py` |
| Configuration | Security settings management | `mcpgateway/config.py` |

### Data Flow Diagram

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

## Validation Logic Details

### Size Validation

The size validation implements the following logic:

1. **Resource Size Limit**: 100KB (102,400 bytes) maximum
2. **Prompt Size Limit**: 10KB (10,240 bytes) maximum
3. **Validation Points**:
   - Before resource creation
   - Before prompt creation
   - During content processing

### MIME Type Validation

The MIME type validation supports:

- **Base MIME Types**: `text/plain`, `application/json`, `image/png`, etc.
- **Vendor MIME Types**: `application/ld+json`, `application/hal+json`, etc.
- **Wildcard Patterns**: `text/*`, `application/*`, `image/*`
- **Suffix Support**: `+json`, `+xml` suffixes
- **Case Insensitivity**: `TEXT/PLAIN` treated same as `text/plain`
- **Parameter Handling**: `text/plain; charset=utf-8` normalized to `text/plain`

### Enforcement Modes

Two enforcement modes are supported:

| Mode | Behavior | Use Case |
|------|----------|----------|
| **Strict Mode** (`CONTENT_STRICT_MIME_VALIDATION=true`) | Reject requests with invalid MIME types with HTTP 415 | Production enforcement |
| **Log-Only Mode** (`CONTENT_STRICT_MIME_VALIDATION=false`) | Log violations but allow processing | Monitoring and analysis |

## Security Controls

### PII-Safe Logging

To prevent exposure of sensitive information:

- **Email Addresses**: Hashed using SHA-256 (first 16 characters)
- **IP Addresses**: Masked (e.g., `192.168.xxx.xxx`)
- **No Raw Content**: Only content size and MIME type are logged
- **Violation Context**: Limited to necessary information for debugging

### Metrics Collection

Prometheus metrics provide visibility into security events:

| Metric | Description | Labels |
|--------|-------------|--------|
| `content_security_size_violations_total` | Count of size violations | `entity_type="resource"` or `"prompt"` |
| `content_security_mime_violations_total` | Count of MIME type violations | None |

## Integration Points

### With Existing Services

- **Resource Service**: Integrated validation in `create_resource()` method
- **Prompt Service**: Integrated validation in `create_prompt()` method
- **FastAPI Application**: Exception handlers for HTTP 413/415 errors
- **Configuration System**: Settings-driven behavior

### With Monitoring Systems

- **Prometheus**: Metrics collection endpoint `/metrics`
- **Logging**: Structured logging with security-relevant fields
- **Alerting**: Configurable alerts based on violation rates

## Security Assumptions

- The application runs in a trusted network environment
- Database connections are secured with TLS
- File storage is isolated from execution environments
- Authentication and authorization are handled by separate services

## Limitations

- This implementation does not include malware scanning
- Does not perform deep content inspection beyond basic MIME detection
- Does not validate content structure (e.g., JSON schema validation)
- Does not implement rate limiting (US-5)

## Future Enhancements

- **US-3**: Malicious pattern detection
- **US-4**: Template syntax validation
- **US-5**: Rate limiting
- **US-6**: Content hashing and integrity verification

## References

- RFC 7231: HTTP/1.1 Semantics and Content
- RFC 6838: Media Type Specifications and Registration Procedures
- OWASP Secure Coding Practices

---

*Document Version: 1.0*
*Last Updated: 2024-01-01*
*Author: MCP Context Forge Security Team*