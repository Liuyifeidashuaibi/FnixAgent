# -*- coding: utf-8 -*-
"""workbuddy loader 尾部追加硬去重（同名任务追加序号，绝不丢弃任务）。"""
from pathlib import Path

path = Path(r"E:\FNIX\FnixAgent\src\fnixagent\bench\datasets.py")
text = path.read_text(encoding="utf-8")
NL = "\r\n" if "\r\n" in text else "\n"

def block(s: str) -> str:
    return s.replace("\n", NL)

old = block('''    if not tasks:
        raise DatasetFetchError(
            "workbuddy-bench 无可用任务: " + ("; ".join(missing) or "缺文件"))
''')
new = block('''    # 硬去重：同一 subset 中若仍重名（深层嵌套目录同 parents），追加序号，
    # 保证全量任务都运行、checkpoint 互不覆盖 —— 不重跑也不丢弃任何任务
    seen_ids: dict[str, int] = {}
    for t in tasks:
        n = seen_ids.get(t.task_id, 0)
        seen_ids[t.task_id] = n + 1
        if n:
            t.task_id = f"{t.task_id}-{n + 1}"
    if not tasks:
        raise DatasetFetchError(
            "workbuddy-bench 无可用任务: " + ("; ".join(missing) or "缺文件"))
''')
assert text.count(old) == 1, f"anchor count={text.count(old)}"
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("patched ok")
