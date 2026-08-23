import re

# Django SQLCompiler class with fix for multiline RawSQL ordering
# The fix addresses issue where ordering_parts regex only matches last line
# of multiline SQL, causing incorrect duplicate detection

class SQLCompiler:
    def get_order_by(self):
        # ... existing code ...
        
        # Fix for multiline RawSQL: normalize newlines before regex matching
        # Original problematic code:
        # without_ordering = self.ordering_parts.search(sql).group(1)
        # 
        # Fixed code:
        sql_oneline = ' '.join(sql.splitlines())
        without_ordering = self.ordering_parts.search(sql_oneline).group(1)
        
        # ... rest of existing code ...
        pass
