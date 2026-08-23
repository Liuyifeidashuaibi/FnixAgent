import os
from typing import Dict, List

from .config import (
    MCPGATEWAY_UI_HIDE_SECTIONS,
    MCPGATEWAY_UI_HIDE_HEADER_ITEMS,
    MCPGATEWAY_UI_HIDE_SECTIONS_ADMIN,
    MCPGATEWAY_UI_HIDE_HEADER_ITEMS_ADMIN,
)


def get_ui_visibility_config(is_admin: bool = False) -> Dict[str, List[str]]:
    """
    Returns UI visibility configuration based on user role and embedded mode.

    - Admins use *_ADMIN env vars.
    - Non-admins use legacy vars, plus auto-hide 'logout' and 'team_selector'
      when MCPGATEWAY_UI_EMBEDDED is truthy.
    """
    # Determine which hide lists to use
    if is_admin:
        sections_to_hide = MCPGATEWAY_UI_HIDE_SECTIONS_ADMIN
        header_items_to_hide = MCPGATEWAY_UI_HIDE_HEADER_ITEMS_ADMIN
    else:
        sections_to_hide = MCPGATEWAY_UI_HIDE_SECTIONS
        header_items_to_hide = MCPGATEWAY_UI_HIDE_HEADER_ITEMS

        # Embedded mode defaults for non-admins only
        if os.getenv("MCPGATEWAY_UI_EMBEDDED", "").lower() in ("1", "true", "yes"):
            # Ensure logout and team_selector are hidden
            if "logout" not in header_items_to_hide:
                header_items_to_hide = header_items_to_hide + ["logout"]
            if "team_selector" not in header_items_to_hide:
                header_items_to_hide = header_items_to_hide + ["team_selector"]

    return {
        "hidden_sections": sections_to_hide,
        "hidden_header_items": header_items_to_hide,
    }
