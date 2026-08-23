from flask import Flask

class Blueprint:
    def __init__(self, name, import_name, static_folder=None, static_url_path=None, template_folder=None, url_prefix=None, subdomain=None, name_prefix='', **options):
        if '.' in name:
            raise ValueError('Blueprint names cannot contain dots')
        self.name = name
        self.import_name = import_name
        self.static_folder = static_folder
        self.static_url_path = static_url_path
        self.template_folder = template_folder
        self.url_prefix = url_prefix
        self.subdomain = subdomain
        self.name_prefix = name_prefix
        self.options = options
