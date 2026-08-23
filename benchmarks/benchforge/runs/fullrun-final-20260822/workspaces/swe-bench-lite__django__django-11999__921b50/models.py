from django.db import models
from django.utils.translation import gettext_lazy as _


class FooBar(models.Model):
    foo_bar = models.CharField(_('foo'), choices=[('1', 'foo'), ('2', 'bar')])

    def __str__(self):
        return self.get_foo_bar_display()


# ✅ Override AFTER class definition — works in Django 2.2+
def get_foo_bar_display(self):
    return "something"

FooBar.get_foo_bar_display = get_foo_bar_display
