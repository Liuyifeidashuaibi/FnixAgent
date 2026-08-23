"""导出 FastAPI OpenAPI schema 到 openapi.json(供前端 SDK 生成用)。"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fnixagent.main import app

# app 可能被 CapabilityMiddleware 包装, 取内部 FastAPI 实例
fastapi_app = getattr(app, "app", app)
if not hasattr(fastapi_app, "openapi"):
    # 再尝试一层解包
    fastapi_app = getattr(fastapi_app, "app", fastapi_app)

schema = fastapi_app.openapi()
out = Path(__file__).parent.parent / "openapi.json"
out.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OpenAPI {schema['openapi']} — {len(schema.get('paths', {}))} paths → {out}")
