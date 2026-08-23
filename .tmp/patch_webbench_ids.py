# -*- coding: utf-8 -*-
"""web-bench task_id 前缀项目名，修复跨项目 ID 冲突。"""
from pathlib import Path

path = Path(r"E:\FNIX\FnixAgent\src\fnixagent\bench\datasets.py")
text = path.read_text(encoding="utf-8")
NL = "\r\n" if "\r\n" in text else "\n"

def block(s: str) -> str:
    return s.replace("\n", NL)

old = block('''            tasks.append(BenchTask(
                dataset="web-bench",
                task_id=rec.get("id") or rec.get("task_id") or f"{project}-{i+1}",
                prompt=prompt, subset=project, expected=rec.get("test") or rec.get("tests"),
                meta=rec,
            ))
''')
new = block('''            # web-bench 每个项目共享 task-1..task-20 同一 id 空间，
            # 必须前缀项目名保证数据集内唯一（否则 checkpoint 去重冲突、轨迹互相覆盖）
            base_id = str(rec.get("id") or rec.get("task_id") or f"task-{i+1}")
            tasks.append(BenchTask(
                dataset="web-bench",
                task_id=f"{project}--{base_id}",
                prompt=prompt, subset=project, expected=rec.get("test") or rec.get("tests"),
                meta=rec,
            ))
''')
assert old in text, "anchor not found"
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("patched ok")
