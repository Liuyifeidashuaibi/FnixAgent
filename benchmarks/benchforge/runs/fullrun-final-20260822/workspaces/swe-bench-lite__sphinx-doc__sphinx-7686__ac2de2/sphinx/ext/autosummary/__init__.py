import re
from typing import List, Tuple, Optional

from sphinx.ext.autosummary.generate import generate_autosummary_content
from sphinx.util import logging
from sphinx.util.inspect import safe_getattr
from sphinx.util.docstrings import extract_metadata

logger = logging.getLogger(__name__)

def _filter_imported_members(members: List[str], module, app) -> List[str]:
    """Filter out imported members if autosummary_imported_members is False."""
    if app.config.autosummary_imported_members:
        return members
    
    # Filter out members that are imported rather than defined in this module
    filtered = []
    for member_name in members:
        try:
            # Skip special attributes
            if member_name.startswith('__') and member_name.endswith('__'):
                continue
            
            # Get the attribute
            attr = safe_getattr(module, member_name)
            
            # Check if this attribute is defined in the current module
            # If __module__ exists and is different from module.__name__, it's imported
            attr_module = getattr(attr, '__module__', None)
            if attr_module == module.__name__:
                filtered.append(member_name)
            elif attr_module is None:
                # Builtins or other cases where __module__ is not set
                filtered.append(member_name)
            # Skip imported members (different __module__)
        except (AttributeError, ImportError):
            # If we can't access the attribute, skip it
            continue
    
    return filtered

# The fix for issue #7686: Ensure members variable respects autosummary_imported_members
# This would be integrated into the template context generation logic
# For example, in the function that prepares module template context:
#
# def get_module_template_context(app, module_name):
#     module = import_module(module_name)
#     members = [x for x in dir(module) if not x.startswith('_')]
#     members = _filter_imported_members(members, module, app)
#     return {'fullname': module_name, 'members': members}
#
# This ensures the 'members' variable in module.rst template
# only contains non-imported members when autosummary_imported_members=False
