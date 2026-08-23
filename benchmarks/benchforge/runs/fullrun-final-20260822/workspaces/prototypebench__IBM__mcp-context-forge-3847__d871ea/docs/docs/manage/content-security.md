# Content Security Management Guide

## Overview

This guide provides operational instructions for managing content security features in the MCP Context Forge gateway. It covers configuration, monitoring, and troubleshooting.

## Configuration

### Environment Variables

The following environment variables control content security behavior:

| Variable | Default | Description |
|----------|---------|-------------|
| `CONTENT_MAX_RESOURCE_SIZE` | `102400` | Maximum size for resources (bytes) |
| `CONTENT_MAX_PROMPT_SIZE` | `10240` | Maximum size for prompts (bytes) |
| `CONTENT_STRICT_MIME_VALIDATION` | `false` | Enable strict rejection mode (`true`/`false`) |
| `CONTENT_ALLOWED_RESOURCE_MIMETYPES` | `text/plain,text/markdown,...` | Comma-separated list of allowed MIME types |

### Configuration Examples

#### Production Configuration
```bash
# Production settings
CONTENT_MAX_RESOURCE_SIZE=102400
CONTENT_MAX_PROMPT_SIZE=10240
CONTENT_STRICT_MIME_VALIDATION=false
CONTENT_ALLOWED_RESOURCE_MIMETYPES=text/plain,text/markdown,text/html,application/json,application/xml,image/png,image/jpeg
```

#### Development Configuration
```bash
# Development with stricter limits
CONTENT_MAX_RESOURCE_SIZE=51200
CONTENT_MAX_PROMPT_SIZE=5120
CONTENT_STRICT_MIME_VALIDATION=true
CONTENT_ALLOWED_RESOURCE_MIMETYPES=text/plain,application/json
```

## Monitoring

### Prometheus Metrics

Monitor these key metrics:

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `content_security_size_violations_total{entity_type="resource"}` | Resource size violations | > 10 per hour |
| `content_security_size_violations_total{entity_type="prompt"}` | Prompt size violations | > 50 per hour |
| `content_security_mime_violations_total` | MIME type violations | > 5 per hour |

### Log Analysis

Security-related log entries include:

- `Content size violation`: Size limit exceeded
- `MIME type violation`: Invalid MIME type detected
- `PII-safe logging`: Hashed emails and masked IPs

Example log entry:
```
WARNING: Content size violation: POST /v1/resources - Resource content size 105000 bytes exceeds maximum allowed 102400 bytes
```

## Deployment Strategy

### Phase 1: Monitoring Mode

1. **Deploy with log-only mode**: `CONTENT_STRICT_MIME_VALIDATION=false`
2. **Monitor for 1-2 weeks**: Track violation patterns and rates
3. **Analyze logs**: Identify legitimate use cases that trigger violations
4. **Adjust allowlist**: Add necessary MIME types to `CONTENT_ALLOWED_RESOURCE_MIMETYPES`

### Phase 2: Enforcement Mode

1. **Enable strict mode**: `CONTENT_STRICT_MIME_VALIDATION=true`
2. **Monitor error rates**: Ensure < 0.1% error rate for legitimate traffic
3. **Prepare rollback plan**: Revert to log-only mode if issues arise
4. **Communicate changes**: Notify API consumers about new restrictions

## Troubleshooting

### Common Issues

| Issue | Diagnosis | Resolution |
|-------|-----------|------------|
| **HTTP 413 errors** | Content size exceeds limit | Reduce file size or increase `CONTENT_MAX_RESOURCE_SIZE` |
| **HTTP 415 errors** | MIME type not in allowlist | Add MIME type to `CONTENT_ALLOWED_RESOURCE_MIMETYPES` or use supported type |
| **High violation rates** | Legitimate traffic being blocked | Review allowlist and adjust for legitimate use cases |
| **Missing metrics** | Prometheus client not configured | Verify `prometheus_client` is imported and metrics are registered |

### Debugging Steps

1. **Check configuration**: Verify environment variables are set correctly
2. **Review logs**: Look for security-related log entries
3. **Test with curl**: Verify behavior with known good/bad requests
4. **Check metrics**: Confirm metrics are being collected

## Testing Commands

### Test Size Limits
```bash
# Test resource size limit (should fail at 102401 bytes)
curl -X POST http://localhost:8000/v1/resources \
  -H "Content-Type: text/plain" \
  --data-binary @<(dd if=/dev/zero bs=1 count=102401 2>/dev/null)
```

### Test MIME Type Validation
```bash
# Test valid MIME type (should succeed)
curl -X POST http://localhost:8000/v1/resources \
  -H "Content-Type: text/plain" \
  --data "test content"

# Test invalid MIME type (should fail in strict mode)
curl -X POST http://localhost:8000/v1/resources \
  -H "Content-Type: application/zip" \
  --data "test content"
```

## Best Practices

- **Start conservative**: Begin with small allowlists and expand as needed
- **Monitor continuously**: Set up alerts for security violations
- **Document changes**: Keep track of allowlist modifications
- **Test thoroughly**: Validate all supported MIME types
- **Plan for evolution**: Allowlist will need updates as new use cases emerge

## Support

For assistance with content security configuration:

- **Internal Support**: security-team@mcp-context-forge.ibm.com
- **Documentation**: https://docs.mcp-context-forge.ibm.com/content-security
- **Issue Tracking**: GitHub issue #538

---

*Document Version: 1.0*
*Last Updated: 2024-01-01*
*Author: MCP Context Forge Operations Team*