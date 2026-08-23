class Dataset:
    def __repr__(self):
        # Get dimensions
        dims_str = f"Dimensions: ({', '.join(f'{k}: {v}' for k, v in self.dims.items())})"
        
        # Format coordinates
        coords_lines = ['Coordinates:']
        for name, coord in self.coords.items():
            # Add units if present
            units = coord.attrs.get('units')
            if units:
                # Handle common unit abbreviations
                if units == 'm':
                    units_str = 'metres'
                elif units == 'mm':
                    units_str = 'mm'
                elif units in ['degC', '°C', 'celsius', 'C']:
                    units_str = 'deg C'
                elif units == 's':
                    units_str = 'seconds'
                else:
                    units_str = units
                coord_name = f"{name}, in {units_str}"
            else:
                coord_name = name
            coords_lines.append(f"  * {coord_name} ({name}) {coord.dtype} ...")
        
        # Format data variables
        vars_lines = ['Data variables:']
        for name, var in self.data_vars.items():
            units = var.attrs.get('units')
            if units:
                if units == 'm':
                    units_str = 'metres'
                elif units == 'mm':
                    units_str = 'mm'
                elif units in ['degC', '°C', 'celsius', 'C']:
                    units_str = 'deg C'
                elif units == 's':
                    units_str = 'seconds'
                else:
                    units_str = units
                var_name = f"{name}, in {units_str}"
            else:
                var_name = name
            vars_lines.append(f"    {var_name} ({', '.join(var.dims)}) {var.dtype} ...")
        
        return '\n'.join([f"<xarray.{self.__class__.__name__}>", dims_str] + coords_lines + vars_lines)
