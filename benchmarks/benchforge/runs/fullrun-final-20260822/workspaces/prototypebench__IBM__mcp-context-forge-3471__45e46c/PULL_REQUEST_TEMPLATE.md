## 🔗 Related Issue
Closes #3428

---

## 📝 Summary
_What does this PR do and why?_

✅ Fixed: FileUrl JSON Serialization Error in Admin UI

### Original Problem Fixed
The admin UI was crashing with `TypeError: Object of type FileUrl is not JSON serializable` when rendering root directories in the template at line 8048 of `admin.html`.

**Solution Implemented:**
Modified `/home/suresh/dev/issue_3428/mcp-context-forge/mcpgateway/main.py`:
- Added imports for `AnyUrl` (from pydantic) and `FileUrl` (from mcpgateway.common.models)
- Created custom `URLEncoder` class in the `tojson_attr` filter that converts `FileUrl` and `AnyUrl` objects to strings
- Updated `json.dumps()` call to use the custom encoder

**Testing:** All tests passed successfully ✅

---

### Additional Issue Identified: Roots Not Persisting

**Root Cause:**
The `RootService` stores roots **in memory only** (`self._roots` dictionary). This is by design, not a bug:
- Roots are ephemeral and only persist for the application's lifetime
- When the app restarts, all roots are lost except those configured in `settings.default_roots`
- There is no database table for roots - they're intentionally transient

**Current Behavior:**
1. User adds a root via admin UI → stored in memory
2. Application restarts or service reinitializes → all non-default roots disappear
3. Only roots in `settings.default_roots` configuration persist across restarts

**Workaround:**
To make roots persist across restarts, add them to the `default_roots` configuration in your environment/config file:
```python
default_roots = ["file:///path/to/dir1", "file:///path/to/dir2"]
```

**Note:** If roots are disappearing immediately after saving (without restart), that would indicate a different issue. The JSON serialization fix I implemented should resolve any immediate display issues after adding roots.

---

## 🏷️ Type of Change
- [ ] Bug fix
- [ ] Feature / Enhancement
- [ ] Documentation
- [ ] Refactor
- [ ] Chore (deps, CI, tooling)
- [ ] Other (describe below)

---

## 🧪 Verification

| Check                     | Command         | Status |
|---------------------------|-----------------|--------|
| Lint suite                | `make lint`     |        |
| Unit tests                | `make test`     |        |
| Coverage ≥ 80%            | `make coverage` |        |

---

## ✅ Checklist
- [X] Code formatted (`make black isort pre-commit`)
- [X] Tests added/updated for changes
- [ ] Documentation updated (if applicable)
- [X] No secrets or credentials committed

---

## 📓 Notes (optional)
_Screenshots, design decisions, or additional context._