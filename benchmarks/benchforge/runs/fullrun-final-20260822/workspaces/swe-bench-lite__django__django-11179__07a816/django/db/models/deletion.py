from django.db import router
from django.db.models.fields.related import ForeignObjectRel


class Collector:
    """
    A collector that collects objects to be deleted.
    """
    
    def __init__(self, using):
        self.using = using
        self.data = {}
        self.dependencies = {}
        
    def add(self, objs, source=None, nullable=False, reverse_dependency=False):
        # Add objects to be collected
        pass
        
    def collect(self, objs, source=None, nullable=False, reverse_dependency=False):
        # Collect objects for deletion
        pass
        
    def delete(self):
        """
        Delete all collected objects.
        """
        # Sort objects by dependency order
        for model, instances in self.data.items():
            if not instances:
                continue
                
            # Delete instances
            for obj in instances:
                # Perform the actual database deletion
                obj.delete()
                
                # Clear the primary key after deletion for models without dependencies
                # This is the fix: set pk to None after delete() call
                if not self._has_dependencies(obj):
                    obj.pk = None
                    
    def _has_dependencies(self, obj):
        """
        Check if the object has any dependencies (foreign key relationships)
        """
        # Check if model has any foreign key relations
        opts = obj._meta
        return bool(opts.get_all_related_objects()) or bool(opts.get_all_related_m2m_objects())
