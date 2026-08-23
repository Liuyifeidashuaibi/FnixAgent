"""Word 文档编辑。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.business.word.editor import (
    create_docx,
    edit_docx,
    format_docx,
    register_word_tools,
)

__all__ = ["create_docx", "edit_docx", "format_docx", "register_word_tools"]
