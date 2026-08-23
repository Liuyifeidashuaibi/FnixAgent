import re
from astroid import nodes

from pylint.checkers import BaseChecker
from pylint.interfaces import IRawChecker


class TodoChecker(BaseChecker):
    """Check for TODO/FIXME/XXX comments."""

    __implements__ = IRawChecker

    name = "misc"
    msgs = {
        "W0511": (
            "%s %s",
            "fixme",
            "Used when a warning comment is seen.",
        ),
    }

    def process_module(self, node):
        """Process a module.

        :param node: astroid.scoped_nodes.Function
        """
        # Get the source code of the module
        try:
            with open(node.file, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            return

        # Compile the pattern for notes
        # Fix: Use negative lookarounds instead of word boundaries
        # to handle punctuation-only notes like ???
        if self.config.notes:
            # Escape notes and join with |
            escaped_notes = [re.escape(note) for note in self.config.notes]
            # Use (?<!\w) and (?!\w) instead of \b for better punctuation handling
            pattern = r"(?i)(?<!\\w)(" + "|".join(escaped_notes) + r")(?!\\w)"
            
            for lineno, line in enumerate(lines, 1):
                # Check for notes in comments
                if "#" in line:
                    comment_start = line.find("#")
                    comment = line[comment_start:].strip()
                    
                    # Match the pattern in the comment
                    match = re.search(pattern, comment)
                    if match:
                        note = match.group(1)
                        # Report the warning
                        self.add_message(
                            "fixme",
                            line=lineno,
                            args=(note, comment[match.end():].strip()),
                        )
