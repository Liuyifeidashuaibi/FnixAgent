# django/core/management/commands/shell.py
def handle(self, **options):
    # Execute the command and exit.
    if options['command']:
        exec(options['command'], {'__builtins__': __builtins__})
        return
