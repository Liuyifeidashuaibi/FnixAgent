from django.contrib.admin.options import ModelAdmin
from django.contrib.admin.views.main import ChangeList
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import six
from django.utils.safestring import mark_safe
from django.utils.text import capfirst
from django.utils.translation import gettext as _


class AdminSite(object):
    """
    An AdminSite object encapsulates an instance of the Django admin application,
    ready to be hooked in to your URLconf. Models are registered with the AdminSite
    using the register() method, and the get_urls() method can be used to obtain
    the URL patterns for the admin application.
    """

    def __init__(self, name='admin'):
        self.name = name
        self._registry = {}  # model_class -> admin_class
        self._actions = {'delete_selected': DeleteSelectedAction}
        self._global_actions = self._actions.copy()

    def build_app_dict(self, request):
        """
        Build the app dictionary. Makes the app_list context variable available
        with model classes included in the context.
        """
        app_dict = {}
        user = request.user

        for model, model_admin in self._registry.items():
            app_label = model._meta.app_label
            has_module_perms = user.has_module_perms(app_label)

            if has_module_perms:
                perms = model_admin.get_model_perms(request)

                # Check whether user has any perm for this module.
                # If so, add the module to the app_dict.
                if True in perms.values():
                    info = (app_label, model._meta.model_name)
                    model_dict = {
                        'name': capfirst(model._meta.verbose_name_plural),
                        'object_name': model._meta.object_name,
                        'perms': perms,
                        'model': model,  # Include the actual model class
                    }
                    if perms.get('change') or perms.get('add'):
                        model_dict['admin_url'] = reverse('admin:%s_%s_changelist' % info, current_app=self.name)
                    if perms.get('add'):
                        model_dict['add_url'] = reverse('admin:%s_%s_add' % info, current_app=self.name)
                    if app_label in app_dict:
                        app_dict[app_label]['models'].append(model_dict)
                    else:
                        app_dict[app_label] = {
                            'name': apps.get_app_config(app_label).verbose_name,
                            'app_url': reverse('admin:app_list', kwargs={'app_label': app_label}, current_app=self.name),
                            'has_module_perms': has_module_perms,
                            'models': [model_dict],
                        }

        return list(six.itervalues(app_dict))

    def index(self, request, extra_context=None):
        """
        Display the main admin index page, which lists all of the installed
        apps that have been registered.
        """
        app_list = self.build_app_dict(request)

        context = {
            'title': _('Site administration'),
            'app_list': app_list,
            'user': request.user,
        }
        context.update(extra_context or {})
        return TemplateResponse(request, self.index_template or 'admin/index.html', context)

    def app_index(self, request, app_label, extra_context=None):
        """
        Display a given app's index page. The app's models are displayed
        in alphabetical order.
        """
        user = request.user
        app_dict = self.build_app_dict(request)

        # Find the app and display its models
        for app in app_dict:
            if app['app_label'] == app_label:
                break
        else:
            raise Http404(_('The requested admin page does not exist.'))

        # Sort models alphabetically
        app['models'].sort(key=lambda x: x['name'])

        context = {
            'title': _('%(app)s administration') % {'app': app['name']},
            'app_list': [app],
            'app_label': app_label,
            'user': request.user,
        }
        context.update(extra_context or {})
        return TemplateResponse(request, self.app_index_template or 'admin/app_index.html', context)
