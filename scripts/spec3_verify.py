"""Spec 3 端点验证：/api/v1/work/artifacts/read"""

# -*- coding: utf-8 -*-
# Copyright (C) 2026 FnixAgent. All rights reserved.
# Software Name: FnixAgent 智能工作台系统 V1.0
# This software and its source code are proprietary and confidential.
# Unauthorized copying, modification, distribution, or use is strictly prohibited.

import json
import urllib.request
import urllib.parse
from pathlib import Path

api_base = "http://127.0.0.1:8003"

# 测试 1: 相对路径
test_path = ".fnix\\artifacts\\hello\\index.html"
url = f"{api_base}/api/v1/work/artifacts/read?path={urllib.parse.quote(test_path)}"
print(f">>> GET {url}")
with urllib.request.urlopen(url) as resp:
    data = json.loads(resp.read().decode("utf-8"))

print(f"ok: {data.get('ok')}")
print(f"name: {data.get('name')}")
print(f"ext: {data.get('ext')}")
print(f"size: {data.get('size')}")
print(f"mime: {data.get('mime')}")
print(f"encoding: {data.get('encoding')}")
print(f"is_html: {data.get('is_html')}")
content = data.get("content", "")
print(f"content length: {len(content)}")
print(f"content preview: {content[:200]}")

print("\n--- 测试 2: 路径穿越攻击 ---")
evil_path = "../../Windows/win.ini"
url2 = f"{api_base}/api/v1/work/artifacts/read?path={urllib.parse.quote(evil_path)}"
print(f">>> GET {url2}")
try:
    with urllib.request.urlopen(url2) as resp:
        data2 = json.loads(resp.read().decode("utf-8"))
    print(f"ok: {data2.get('ok')}")
    print(f"error: {data2.get('error')}")
    if data2.get("ok"):
        print("FAIL: 路径穿越攻击成功！")
    else:
        print("PASS: 路径穿越被拒绝")
except Exception as e:
    print(f"PASS: 路径穿越被拒绝 (异常: {e})")

print("\n--- 测试 3: 不存在文件 ---")
ghost_path = ".fnix/artifacts/ghost/no_such_file.html"
url3 = f"{api_base}/api/v1/work/artifacts/read?path={urllib.parse.quote(ghost_path)}"
print(f">>> GET {url3}")
with urllib.request.urlopen(url3) as resp:
    data3 = json.loads(resp.read().decode("utf-8"))
print(f"ok: {data3.get('ok')}")
print(f"error: {data3.get('error')}")
if not data3.get("ok"):
    print("PASS: 不存在文件正确返回错误")
else:
    print("FAIL: 不存在文件返回 ok=true")

print("\n--- 测试 4: 不允许的扩展名 ---")
# 创建一个 .exe 文件测试
exe_path = Path(".fnix/artifacts/hello/test.exe")
exe_path.parent.mkdir(parents=True, exist_ok=True)
exe_path.write_bytes(b"MZ\x90\x00test")
try:
    url4 = f"{api_base}/api/v1/work/artifacts/read?path={urllib.parse.quote(str(exe_path))}"
    print(f">>> GET {url4}")
    with urllib.request.urlopen(url4) as resp:
        data4 = json.loads(resp.read().decode("utf-8"))
    print(f"ok: {data4.get('ok')}")
    print(f"error: {data4.get('error')}")
    if not data4.get("ok") and "not previewable" in (data4.get("error") or ""):
        print("PASS: .exe 被拒绝")
    else:
        print("FAIL: .exe 应被拒绝")
finally:
    exe_path.unlink(missing_ok=True)

print("\n=== Spec 3 后端端点验证完成 ===")
