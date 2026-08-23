from enum import Enum
import inspect

class Field:
    def deconstruct(self):
        """
        Return enough information to recreate the field as a 4-tuple:
        (name, path, args, kwargs)
        """
        # ... existing code ...
        
        # Handle enum defaults - use enum name instead of value for stability
        if hasattr(self.default, '__class__') and hasattr(self.default.__class__, '__members__'):
            # This is an enum member
            if hasattr(self.default, 'name') and hasattr(self.default, 'value'):
                # Serialize as EnumClass['NAME'] instead of EnumClass(value)
                # This prevents issues with translated enum values
                enum_class = self.default.__class__
                enum_name = self.default.name
                # Replace the default with a string representation that will be evaluated
                # as EnumClass['NAME'] in migrations
                args = [f"{enum_class.__name__}['{enum_name}']"]
                kwargs.pop('default', None)
                return name, path, args, kwargs
        
        # ... rest of existing deconstruct logic ...
        return name, path, args, kwargs