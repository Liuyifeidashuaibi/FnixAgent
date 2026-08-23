# Django Query class fix for named tuple __range issue
# Issue: TypeError: __new__() missing 1 required positional argument: 'far'
# Fix: unpack iterator when reconstructing named tuples

class Query:
    def resolve_lookup_value(self, value, can_reuse, allow_joins):
        # ... existing code ...
        if isinstance(value, (list, tuple)):
            resolved_elements = [self.resolve_lookup_value(elem, can_reuse, allow_joins) for elem in value]
            # FIXED: unpack the resolved_elements instead of passing as iterator
            new_value = type(value)(*resolved_elements)
        # ... rest of method ...
