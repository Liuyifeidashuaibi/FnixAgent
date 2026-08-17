"""论文文献检索。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

from fnixagent.business.search.arxiv import (
    register_search_tools,
    search_arxiv,
    search_paper,
    search_semantic_scholar,
)

__all__ = ["register_search_tools", "search_arxiv", "search_paper", "search_semantic_scholar"]
