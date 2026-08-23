# Django sqlmigrate command fix for issue #11039
# The output_transaction should consider both migration.atomic and connection.features.can_rollback_ddl

# Original code likely had:
# self.output_transaction = migration.atomic

# Fixed code should be:
# self.output_transaction = migration.atomic and connection.features.can_rollback_ddl
