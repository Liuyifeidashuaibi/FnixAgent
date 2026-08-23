# -*- coding: utf-8 -*-
"""为 work.py 的 runs 接口增加 API Key 脱敏（按内容替换，容忍 CRLF）。"""
from pathlib import Path

path = Path(r"E:\FNIX\FnixAgent\src\fnixagent\api\routers\work.py")
text = path.read_text(encoding="utf-8")
NL = "\r\n" if "\r\n" in text else "\n"

def block(s: str) -> str:
    return s.replace("\n", NL)

helper = block('''def _redact_run_meta(meta: dict) -> dict:
    """runs 对外响应脱敏：不把 API Key 回传给客户端。

    存储层保留完整凭据供 resume 使用；仅在 HTTP 响应出口遮罩。
    """
    import copy

    sanitized = copy.deepcopy(meta or {})
    llm = sanitized.get("llm")
    if isinstance(llm, dict):
        for key_field in ("api_key", "apiKey"):
            if llm.get(key_field):
                llm[key_field] = "***redacted***"
    return sanitized

''')

anchor1 = block('@router.get("/runs")\nasync def work_list_runs(')
assert helper not in text, "helper already present"
assert anchor1 in text, "anchor1 missing"
text = text.replace(anchor1, helper + anchor1, 1)

old2 = block('                "meta": meta,\n')
new2 = block('                "meta": _redact_run_meta(meta),\n')
assert text.count(old2) == 1, f"anchor2 count={text.count(old2)}"
text = text.replace(old2, new2, 1)

old3 = block('''    return {
        "ok": True,
        "run": run,
        "checkpoint": checkpoint,
        "events": events[-50:],  # 最近 50 条
        "events_total": len(events),
        "resumable": run["status"] in ("running", "failed", "interrupted"),
    }
''')
new3 = block('''    public_run = dict(run)
    if isinstance(public_run.get("meta"), dict):
        public_run["meta"] = _redact_run_meta(public_run["meta"])
    return {
        "ok": True,
        "run": public_run,
        "checkpoint": checkpoint,
        "events": events[-50:],  # 最近 50 条
        "events_total": len(events),
        "resumable": run["status"] in ("running", "failed", "interrupted"),
    }
''')
assert old3 in text, "anchor3 missing"
text = text.replace(old3, new3, 1)

path.write_text(text, encoding="utf-8")
print("patched ok")
