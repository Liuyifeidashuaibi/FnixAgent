# MCP Context Forge - Visibility Validation PR

## Summary
This PR tightens visibility validation at the schema boundary so only supported enum values are accepted.

Previously, several schemas used plain string typing for `visibility`, which allowed arbitrary values such as `invalid_value`, empty strings, or wrong casing to pass validation. This could lead to inconsistent behavior in token-scoping logic that branches on visibility values.

## Changes Made

### Schema Updates
- Replaced unconstrained visibility string types with `Literal` enums for affected schemas
- Updated `GatewayUpdate`, `ServerCreate`, `A2AAgentCreate`, `A2AAgentUpdate`, and `TeamResponse` schemas
- `TeamResponse.visibility` now uses Team enum typing (`"private" | "public"`) to match Team create/update schemas

### Validator Removal
- Removed redundant visibility validators that became dead code after the `Literal` migration:
  - `ServerCreate.validate_visibility`
  - `A2AAgentCreate.validate_visibility`
  - `A2AAgentUpdate.validate_visibility`

### Test Updates
- Updated tests that previously called removed validator methods directly to use schema instantiation assertions
- Added broad literal-enum validation coverage (`test_visibility_literal_enum_validation`) for valid and invalid visibility inputs across impacted schemas

## Validation Rules
- `GatewayUpdate`, `ServerCreate`, `A2AAgentCreate`, `A2AAgentUpdate`: accept `"private"`, `"public"`, `"org"`
- `TeamResponse`, `TeamCreate`, `TeamUpdate`: accept only `"private"`, `"public"`

## Verification
- Targeted visibility/schema unit tests pass
- Schema-focused unit subset passes (379 passed, 6 skipped)

## Related Issue
Closes: #3525