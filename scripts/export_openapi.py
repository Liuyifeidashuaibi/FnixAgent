"""导出 FastAPI OpenAPI schema 到 openapi.json(供前端 SDK 生成用)。"""
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
