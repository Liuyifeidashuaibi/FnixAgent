import os
from django.core.exceptions import ObjectDoesNotExist
from django.db import ProgrammingError, OperationalError
from django.db.backends.base.base import BaseDatabaseWrapper


class BaseDatabaseCreation:
    def __init__(self, connection):
        self.connection = connection

    def get_objects(self):
        """
        Returns an iterator over the queryset for all models.
        """
        from django.core.exceptions import ObjectDoesNotExist
        from django.db import ProgrammingError, OperationalError

        for model in self.connection.introspection.installed_models(
            self.connection.introspection.table_names(self.connection.cursor())
        ):
            if model._meta.proxy or model._meta.swapped:
                continue
            queryset = model._base_manager.using(self.connection.alias).order_by(model._meta.pk.name)
            try:
                yield from queryset.iterator()
            except (ProgrammingError, OperationalError):
                # The table doesn't exist (e.g., when MIGRATE=False and app has no migrations).
                continue
