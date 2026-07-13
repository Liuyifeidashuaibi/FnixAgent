"""导出 FastAPI OpenAPI schema 到 openapi.json(供前端 SDK 生成用)。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from fnixagent.main import app

schema = app.openapi()
out = Path(__file__).parent.parent / "openapi.json"
out.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OpenAPI {schema['openapi']} — {len(schema.get('paths', {}))} paths → {out}")
