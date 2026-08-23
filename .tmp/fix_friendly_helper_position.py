# -*- coding: utf-8 -*-
"""把 humanizeErrorMessage 从对象字面量内移到模块顶层。"""
import re
from pathlib import Path

path = Path(r"E:\FNIX\FnixAgent\apps\workbench\src\shell\desktop\useChatFlow.ts")
text = path.read_text(encoding="utf-8")
NL = "\r\n" if "\r\n" in text else "\n"

# 1. 摘出当前错误位置的 helper 块
pat = re.compile(
    re.escape("\n/**") + r".*?humanizeErrorMessage.*?\n\}\n",
    re.S,
)
m = pat.search(text)
assert m, "helper block not found in wrong location"
helper_block = m.group(0)
text = text[:m.start()] + "\n" + text[m.end():]

# 2. 插入到模块顶层：第一个 export 语句之前
m2 = re.search(r"^export ", text, re.M)
assert m2, "no export found"
text = text[:m2.start()] + helper_block.strip("\n") + NL + NL + text[m2.start():]

path.write_text(text, encoding="utf-8")
print("moved ok")
