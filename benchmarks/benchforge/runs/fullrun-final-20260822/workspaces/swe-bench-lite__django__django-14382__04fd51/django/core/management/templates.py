"""
Templates for Django management commands.
"""

import os
from django.core.management.base import CommandError, BaseCommand
from django.core.management.utils import get_random_secret_key
from django.template.utils import get_app_template_dirs
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Creates a Django app directory structure for the given app name in "
        "the specified directory."
    )
    missing_args_message = "You must provide an application name."

    def add_arguments(self, parser):
        parser.add_argument('name', help='The name of the application or project.')
        parser.add_argument('directory', nargs='?', help='The directory to create the app in.')

    def handle(self, *args, **options):
        app_name = options['name']
        target = options.get('directory')

        # Check that the app_name is a valid Python identifier.
        self.validate_name(app_name, 'app')

        if target:
            # Check that the target directory is a valid Python identifier.
            self.validate_name(os.path.basename(target.rstrip(os.sep)), 'directory')
            
            # Create the directory if it doesn't exist.
            if not os.path.exists(target):
                os.makedirs(target)

            # Use the target directory as the root for the app.
            target = os.path.abspath(target)
        else:
            target = os.getcwd()

        # Create the app directory.
        app_dir = os.path.join(target, app_name)
        if not os.path.exists(app_dir):
            os.makedirs(app_dir)

        # Create the app's __init__.py file.
        init_path = os.path.join(app_dir, '__init__.py')
        with open(init_path, 'w') as f:
            f.write('"""' + app_name + '"""\n')

        # Create the app's models.py file.
        models_path = os.path.join(app_dir, 'models.py')
        with open(models_path, 'w') as f:
            f.write('from django.db import models\n\n\n' +
                    '# Create your models here.\n')

        # Create the app's views.py file.
        views_path = os.path.join(app_dir, 'views.py')
        with open(views_path, 'w') as f:
            f.write('from django.shortcuts import render\n\n\n' +
                    '# Create your views here.\n')

        # Create the app's urls.py file.
        urls_path = os.path.join(app_dir, 'urls.py')
        with open(urls_path, 'w') as f:
            f.write('from django.urls import path\n\n\n' +
                    '# urlpatterns = [\n' +
                    '#     path(\'\', views.home, name=\'home\'),\n' +
                    '# ]\n')

        # Create the app's admin.py file.
        admin_path = os.path.join(app_dir, 'admin.py')
        with open(admin_path, 'w') as f:
            f.write('from django.contrib import admin\n\n\n' +
                    '# Register your models here.\n')

        # Create the app's apps.py file.
        apps_path = os.path.join(app_dir, 'apps.py')
        with open(apps_path, 'w') as f:
            f.write('from django.apps import AppConfig\n\n\n' +
                    'class ' + app_name.capitalize() + 'Config(AppConfig):\n' +
                    '    default_auto_field = \'django.db.models.BigAutoField\'\n' +
                    '    name = \'' + app_name + '\'\n')

        # Create the app's tests.py file.
        tests_path = os.path.join(app_dir, 'tests.py')
        with open(tests_path, 'w') as f:
            f.write('from django.test import TestCase\n\n\n' +
                    '# Create your tests here.\n')

        # Create the app's migrations directory.
        migrations_dir = os.path.join(app_dir, 'migrations')
        if not os.path.exists(migrations_dir):
            os.makedirs(migrations_dir)

        # Create the migrations directory's __init__.py file.
        migrations_init_path = os.path.join(migrations_dir, '__init__.py')
        with open(migrations_init_path, 'w') as f:
            f.write('"""\n' +
                    'Migrations for the ' + app_name + ' app.\n' +
                    '"""\n')

        self.stdout.write(self.style.SUCCESS(f'App {app_name} created successfully.'))