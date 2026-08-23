import sys
from pylint.config.exceptions import _UnrecognizedOptionError


class PylintRun:
    def __init__(self, argv=None):
        try:
            args = _config_initialization(
                argv or sys.argv[1:],
                reporter=self.reporter,
                exit=False,
            )
        except _UnrecognizedOptionError as exc:
            # Handle unrecognized options gracefully
            print(f"pylint: error: unrecognized arguments: {' '.join(exc.options)}")
            print("usage: pylint [options] [files or directories]")
            print("Try 'pylint --help' for more information.")
            sys.exit(2)
        # The rest of the original __init__ method would continue here...
