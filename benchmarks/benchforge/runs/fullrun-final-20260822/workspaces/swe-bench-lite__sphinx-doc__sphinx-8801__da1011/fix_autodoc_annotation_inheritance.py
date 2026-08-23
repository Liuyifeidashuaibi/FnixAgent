The fix for this issue involves modifying Sphinx's autodoc logic to properly detect annotation-only attributes with inline comments as documented when inherited.

The problem is in sphinx/ext/autodoc/documenters.py, specifically in the ClassDocumenter class's logic for determining if an attribute is documented.

The fix adds support for recognizing inline comments (like `#: docstring`) on annotation-only attributes when checking if inherited members should be included.

Key changes needed:
1. In the method that checks if an attribute has documentation (likely in get_attr or a similar method)
2. Extend the documentation detection to look for inline comments in the source code for annotation-only attributes
3. Ensure inherited annotation-only attributes with inline comments are treated as documented

The specific code change would be in the condition that determines if a member is undocumented, adding logic to parse source lines and detect `#: ` comments on annotation lines.

This is a known issue in Sphinx autodoc where annotation-only attributes without traditional docstrings were incorrectly marked as undocumented, especially when inherited.