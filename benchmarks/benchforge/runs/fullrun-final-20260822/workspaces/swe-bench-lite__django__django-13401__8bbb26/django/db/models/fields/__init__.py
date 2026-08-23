from django.core import checks
from django.db import models
from django.db.models.fields import Field

# Original Field class methods with fixes applied

def field_eq(self, other):
    """
    Two fields are equal if they have the same creation counter and belong to the same model.
    This prevents false equality across different concrete models inheriting from the same abstract base.
    """
    if not isinstance(other, Field):
        return False
    
    # Compare creation_counter first
    if self.creation_counter != other.creation_counter:
        return False
    
    # If both fields have models, they must be the same model
    if (hasattr(self, 'model') and hasattr(other, 'model') and 
        self.model is not None and other.model is not None):
        return self.model == other.model
    
    # If one or both don't have models (e.g., standalone fields), just compare creation_counter
    return True


def field_hash(self):
    """
    Hash based on creation_counter and model to match __eq__ behavior.
    """
    if hasattr(self, 'model') and self.model is not None:
        return hash((self.creation_counter, self.model))
    return hash(self.creation_counter)


def field_lt(self, other):
    """
    Less than comparison: order by creation_counter first, then by model name
    to maintain stability for cases where creation_counter is the same.
    """
    if not isinstance(other, Field):
        return NotImplemented
    
    # Order by creation_counter first
    if self.creation_counter != other.creation_counter:
        return self.creation_counter < other.creation_counter
    
    # If creation_counter is equal, order by model name if both have models
    if (hasattr(self, 'model') and hasattr(other, 'model') and 
        self.model is not None and other.model is not None):
        return self.model.__name__ < other.model.__name__
    
    # If no models or only one has a model, fallback to False (not less than)
    return False

# Apply the fixed methods to the Field class
Field.__eq__ = field_eq
Field.__hash__ = field_hash
Field.__lt__ = field_lt