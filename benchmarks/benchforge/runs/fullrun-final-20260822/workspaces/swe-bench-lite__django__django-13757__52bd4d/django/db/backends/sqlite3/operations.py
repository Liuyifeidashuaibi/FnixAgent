from django.db.backends.sqlite3.operations import DatabaseOperations

class DatabaseOperations(DatabaseOperations):
    def compile_json_key_transform_isnull(self, compiler, connection, lookup, lhs, rhs):
        # Fix for KeyTransformIsNull with isnull=True
        # Should only match when key doesn't exist, not when key exists with JSON null
        if rhs:
            # For isnull=True: check that key doesn't exist using json_type
            return "json_type({lhs}, '$.{key}') IS NULL".format(
                lhs=lhs,
                key=lookup.key_name
            )
        else:
            # For isnull=False: use original logic (key exists and is not null)
            return "json_type({lhs}, '$.{key}') IS NOT NULL AND json_extract({lhs}, '$.{key}') IS NOT NULL".format(
                lhs=lhs,
                key=lookup.key_name
            )
