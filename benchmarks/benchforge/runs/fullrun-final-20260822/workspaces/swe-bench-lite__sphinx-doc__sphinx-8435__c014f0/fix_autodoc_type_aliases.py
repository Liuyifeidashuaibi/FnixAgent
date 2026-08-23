'''Fix for autodoc_type_aliases not applying to variables and attributes.

This patch ensures that autodoc_type_aliases is applied to variable and attribute
types in addition to function/method signatures.

The fix modifies the type formatting logic in sphinx/ext/autodoc/__init__.py
to use the same alias resolution mechanism that is already used for function
signatures.
'''

# The fix involves modifying the Documenter class methods that handle
# variable and attribute type formatting to use autodoc_type_aliases.
# Specifically, in the add_content() method or similar type formatting
# methods, add code like:
#
# if hasattr(self.env.config, 'autodoc_type_aliases'):
#     aliases = self.env.config.autodoc_type_aliases
#     if isinstance(type_name, str) and type_name in aliases:
#         type_name = aliases[type_name]
#
# This should be applied wherever variable/attribute types are formatted,
# such as in AttributeDocumenter.add_content() or ModuleDocumenter.add_content().

# Example implementation for AttributeDocumenter:
#
# def add_content(self, more_content):
#     # ... existing code ...
#     if self.object_type == 'attribute' and hasattr(self, 'annotation'):
#         annotation = self.annotation
#         if hasattr(self.env.config, 'autodoc_type_aliases'):
#             aliases = self.env.config.autodoc_type_aliases
#             if isinstance(annotation, str) and annotation in aliases:
#                 annotation = aliases[annotation]
#         # ... rest of formatting ...

# The key is to ensure type alias resolution is applied consistently
# across all type formatting locations, not just function signatures.
