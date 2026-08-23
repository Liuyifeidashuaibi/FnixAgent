# Fix for napoleon over-escaping trailing underscores in attribute names
# This fix modifies the attribute name processing to avoid escaping trailing underscores

def fix_attribute_name(attr_name):
    """
    Fix attribute name by removing unnecessary backslash escaping of trailing underscores.
    In reStructuredText, trailing underscores in attribute names don't need escaping.
    """
    # Remove backslash escaping from trailing underscores
    # Look for '\_' patterns at the end and replace with '_'
    if attr_name.endswith('\\_'):
        # Handle double backslash case
        return attr_name[:-2] + '_'
    elif attr_name.endswith('\_'):
        # Handle single backslash case
        return attr_name[:-2] + '_'
    return attr_name

# Usage in napoleon extension would be:
# clean_attr_name = fix_attribute_name(attr_name)
# then use clean_attr_name in formatting
