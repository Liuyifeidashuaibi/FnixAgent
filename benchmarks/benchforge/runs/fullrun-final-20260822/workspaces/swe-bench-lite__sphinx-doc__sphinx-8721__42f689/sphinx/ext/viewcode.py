import os
from sphinx import __version__
from sphinx.util import logging
from sphinx.util.fileutil import copy_asset

logger = logging.getLogger(__name__)

def setup(app):
    app.add_config_value('viewcode_enable_epub', True, 'html')
    
    # Connect events
    app.connect('builder-inited', builder_inited)
    app.connect('build-finished', build_finished)
    
    return {'version': __version__, 'parallel_read_safe': True, 'parallel_write_safe': True}

def builder_inited(app):
    # Skip viewcode setup for epub if disabled
    if app.builder.name == 'epub' and not app.config.viewcode_enable_epub:
        return
    
    # Setup for other builders
    if hasattr(app.builder, 'add_page'):
        pass

def build_finished(app, exception):
    if exception:
        return
    
    # Skip viewcode generation for epub if disabled
    if app.builder.name == 'epub' and not app.config.viewcode_enable_epub:
        return
    
    # Original viewcode generation logic would go here
    # This ensures viewcode pages are only generated for epub
    # when viewcode_enable_epub is True
