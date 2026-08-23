# -*- coding: utf-8 -*-
"""workbuddy task_id 前缀 subset，修复跨子集 ID 冲突。"""
from pathlib import Path

path = Path(r"E:\FNIX\FnixAgent\src\fnixagent\bench\datasets.py")
text = path.read_text(encoding="utf-8")
NL = "\r\n" if "\r\n" in text else "\n"

def block(s: str) -> str:
    return s.replace("\n", NL)

old = block('''                    task_id = member.name.split("/")[-2]
''')
new = block('''                    # 各子集内任务目录名可能重名（如 task-01），前缀 subset 保证全库唯一
                    task_id = f"{subset}--{member.name.split('/')[-2]}"
''')
assert text.count(old) == 1, f"anchor count={text.count(old)}"
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("patched ok")
