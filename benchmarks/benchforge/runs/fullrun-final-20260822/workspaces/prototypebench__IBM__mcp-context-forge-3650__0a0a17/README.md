# MCP Context Forge - Maximum Members Fix

## Bug Description
The "Maximum Members" field in the Create Team and Edit Team modals had `max="1000"` hardcoded, causing two issues:
- Non-admin users could set `max_members` above `MAX_MEMBERS_PER_TEAM`
- When `MAX_MEMBERS_PER_TEAM > 1000`, the browser rejected valid values

## Solution
Implemented role-aware behavior for the Maximum Members input:

### For Admin Users
- No `max` attribute (no browser-side cap)
- Helper text: "Optional. Admins can set any limit."

### For Non-Admin Users
- `max` attribute set to `MAX_MEMBERS_PER_TEAM` (default 100)
- Default value: `min(50, MAX_MEMBERS_PER_TEAM)`
- Helper text: "Optional, defaults to {MAX_MEMBERS_PER_TEAM}."

## Files Modified
- `mcpgateway/admin.py`: Reads `MAX_MEMBERS_PER_TEAM` from environment and passes to template context
- `mcpgateway/templates/admin.html`: Implements conditional max attribute and helper text
- `.env`: Example configuration file

## Environment Variable
`MAX_MEMBERS_PER_TEAM` (default: 100) controls the maximum members per team for non-admin users.

## Verification
- Set `MAX_MEMBERS_PER_TEAM=30` in `.env` → non-admin users can only set up to 30
- Set `MAX_MEMBERS_PER_TEAM=2000` in `.env` → non-admin users can set up to 2000, admins have no limit
- Default value in Create modal is `min(50, MAX_MEMBERS_PER_TEAM)`
