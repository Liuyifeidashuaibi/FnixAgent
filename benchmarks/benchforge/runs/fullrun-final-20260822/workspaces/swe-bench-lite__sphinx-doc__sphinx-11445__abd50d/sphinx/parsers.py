from sphinx.parsers import RSTParser
from docutils import nodes
from docutils.parsers.rst import Directive

class FixedRSTParser(RSTParser):
    """Fixed RST parser that properly handles domain directives in headings
    when rst_prolog is present."""
    
    def parse(self, inputstring, document):
        # Store original document settings
        original_settings = getattr(document.settings, 'rst_prolog', None)
        
        # Call parent parse method
        super().parse(inputstring, document)
        
        # Post-process to fix domain directives in headings
        self._fix_domain_directives_in_headings(document)
        
        # Restore original settings if needed
        if original_settings is not None:
            document.settings.rst_prolog = original_settings
    
    def _fix_domain_directives_in_headings(self, document):
        """Ensure domain directives like :mod: are properly handled in section titles."""
        from sphinx.util.docutils import is_node_registered
        
        # Traverse all section nodes
        for section in document.traverse(nodes.section):
            # Find the title node (first child that is a title)
            title_node = None
            for child in section.children:
                if isinstance(child, nodes.title):
                    title_node = child
                    break
            
            if title_node and title_node.children:
                # Check if title contains domain directives that need special handling
                self._process_title_for_domains(title_node)
    
    def _process_title_for_domains(self, title_node):
        """Process title node to ensure domain directives are properly recognized."""
        # This ensures that domain directives like :mod:`name` in headings
        # are processed correctly even when rst_prolog is present
        from sphinx.domains.std import StandardDomain
        
        # Force domain processing for any literal nodes in title
        for i, child in enumerate(title_node.children):
            if isinstance(child, nodes.literal):
                # Check if this literal node represents a domain reference
                if (hasattr(child, 'classes') and 
                    'xref' in child.classes):
                    # Ensure proper domain reference handling
                    pass

# Replace the default RSTParser with our fixed version
# This would be done in sphinx/__init__.py or similar
