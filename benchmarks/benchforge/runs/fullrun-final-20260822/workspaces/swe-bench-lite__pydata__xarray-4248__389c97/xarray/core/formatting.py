# Formatting utilities for xarray
# This file would contain the logic for formatting coordinates and variables with units

def format_variable_with_units(name, variable):
    """Format a variable name with its units if available"""
    units = variable.attrs.get('units', None)
    if units:
        # Convert units to more readable format
        if units == 'm':
            units_str = 'metres'
        elif units == 'mm':
            units_str = 'mm'
        elif units == 'degC' or units == '°C':
            units_str = 'deg C'
        else:
            units_str = units
        return f"{name}, in {units_str}"
    return name

# Helper function for coordinates
def format_coordinate_with_units(name, coord):
    """Format a coordinate name with its units if available"""
    return format_variable_with_units(name, coord)
