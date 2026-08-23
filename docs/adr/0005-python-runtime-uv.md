---
adr_id: 0005
title: Python 异步运行时 + uv 包管理
status: Accepted
date: 2026-08-16
deciders: FnixAgent Core Team
consulted: DevEx WG
informed: All contributors
supersedes: null
superseded_by: null
tags: [engineering, runtime, packaging]
---

# ADR-0005: Python 异步运行时 + uv 包管理

## Context (背景)

FnixAgent 核心逻辑用 Python 实现 (LLM 客户端、工具注册、记忆、规划),需要选择:

1. **Python 版本**:3.10 / 3.11 / 3.12 / 3.13
2. **异步运行时**:asyncio / trio / anyio
3. **包管理**:pip + venv / poetry / pdm / uv / rye
4. **依赖锁定**:requirements.txt / poetry.lock / uv.lock / pylock.toml

候选对比:

| 维度 | asyncio + uv | trio + poetry | asyncio + pdm |
| --- | --- | --- | --- |
| LLM SDK 支持 | ★★★★★ | ★★★ | ★★★★★ |
| 包安装速度 | ★★★★★ (uv 比 pip 快 10-100x) | ★★ | ★★★ |
| 锁文件可读 | ★★★★★ (uv.lock TOML) | ★★★★ | ★★★ |
| 跨平台 | ✓ | ✓ | ✓ |
| 生态熟悉度 | ★★★★ | ★★★ | ★★★ |

## Decision (决策)

### 1. Python 3.12

- 最低支持:`python_requires=">=3.10"` (3.10 才稳定)
- 开发/CI:3.12
- 测试矩阵:`[3.10, 3.11, 3.12, 3.13]`

### 2. asyncio + anyio

- 主运行时:标准库 `asyncio`
- 跨平台抽象:`anyio` (兼容 trio 异步组)
- LLM SDK 全部用 `httpx.AsyncClient`

### 3. uv (Astral)

- 安装:`curl -LsSf https://astral.sh/uv/install.sh | sh` (官方)
- 锁文件:`uv.lock` (TOML 格式)
- 同步脚本:`uv sync --all-extras`
- 运行脚本:`uv run python -m fnixagent`

### 4. 标准化布局

```
fnixagent/
├── pyproject.toml          # 单一来源
├── uv.lock                 # 锁文件 (commit 进 git)
├── .python-version         # 3.12
├── src/fnixagent/          # src 布局 (避免 import 歧义)
└── tests/
```

## Consequences (后果)

### 正面

- **安装速度**:从 poetry 的 60s 降到 uv 的 2s (实测)
- **锁文件可读**:uv.lock 是 TOML,review 友好
- **跨团队统一**:一个 pyproject.toml 就够
- **CI 缓存命中**:uv 的 cache key 算法比 pip 更精确

### 负面 / 风险

- uv 仍在 0.x → 偶发 breaking change
- 团队成员需要安装 uv (CI 镜像内置)

### 缓解

- uv 升级前看 changelog,有 breaking 就 freeze 一个月
- `Makefile` 提供 `make install` / `make test` 包装,降低入门成本

## Alternatives Considered (备选方案)

- **poetry**:成熟但慢,锁文件 review 体验差
- **pdm**:功能全但生态弱
- **rye**:已经合并到 uv,排除

## References (参考)

- [uv 官方文档](https://docs.astral.sh/uv/)
- [PEP 621 pyproject.toml](https://peps.python.org/pep-0621/)
- [PEP 735 Dependency Groups](https://peps.python.org/pep-0735/)

## Notes (备注)

本仓库 `pyproject.toml` 已切到 uv。GitHub Actions 用 `astral-sh/setup-uv@v3`。