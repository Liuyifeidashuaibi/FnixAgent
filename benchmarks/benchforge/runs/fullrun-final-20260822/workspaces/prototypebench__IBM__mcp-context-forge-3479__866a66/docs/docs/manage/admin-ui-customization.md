# Admin vs Non-Admin UI Visibility

This document explains how UI sections and header items can be hidden differently for admin and non-admin users.

## Environment Variables

| Variable | Applies to | Default |
|---|---|---|
| `MCPGATEWAY_UI_HIDE_SECTIONS` | non-admin users | `[]` |
| `MCPGATEWAY_UI_HIDE_HEADER_ITEMS` | non-admin users | `[]` |
| `MCPGATEWAY_UI_HIDE_SECTIONS_ADMIN` | admin users | `[]` (show all) |
| `MCPGATEWAY_UI_HIDE_HEADER_ITEMS_ADMIN` | admin users | `[]` (show all) |

## Embedded Mode Behavior

In embedded mode (`MCPGATEWAY_UI_EMBEDDED=1`), the following header items are **automatically hidden for non-admin users only**:  
- `logout`  
- `team_selector`

Admins retain full access unless explicitly hidden via `_ADMIN` variables.

## Example Usage

Hide the `settings` section and `help` header item for non-admins:
```env
MCPGATEWAY_UI_HIDE_SECTIONS=["settings"]
MCPGATEWAY_UI_HIDE_HEADER_ITEMS=["help"]
```

Hide `audit_logs` and `users` sections *only for admins*:
```env
MCPGATEWAY_UI_HIDE_SECTIONS_ADMIN=["audit_logs", "users"]
```

## Backward Compatibility

Deployments without `_ADMIN` variables behave identically: admins see everything; non-admin behavior is unchanged.
