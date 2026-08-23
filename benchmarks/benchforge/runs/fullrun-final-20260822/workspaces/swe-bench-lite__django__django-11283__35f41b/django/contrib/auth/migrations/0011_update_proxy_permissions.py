from django.db import migrations


def update_proxy_permissions(apps, schema_editor):
    """
    Update proxy model permissions to use the content type of the concrete model.
    
    This migration fixes the issue where proxy models had permissions created with
    their own content type instead of the concrete model's content type.
    """
    ContentType = apps.get_model("contenttypes.ContentType")
    Permission = apps.get_model("auth.Permission")
    
    # Get all models from all installed apps
    from django.apps import apps as global_apps
    
    for app_config in global_apps.get_app_configs():
        for model in app_config.get_models():
            if model._meta.proxy:
                try:
                    # Get content types
                    proxy_content_type = ContentType.objects.get_for_model(model, for_concrete_model=False)
                    concrete_content_type = ContentType.objects.get_for_model(model._meta.concrete_model, for_concrete_model=True)
                    
                    # Get permissions for this proxy model
                    proxy_permissions = Permission.objects.filter(
                        content_type=proxy_content_type
                    )
                    
                    # For each permission, ensure it exists for the concrete model
                    for perm in proxy_permissions:
                        # Try to get existing permission for concrete model
                        try:
                            concrete_perm = Permission.objects.get(
                                content_type=concrete_content_type,
                                codename=perm.codename
                            )
                            # If it exists, we don't need to do anything
                            # Just delete the proxy permission
                            perm.delete()
                        except Permission.DoesNotExist:
                            # Create the permission for concrete model
                            Permission.objects.create(
                                name=perm.name,
                                content_type=concrete_content_type,
                                codename=perm.codename
                            )
                            # Delete the proxy permission
                            perm.delete()
                except Exception:
                    # Skip models that cause issues
                    pass


def reverse_update_proxy_permissions(apps, schema_editor):
    """
    Reverse the proxy permissions update.
    This is a no-op since we can't reliably restore the original state.
    """
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('auth', '0010_alter_group_name_max_length'),
    ]

    operations = [
        migrations.RunPython(update_proxy_permissions, reverse_update_proxy_permissions),
    ]