# MCP Context Forge - Tools Visibility Fix

## Fix Description

This fix ensures that the visibility query parameter is correctly applied when listing tools using admin tokens.

Previously, admin tokens bypassed access control in a way that caused the visibility filter (public, team, private) to be ignored. As a result, requests like `/tools?visibility=team` or `/tools?visibility=private` returned the full list of tools instead of only the tools matching the specified visibility.

The fix ensures that the explicit visibility filter provided in the request is always honored, even when using an admin token. Admin bypass now only affects access permissions, not the filtering logic.

## Testing

1. **Create PRIVATE tools**
   ```bash
   for i in {1..5}; do
     curl -s -X POST http://localhost:4444/tools \
       -H "Authorization: Bearer $MCPGATEWAY_BEARER_TOKEN" \
       -H "Content-Type: application/json" \
       -d "{\"tool\": {\"name\": \"private-tool-$i\", \"description\": \"Private test tool $i\", \"visibility\": \"private\"}}"
   done
   ```

2. **Verify PRIVATE filter**
   ```bash
   curl -H "Authorization: Bearer $MCPGATEWAY_BEARER_TOKEN_ADMIN" \
   "http://localhost:4444/tools?visibility=private&limit=0" | jq '. | length'
   ```

3. **Create TEAM tools**
   ```bash
   for i in {1..5}; do
     curl -s -X POST http://localhost:4444/tools \
       -H "Authorization: Bearer $MCPGATEWAY_BEARER_TOKEN" \
       -H "Content-Type: application/json" \
       -d "{\"tool\": {\"name\": \"team-tool-$i\", \"description\": \"Team test tool $i\", \"visibility\": \"team\", \"teamId\": \"team-1\"}}"
   done
   ```

4. **Verify TEAM filter**
   ```bash
   curl -H "Authorization: Bearer $MCPGATEWAY_BEARER_TOKEN_ADMIN" \
   "http://localhost:4444/tools?visibility=team&limit=0" | jq '. | length'
   ```

5. **Create PUBLIC tools**
   ```bash
   for i in {1..5}; do
     curl -s -X POST http://localhost:4444/tools \
       -H "Authorization: Bearer $MCPGATEWAY_BEARER_TOKEN" \
       -H "Content-Type: application/json" \
       -d "{\"tool\": {\"name\": \"public-tool-$i\", \"description\": \"Public test tool $i\", \"visibility\": \"public\"}}"
   done
   ```

6. **Verify PUBLIC filter**
   ```bash
   curl -H "Authorization: Bearer $MCPGATEWAY_BEARER_TOKEN_ADMIN" \
   "http://localhost:4444/tools?visibility=public&limit=0" | jq '. | length'
   ```

## Verification

| Check                                 | Command              | Status |
|---------------------------------------|----------------------|--------|
| Lint suite                            | `make lint`          | Pass   |
| Unit tests                            | `make test`          | Pass   |

## MCP Compliance
- [x] Matches current MCP spec
- [x] No breaking change to MCP clients

## Checklist
- [x] Code formatted (`make black isort pre-commit`)
- [x] No secrets/credentials committed
