from django.db import models

class Parent(models.Model):
    class Meta:
        ordering = ["-pk"]

class Child(Parent):
    pass

# This test demonstrates the fix for Django issue #12470
# The Child.objects.all() query should order by pk DESC, not ASC
# The fix ensures that "-pk" in Parent.Meta.ordering is correctly translated
# to the appropriate field name with DESC ordering in SQL queries
