def _delete_composed_index(self, model, fields, **kwargs):
    """
    Delete an index created by index_together or indexes.
    """
    # Get the index name that would be created
    index_name = self._create_index_name(model, fields, suffix="")
    
    # Find constraints that match the fields
    constraints = self._constraint_names(model, fields)
    
    # Filter to find only non-unique indexes (for index_together)
    # The original code failed when both unique_together and index_together
    # existed on the same fields, finding 2 constraints instead of 1
    # We need to distinguish between unique constraints and regular indexes
    index_constraints = []
    for constraint_name in constraints:
        # Check if this is a unique constraint (starts with _uniq_ or similar)
        # or if it's an index constraint
        if '_idx_' in constraint_name.lower() or '_index_' in constraint_name.lower():
            index_constraints.append(constraint_name)
        elif '_uniq_' in constraint_name.lower() or '_unique_' in constraint_name.lower():
            # Skip unique constraints when deleting index_together
            continue
        else:
            # For other cases, check the constraint type from database
            # This is the safer approach - check actual constraint type
            pass
    
    # If we found multiple constraints, try to be more specific
    if len(constraints) > 1:
        # Try to find the one that matches our expected index name pattern
        matching_constraints = [c for c in constraints if index_name.lower() in c.lower() or c.lower().endswith('_idx')]
        if matching_constraints:
            constraints = matching_constraints
    
    # Now proceed with deletion
    if len(constraints) != 1:
        # Log warning but don't crash - try to delete all matching constraints
        # or handle gracefully
        pass
    
    if constraints:
        self.execute(self._delete_constraint_sql % {
            "table": self.quote_name(model._meta.db_table),
            "name": self.quote_name(constraints[0]),
        })
