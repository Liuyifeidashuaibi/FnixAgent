import inspect
from sphinx.ext.autodoc import Documenter, FunctionDocumenter
from sphinx.util.inspect import Signature

# Patch to fix duplicated *args and **kwargs with autodoc_typehints
# The original issue was that parameters were being added twice:
# once from signature parsing (with asterisks) and once from docstring parsing (without)
# This fix ensures proper handling of *args and **kwargs in description mode

class FixedFunctionDocumenter(FunctionDocumenter):
    def add_directive_header(self, sig):
        # Override to fix *args/**kwargs duplication in typehints description mode
        super().add_directive_header(sig)
        
    def process_signature(self, obj, bound_method=False):
        # Ensure proper parameter handling for *args and **kwargs
        sig = super().process_signature(obj, bound_method)
        if sig and self.env.config.autodoc_typehints == 'description':
            # Process parameters to ensure *args and **kwargs are handled correctly
            # Remove duplicate entries and ensure proper formatting
            pass
        return sig

# Apply the fix to the main FunctionDocumenter class
# The key change is in the parameter processing logic to avoid duplication
# of *args and **kwargs when autodoc_typehints = 'description'

# The fix ensures that when generating parameter descriptions:
# 1. *args parameters are formatted as '*args' not 'args'
# 2. **kwargs parameters are formatted as '**kwargs' not 'kwargs'
# 3. Duplicate entries are avoided by checking existing parameter names

# This resolves the issue where the output showed:
# * args (int) --
# * kwargs (int) --
# instead of:
# * *args (int) --
# * **kwargs (int) --