# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

"fnixagent kernel package."

import datetime as _datetime

# Python 3.11+ compatibility: inject UTC for Python 3.10
if not hasattr(_datetime, "UTC"):
    _datetime.UTC = _datetime.UTC

__version__ = "1.0.0"
