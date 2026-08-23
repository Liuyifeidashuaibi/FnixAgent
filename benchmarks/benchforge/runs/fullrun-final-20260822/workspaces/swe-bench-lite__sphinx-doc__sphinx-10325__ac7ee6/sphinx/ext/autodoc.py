# Sphinx autodoc extension - support for multiple classes in inherited-members

# ... existing imports ...

from typing import List, Optional, Union, Any

# ... existing code ...

class Documenter:
    # ... existing class definition ...
    
    def get_object_members(self, want_all: bool) -> List[tuple]:
        """Get members of the object, filtering inherited members from excluded classes."""
        # Get original members
        members = self._get_object_members(want_all)
        
        # Process inherited-members option
        if self.options.inherited_members and self.options.inherited_members != True:
            # Parse comma-separated list of classes to exclude
            if isinstance(self.options.inherited_members, str):
                exclude_classes = [cls.strip() for cls in self.options.inherited_members.split(',')]
            elif isinstance(self.options.inherited_members, (list, tuple)):
                exclude_classes = [str(cls) for cls in self.options.inherited_members]
            else:
                exclude_classes = [str(self.options.inherited_members)]
            
            # Filter out members inherited from excluded classes
            filtered_members = []
            for member_name, member in members:
                # Check if member is inherited from any excluded class
                if not self._is_inherited_from_any_excluded_class(member_name, member, exclude_classes):
                    filtered_members.append((member_name, member))
            members = filtered_members
        
        return members
    
    def _is_inherited_from_any_excluded_class(self, member_name: str, member, exclude_classes: List[str]) -> bool:
        """Check if member is inherited from any of the excluded classes."""
        # Get base classes via MRO
        if hasattr(self.object, '__mro__'):
            for base in self.object.__mro__[1:]:
                if hasattr(base, '__name__') and base.__name__ in exclude_classes:
                    if hasattr(base, member_name) and getattr(base, member_name) is member:
                        return True
        return False
    
    # ... rest of existing methods ...

# ... rest of file ...
