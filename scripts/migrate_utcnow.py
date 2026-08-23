"""Batch migrate datetime.utcnow() -> datetime.now(UTC) across src/fnixagent/."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "fnixagent"

changed_files = []

for py in SRC.rglob("*.py"):
    if "__pycache__" in py.name:
        continue
    text = py.read_text(encoding="utf-8")
    if "datetime.utcnow()" not in text:
        continue

    original = text
    count = text.count("datetime.utcnow()")
    text = text.replace("datetime.utcnow()", "datetime.now(UTC)")

    # Ensure UTC is imported
    # Pattern: from datetime import datetime  ->  from datetime import datetime, UTC
    # Pattern: from datetime import datetime, timedelta  ->  from datetime import datetime, timedelta, UTC
    # Skip if UTC already in the import line
    lines = text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("from datetime import"):
            if "UTC" not in line:
                lines[i] = line.rstrip() + ", UTC"
                break
    else:
        # No "from datetime import" found — check for "import datetime"
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if stripped == "import datetime" or stripped.startswith("import datetime as"):
                # Replace with from datetime import datetime, UTC
                lines[i] = "from datetime import datetime, UTC"
                break
        else:
            print(f"  WARNING: {py.relative_to(ROOT)} — could not find datetime import to patch")
            # Still write the file, the user will need to add the import manually

    text = "\n".join(lines)

    if text != original:
        py.write_text(text, encoding="utf-8")
        changed_files.append((py.relative_to(ROOT), count))
        print(f"  {py.relative_to(ROOT)}: {count} replacements")

print(f"\nTotal: {len(changed_files)} files, {sum(c for _, c in changed_files)} replacements")
