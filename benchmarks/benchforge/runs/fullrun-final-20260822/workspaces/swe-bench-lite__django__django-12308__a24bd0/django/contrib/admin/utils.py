from django.db import models
from django.db.models import JSONField


def display_for_field(value, field, empty_value_display=''):
    from django.contrib.admin.utils import _get_separator
    
    # Handle JSONField specially for readonly display
    if isinstance(field, JSONField):
        # Use prepare_value to get proper JSON string representation
        # This handles InvalidJSONInput cases properly
        if hasattr(field, 'prepare_value'):
            return field.prepare_value(value)
    
    # Original display logic for other field types
    if value is None:
        return empty_value_display
    
    if hasattr(field, 'flatchoices') and field.flatchoices:
        for choice_id, choice_display in field.flatchoices:
            if value == choice_id:
                return str(choice_display)
    
    if isinstance(field, models.BooleanField):
        return {True: 'Yes', False: 'No', '': 'Unknown'}.get(value, value)
    
    if isinstance(field, models.DateTimeField):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    
    if isinstance(field, models.DateField):
        return value.strftime('%Y-%m-%d')
    
    if isinstance(field, models.TimeField):
        return value.strftime('%H:%M:%S')
    
    if isinstance(field, models.DecimalField):
        return str(value)
    
    if isinstance(field, models.FloatField):
        return str(value)
    
    if isinstance(field, models.IntegerField):
        return str(value)
    
    if isinstance(field, models.CharField):
        return str(value)
    
    if isinstance(field, models.TextField):
        return str(value)
    
    if isinstance(field, models.EmailField):
        return str(value)
    
    if isinstance(field, models.URLField):
        return str(value)
    
    if isinstance(field, models.FileField):
        return str(value)
    
    if isinstance(field, models.ImageField):
        return str(value)
    
    if isinstance(field, models.ForeignKey):
        return str(value)
    
    if isinstance(field, models.ManyToManyField):
        return str(value)
    
    # Default fallback
    return str(value)
