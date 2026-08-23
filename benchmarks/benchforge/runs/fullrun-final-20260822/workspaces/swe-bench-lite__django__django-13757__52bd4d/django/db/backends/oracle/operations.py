from django.db.backends.oracle.operations import DatabaseOperations

class DatabaseOperations(DatabaseOperations):
    def compile_json_key_transform_isnull(self, compiler, connection, lookup, lhs, rhs):
        # Fix for KeyTransformIsNull with isnull=True
        # Should only match when key doesn't exist, not when key exists with JSON null
        if rhs:
            # For isnull=True: check that key doesn't exist using JSON_EXISTS
            return "NOT JSON_EXISTS({lhs}, '$.{key}')".format(
                lhs=lhs,
                key=lookup.key_name
            )
        else:
            # For isnull=False: key exists and is not null
            return "JSON_EXISTS({lhs}, '$.{key}') AND JSON_VALUE({lhs}, '$.{key}') IS NOT NULL".format(
                lhs=lhs,
                key=lookup.key_name
            )
