'''Fix for Django 2.2+ E028 error: multiple models using same db_table

Solution: Make db_table names unique across all apps by adding app prefixes.

Before:
class ModelName(models.Model):
    class Meta:
        db_table = 'table_name'

After:
class ModelName(models.Model):
    class Meta:
        db_table = 'base_table_name'  # for base app
        # or 'app2_table_name' for app2

Also ensure database routers are properly configured to route models
to their respective databases.
'''

# Example database router configuration

class DatabaseRouter:
    '''
    A router to control database operations on models
    '''
    
    def db_for_read(self, model, **hints):
        """Suggests the database that should be used for read operations."""
        if model._meta.app_label == 'base':
            return 'central_db'
        elif model._meta.app_label == 'app2':
            return 'app2_db'
        return None
    
    def db_for_write(self, model, **hints):
        """Suggests the database that should be used for write operations."""
        if model._meta.app_label == 'base':
            return 'central_db'
        elif model._meta.app_label == 'app2':
            return 'app2_db'
        return None
    
    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations if both objects are in the same database."""
        db_set = {'central_db', 'app2_db'}
        if obj1._state.db in db_set and obj2._state.db in db_set:
            return True
        return None
    
    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Make sure the auth app only appears in the 'auth_db' database."""
        if app_label == 'base':
            return db == 'central_db'
        elif app_label == 'app2':
            return db == 'app2_db'
        return None