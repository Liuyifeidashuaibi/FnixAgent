"""SampleFlawedAgent — FnixForge 演示用"半成品 Agent"。

故意包含的缺陷（Forge 会逐一暴露）:
  1. 输出不精确: 写文件时总爱附带"解释性前缀" → 违背指令遵循/输出契约类题目
  2. 作用域越界: 每次都会在沙箱里留下 agent.log → 触发 scope_respected 失败
  3. 中文理解差: "去重排序"类任务只做了去重没排序
  4. 数字处理偷懒: 统计任务写文字而不是纯数字
  5. 从不读已有文件做最小编辑 → edit 类题目全灭

用 fnixagent forge fix 可让 FnixAgent 自动把这个 Agent 修到通过。
"""

# -*- coding: utf-8 -*-
from __future__ import annotations

import base64
import os
import re
import sys
from pathlib import Path

def _decode_prompt() -> str:
    b64 = os.environ.get("FNIX_FORGE_PROMPT_B64", "")
    if b64:
        try:
            return base64.b64decode(b64).decode("utf-8")
        except Exception:
            return ""
    return " ".join(sys.argv[2:])

def _leave_log(ws: Path, msg: str) -> None:
    # 缺陷 2: 乱写日志文件（越界）
    (ws / "agent.log").write_text(msg, encoding="utf-8")

def _find_txt_name(prompt: str) -> str | None:
    m = re.search(r"([A-Za-z0-9_\-]+\.(?:txt|json|py|ini|md))", prompt)
    return m.group(1) if m else None

def handle(prompt: str, ws: Path) -> int:
    p = prompt.lower()

    # --- 简单"创建文件"意图 ---
    if ("创建" in prompt or "新建" in prompt or "写入" in prompt or "创建" in p) :
        name = _find_txt_name(prompt)
        if name:
            # 缺陷 1: 内容里加解释性文字，破坏精确匹配
            content = "已完成任务。\n" + re.search(r"内容(?:写)?[:：]?\s*(.+?)(?:。|$)", prompt, re.S).group(1) if re.search(r"内容(?:写)?[:：]\s*(.+?)(?:。|$)", prompt, re.S) else "已完成任务。\n"
            (ws / name).write_text(content, encoding="utf-8")
            _leave_log(ws, f"created {name}")
            print(f"已创建 {name}")
            return 0

    # --- 统计类 ---
    if "行数" in prompt or "统计" in prompt:
        src = next(ws.glob("*.csv"), None)
        if src is not None:
            n = max(0, len(src.read_text(encoding="utf-8").strip().splitlines()) - 1)
            # 缺陷 4: 写文字而不是纯数字
            (ws / "count.txt").write_text(f"一共有 {n} 行", encoding="utf-8")
            _leave_log(ws, "counted")
            print("统计完成")
            return 0

    # --- 去重排序 ---
    if "去重" in prompt:
        src = ws / "names.txt"
        if src.is_file():
            lines = [x.strip() for x in src.read_text(encoding="utf-8").splitlines() if x.strip()]
            uniq = list(dict.fromkeys(lines))  # 缺陷 3: 没去排序
            (ws / "sorted.txt").write_text("\n".join(uniq) + "\n", encoding="utf-8")
            _leave_log(ws, "sorted")
            print("排序完成")
            return 0

    # --- 其余任务: 直接放弃（缺陷 5）---
    _leave_log(ws, f"unsupported: {prompt[:80]}")
    print("这个任务我暂时不会。")
    return 0

def main() -> int:
    ws = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    prompt = _decode_prompt()
    if not prompt:
        print("no prompt", file=sys.stderr)
        return 2
    return handle(prompt, ws)

if __name__ == "__main__":
    raise SystemExit(main())
