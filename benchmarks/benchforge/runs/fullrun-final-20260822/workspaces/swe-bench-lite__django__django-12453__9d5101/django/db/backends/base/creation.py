import time
from django.apps import apps
from django.conf import settings
from django.core import serializers
from django.db import router, transaction
from django.utils.six import StringIO
from django.utils.six.moves import input


class BaseDatabaseCreation(object):
    def deserialize_db_from_string(self, data):
        """
        Load serialized database data into the database.

        This method is used by TransactionTestCase when serialized_rollback=True.
        """
        data = StringIO(data)
        with transaction.atomic(using=self.connection.alias):
            for obj in serializers.deserialize("json", data, using=self.connection.alias):
                obj.save()

    def _get_database_display_str(self, verbosity, database_name):
        """
        Returns a display string for the database.
        """
        return database_name
