import copy
from .hooks import default_hooks

class Request:
    def __init__(self, method=None, url=None, headers=None, files=None,
                 data=None, params=None, auth=None, cookies=None, hooks=None,
                 json=None):
        # ... other initialization
        
        # Initialize hooks with default values
        self.hooks = default_hooks()
        
        # Fix: Handle lists in hooks dictionary values properly
        if hooks:
            for event in hooks:
                if event in self.hooks:
                    hook_value = hooks[event]
                    if isinstance(hook_value, (list, tuple)):
                        # Use the list/tuple as-is
                        self.hooks[event] = list(hook_value)
                    elif callable(hook_value):
                        # Wrap single callable in a list
                        self.hooks[event] = [hook_value]
                    else:
                        # Skip invalid hook values
                        continue
        # ... rest of init method
