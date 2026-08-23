from django.core.exceptions import FieldError


class IsNull(Lookup):
    lookup_name = 'isnull'

    def __init__(self, lhs, rhs):
        # Validate that rhs is boolean
        if not isinstance(rhs, bool):
            raise ValueError("The __isnull lookup only accepts True or False values.")
        super().__init__(lhs, rhs)

    def as_sql(self, compiler, connection):
        lhs_sql, params = self.process_lhs(compiler, connection)
        rhs_sql, _ = self.process_rhs(compiler, connection)
        return '%s IS %sNULL' % (lhs_sql, '' if self.rhs else 'NOT '), params
