## 🔗 Related Issue
Closes https://github.com/IBM/mcp-context-forge/issues/3368

---

## 📝 Summary

1. Modified `mcpgateway/admin.py `(lines 10764-10777):

- Added try-catch block around all orjson.loads() calls for form field parsing
- Catches `orjson.JSONDecodeError` and returns a 422 response with descriptive error message
- Affects fields: headers, input_schema, output_schema, annotations, query_mapping, header_mapping, allowlist, plugin_chain_pre, plugin_chain_post
- Error message format: `Invalid JSON in form field: {error details}`
- Applied identical fix to admin_edit_tool endpoint

2. Added/updated tests in `tests/unit/mcpgateway/test_admin.py`:

- test_admin_add_tool_with_invalid_query_mapping_json: New test verifying 422 for invalid query_mapping JSON
- test_admin_add_tool_with_invalid_header_mapping_json: New test verifying 422 for invalid header_mapping JSON
- test_admin_add_tool_with_invalid_json: Updated existing test to expect 422 response instead of raised exception
- Added test_admin_edit_tool_with_invalid_headers_json
- Added test_admin_edit_tool_with_invalid_input_schema_json

Test Results:

All 3 new/updated tests pass
All 17 tests in TestAdminToolRoutes pass
No regressions introduced

---

## 🏷️ Type of Change
- [x] Bug fix
- [ ] Feature / Enhancement
- [ ] Documentation
- [ ] Refactor
- [ ] Chore (deps, CI, tooling)
- [ ] Other (describe below)

---

## 🧪 Verification

| Check                     | Command         | Status |
|---------------------------|-----------------|--------|
| Lint suite                | `make lint`     |      ✅   |
| Unit tests                | `make test`     |    ✅     |
| Coverage ≥ 80%            | `make coverage` |        |

---

## ✅ Checklist
- [x] Code formatted (`make black isort pre-commit`)
- [x] Tests added/updated for changes
- [ ] Documentation updated (if applicable)
- [x] No secrets or credentials committed

---

## 📓 Notes (optional)
_Screenshots, design decisions, or additional context._