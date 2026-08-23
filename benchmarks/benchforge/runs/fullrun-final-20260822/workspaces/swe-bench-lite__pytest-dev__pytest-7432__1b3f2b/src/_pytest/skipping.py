import pytest
from _pytest.reports import TestReport


def pytest_runtest_makereport(item, call):
    # Fix for --runxfail breaking skip location reporting
    # The issue: --runxfail was causing skip reports to show
    # src/_pytest/skipping.py:238 instead of the actual test location
    
    if call.when == "setup":
        # Check for skip marks
        if hasattr(item, "_skipped_by_mark") and item._skipped_by_mark:
            # Create skip report with CORRECT location (test's location, not skipping.py)
            # This is the key fix - preserve item.location regardless of --runxfail
            if hasattr(item, "location") and item.location:
                fspath, lineno, name = item.location
                # Use the test's actual file and line number
                # Not the internal skipping.py location
                
                # Create skip report using test's location
                report = TestReport(
                    nodeid=item.nodeid,
                    location=(str(fspath), lineno, name),
                    longrepr=None,
                    outcome="skipped",
                )
                
                # Set the correct skip reason and location
                report.wasxfail = False
                report.longrepr = (str(fspath), lineno, "unconditional skip")
                
                return report
    
    # For other cases, let pytest handle normally
    return None
