diff --git a/django/db/models/fields/__init__.py b/django/db/models/fields/__init__.py
index abc123..def456 100644
--- a/django/db/models/fields/__init__.py
+++ b/django/db/models/fields/__init__.py
@@ -123,6 +123,15 @@ class Field:
         # Handle enum defaults
         if hasattr(default, '__members__') and hasattr(default, '__class__'):
             # This is an enum member
+            if hasattr(default, 'name') and hasattr(default, 'value'):
+                # Use enum name instead of value for migration stability
+                # This prevents issues with translated enum values
+                import enum
+                if isinstance(default, enum.Enum):
+                    # Serialize as EnumClass['NAME'] instead of EnumClass(value)
+                    args = [f"{default.__class__.__name__}['{default.name}']"]
+                    kwargs.pop('default', None)
+                    return name, path, args, kwargs
         # Original deconstruction logic
         return name, path, args, kwargs