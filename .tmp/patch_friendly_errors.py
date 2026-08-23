# -*- coding: utf-8 -*-
"""useChatFlow: 把裸技术错误转译成用户可行动的指引文案。"""
from pathlib import Path

path = Path(r"E:\FNIX\FnixAgent\apps\workbench\src\shell\desktop\useChatFlow.ts")
text = path.read_text(encoding="utf-8")
NL = "\r\n" if "\r\n" in text else "\n"

def block(s: str) -> str:
    return s.replace("\n", NL)

helper = block('''
/** 把后端返回的裸技术错误转译为用户可行动的指引文案（保留原文供诊断）。 */
export function humanizeErrorMessage(raw: string): string {
  const msg = String(raw || '');
  if (!msg) return msg;
  if (/insufficient_quota|Free quota exhausted|HTTP 40[13]/i.test(msg)) {
    return '模型配额已耗尽或鉴权失败：请在设置中更换有效模型/Key，或启用兜底模型链后重试。';
  }
  if (/Too Many Requests|HTTP 429/i.test(msg)) {
    return '模型服务限流中，系统已自动重试；若持续失败请稍后重试或切换模型。';
  }
  if (/HTTP 4294|Deadlock detected/i.test(msg)) {
    return msg;
  }
  if (/任务超时|TimeoutError/i.test(msg)) {
    return '任务执行超时：可拆小任务或在设置中增大超时时间后重试。';
  }
  return msg;
}

''')

anchor = block('''    onError: (message: string) => {
      setError(message);
''')
if helper.strip() not in text:
    # 在 onError 锚点前插入 helper（向上一段缩进级别插入）
    assert anchor in text, "onError anchor not found"
    text = text.replace(anchor, helper + anchor, 1)

old = block('''    onError: (message: string) => {
      setError(message);
''')
new = block('''    onError: (rawMessage: string) => {
      const message = humanizeErrorMessage(rawMessage);
      setError(message);
''')
assert old in text, "onError body anchor not found"
text = text.replace(old, new, 1)

path.write_text(text, encoding="utf-8")
print("patched ok")
