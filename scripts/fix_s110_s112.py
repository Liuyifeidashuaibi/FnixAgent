"""
Batch fix S110 (except-pass) and S112 (except-continue) violations.
v3: Fixed logger insertion to only use module-level imports.
Strategy:
1. Process violations bottom-to-top (no line shift above)
2. Add logger AFTER all violations fixed (no line shift during processing)
3. Logger insertion only considers indentation==0 imports
"""

import json
import re
import subprocess
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path("E:/FNIX/FnixAgent")

# 1. Get all violations from ruff
result = subprocess.run(
    ["python", "-m", "ruff", "check", "--select", "S110,S112", "--output-format", "json", "src/"],
    capture_output=True,
    text=True,
    cwd=str(PROJECT_ROOT),
)
violations = json.loads(result.stdout)
print(f"Total violations: {len(violations)}")

# Group by file
by_file = defaultdict(list)
for v in violations:
    by_file[v["filename"]].append(v)

print(f"Files to process: {len(by_file)}")

LOGGER_PATTERNS = [
    r"_logger\s*=\s*logging\.getLogger",
    r"logger\s*=\s*logging\.getLogger",
    r"_logger\s*=\s*log\.getLogger",
    r"logger\s*=\s*log\.getLogger",
]


def has_logger(lines):
    for line in lines:
        for pat in LOGGER_PATTERNS:
            if re.search(pat, line):
                return True
    return False


def find_logger_name(lines):
    for line in lines:
        for name in ["_logger", "logger"]:
            if re.search(rf"{name}\s*=\s*(logging|log)\.getLogger", line):
                return name
    return None


def fix_violation(lines, row, code):
    """Fix a single S110/S112 violation. row is 1-based, pointing to except line."""
    idx = row - 1
    if idx >= len(lines):
        return lines, False, f"Row {row} out of range"

    except_line = lines[idx]
    indent = len(except_line) - len(except_line.lstrip())
    body_indent = " " * (indent + 4)

    # Case 1: inline except: pass/continue (with optional trailing comment)
    inline_match = re.match(r"^(\s*except.*?:\s*)(pass|continue)(\s+#.*)?\s*$", except_line)
    if inline_match:
        prefix = inline_match.group(1)
        action = inline_match.group(2)
        comment = inline_match.group(3) or ""
        if action == "pass":
            lines[idx] = f"{prefix}_logger.debug('Unhandled exception', exc_info=True){comment}\n"
        else:
            lines[idx] = (
                f"{prefix}_logger.debug('Unhandled exception', exc_info=True); continue{comment}\n"
            )
        return lines, True, f"Inline {action} at line {row}"

    # Case 2: pass/continue on next line (with optional trailing comment)
    if idx + 1 < len(lines):
        next_line = lines[idx + 1]
        next_stripped = next_line.strip()
        next_indent = len(next_line) - len(next_line.lstrip())

        if next_indent > indent:
            m = re.match(r"^(pass|continue)(\s+#.*)?$", next_stripped)
            if m:
                action = m.group(1)
                comment = m.group(2) or ""
                if action == "pass":
                    lines[idx + 1] = (
                        f"{body_indent}_logger.debug('Unhandled exception', exc_info=True){comment}\n"
                    )
                else:
                    lines[idx + 1] = (
                        f"{body_indent}_logger.debug('Unhandled exception', exc_info=True)\n{body_indent}continue{comment}\n"
                    )
                return lines, True, f"{action} at line {row + 1}"

    # Case 3: multi-line except (pass/continue deeper in block)
    for i in range(idx + 1, min(idx + 8, len(lines))):
        line = lines[i]
        stripped = line.strip()
        line_indent = len(line) - len(line.lstrip())

        if line_indent <= indent:
            break

        m = re.match(r"^(pass|continue)(\s+#.*)?$", stripped)
        if m:
            action = m.group(1)
            comment = m.group(2) or ""
            if action == "pass":
                lines[i] = (
                    f"{body_indent}_logger.debug('Unhandled exception', exc_info=True){comment}\n"
                )
            else:
                lines[i] = (
                    f"{body_indent}_logger.debug('Unhandled exception', exc_info=True)\n{body_indent}continue{comment}\n"
                )
            return lines, True, f"nested {action} at line {i + 1}"

    return lines, False, f"Could not find pass/continue near line {row}"


def add_logger_to_file(lines):
    """Add logging import and _logger definition at module level."""
    if has_logger(lines):
        return lines, find_logger_name(lines), 0

    # Find last MODULE-LEVEL import (indentation == 0)
    last_import = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Only consider lines at module level (no leading whitespace)
        if line and not line[0].isspace():
            if stripped.startswith("import ") or stripped.startswith("from "):
                if stripped.endswith("("):
                    # Multi-line import
                    for j in range(i + 1, len(lines)):
                        if ")" in lines[j]:
                            last_import = j
                            break
                else:
                    last_import = i

    insert_idx = last_import + 1 if last_import >= 0 else 0

    # Add blank line before logger if needed
    need_blank = insert_idx > 0 and lines[insert_idx - 1].strip() != ""

    new_lines = []
    if need_blank:
        new_lines.append("\n")
    if not any("import logging" in line or "from logging" in line for line in lines):
        new_lines.append("import logging\n")
        new_lines.append("\n")
    new_lines.append("_logger = logging.getLogger(__name__)\n")
    new_lines.append("\n")

    result_lines = lines[:insert_idx] + new_lines + lines[insert_idx:]
    return result_lines, "_logger", len(new_lines)


# Process each file
total_fixed = 0
total_failed = 0
failed_details = []

for filepath_str, file_violations in sorted(by_file.items()):
    filepath = Path(filepath_str)
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        # Preserve original line endings
        has_trailing_newline = content.endswith("\n")
        lines = content.split("\n")
        lines = [line + "\n" for line in lines[:-1]] + [lines[-1]]

        # Sort violations by row DESCENDING
        file_violations.sort(key=lambda v: v["location"]["row"], reverse=True)

        file_fixed = 0
        file_failed = 0

        for v in file_violations:
            row = v["location"]["row"]
            code = v["code"]
            lines, success, desc = fix_violation(lines, row, code)
            if success:
                file_fixed += 1
            else:
                file_failed += 1
                failed_details.append(f"{filepath_str}:{row} - {desc}")

        # Add logger AFTER all violations fixed
        lines, logger_name, inserted = add_logger_to_file(lines)

        # Write back
        new_content = "".join(lines)
        if not has_trailing_newline:
            new_content = new_content.rstrip("\n")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

        total_fixed += file_fixed
        total_failed += file_failed

        rel_path = filepath_str.replace(str(PROJECT_ROOT) + "\\", "").replace("\\", "/")
        if file_fixed > 0 or file_failed > 0:
            log_info = f" (+logger)" if inserted > 0 else ""
            print(f"  {rel_path}: {file_fixed} fixed, {file_failed} failed{log_info}")

    except Exception as e:
        print(f"  ERROR processing {filepath_str}: {e}")
        total_failed += len(file_violations)

print(f"\n=== SUMMARY ===")
print(f"Total fixed: {total_fixed}/{len(violations)}")
print(f"Total failed: {total_failed}")
if failed_details:
    print(f"\nFailed details:")
    for d in failed_details:
        print(f"  {d}")
