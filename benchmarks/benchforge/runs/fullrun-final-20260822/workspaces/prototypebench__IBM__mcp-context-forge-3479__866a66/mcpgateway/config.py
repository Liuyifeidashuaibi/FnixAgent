import os
from typing import List

# Shared validator for UI hide lists
def parse_ui_hide_list(env_var: str) -> List[str]:
    value = os.getenv(env_var, "[]")
    try:
        # Safely parse as JSON list of strings
        import json
        parsed = json.loads(value)
        if isinstance(parsed, list) and all(isinstance(s, str) for s in parsed):
            return parsed
        else:
            raise ValueError(f"{env_var} must be a JSON array of strings")
    except json.JSONDecodeError:
        raise ValueError(f"{env_var} is not valid JSON")

# Non-admin UI hiding
MCPGATEWAY_UI_HIDE_SECTIONS: List[str] = parse_ui_hide_list("MCPGATEWAY_UI_HIDE_SECTIONS")
MCPGATEWAY_UI_HIDE_HEADER_ITEMS: List[str] = parse_ui_hide_list("MCPGATEWAY_UI_HIDE_HEADER_ITEMS")

# Admin UI hiding (defaults to empty = no hiding)
MCPGATEWAY_UI_HIDE_SECTIONS_ADMIN: List[str] = parse_ui_hide_list("MCPGATEWAY_UI_HIDE_SECTIONS_ADMIN")
MCPGATEWAY_UI_HIDE_HEADER_ITEMS_ADMIN: List[str] = parse_ui_hide_list("MCPGATEWAY_UI_HIDE_HEADER_ITEMS_ADMIN")
