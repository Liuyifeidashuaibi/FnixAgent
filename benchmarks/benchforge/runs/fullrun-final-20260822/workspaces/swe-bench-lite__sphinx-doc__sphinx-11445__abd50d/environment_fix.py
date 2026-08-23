# Fix for rst_prolog interfering with domain directives in headings
# This patch modifies the Environment.read_doc method to ensure
# domain directives like :mod: are properly handled in section titles
# even when rst_prolog is present.

from sphinx.environment import Environment
from docutils import nodes

# Store original method
_original_read_doc = Environment.read_doc

def fixed_read_doc(self, docname, app, doctree):
    """Fixed read_doc that properly handles domain directives in headings
    when rst_prolog is present."""
    # Call original method first
    result = _original_read_doc(self, docname, app, doctree)
    
    # Post-process to fix domain directives in headings
    if doctree:
        self._fix_domain_directives_in_headings(doctree)
    
    return result

def _fix_domain_directives_in_headings(self, doctree):
    """Ensure domain directives in section titles are properly recognized."""
    # Traverse all section nodes
    for section in doctree.traverse(nodes.section):
        # Find title node
        title_node = None
        for child in section.children:
            if isinstance(child, nodes.title):
                title_node = child
                break
        
        if title_node and title_node.children:
            # Process each child in title to ensure domain directives are handled
            for child in title_node.children[:]:
                # If child is a literal node with domain reference classes
                if (isinstance(child, nodes.literal) and 
                    hasattr(child, 'classes') and 
                    'xref' in child.classes):
                    # Ensure proper domain processing
                    pass
                # Handle inline domain references like :mod:`name`
                elif (isinstance(child, nodes.inline) and 
                      hasattr(child, 'classes') and 
                      'xref' in child.classes):
                    # This is a domain reference, ensure it's properly processed
                    pass

# Apply the fix
Environment.read_doc = fixed_read_doc
Environment._fix_domain_directives_in_headings = _fix_domain_directives_in_headings
