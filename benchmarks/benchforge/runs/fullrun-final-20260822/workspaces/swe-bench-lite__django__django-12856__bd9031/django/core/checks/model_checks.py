def _check_unique_constraint_fields(app_configs=None, **kwargs):
    from django.core.checks import Error
    from django.db import models

    if app_configs is None:
        from django.apps import apps
        app_configs = apps.get_app_configs()

    errors = []
    for app_config in app_configs:
        for model in app_config.get_models():
            # Check UniqueConstraint fields
            for constraint in model._meta.constraints:
                if isinstance(constraint, models.UniqueConstraint):
                    # Check that all fields in the constraint exist on the model
                    for field_name in constraint.fields:
                        try:
                            model._meta.get_field(field_name)
                        except models.FieldDoesNotExist:
                            errors.append(
                                Error(
                                    f"UniqueConstraint refers to the non-existent field '{field_name}'.",
                                    obj=model,
                                    id='models.E043',
                                )
                            )
    return errors

# Add the check to the registry
from django.core.checks import register
register(_check_unique_constraint_fields, 'models')
