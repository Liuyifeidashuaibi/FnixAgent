# 测试策略 / Testing Strategy

> 本文件定义 FnixAgent 的测试金字塔、覆盖率目标、CI 流程。

---

## 一、测试金字塔 / Test Pyramid

```
          /\
         /  \         E2E (Playwright)        < 5%
        /    \        慢, 端到端
       /------\
      /        \      Integration (Testcontainers)  ~ 15%
     /          \     真实 DB / Network
    /------------\
   /              \   Unit (pytest / vitest)         ~ 80%
  /________________\  快, 纯函数 / 模块
```

**目标覆盖率**:

| 层级 | 覆盖率目标 | 工具 |
| --- | --- | --- |
| Python (核心) | 85% | pytest-cov |
| TypeScript (前端) | 80% | vitest --coverage |
| Rust (Tauri) | 75% | cargo-tarpaulin |
| 整体 (跨语言集成) | 70% | E2E 间接覆盖 |

**核心模块硬性 95%**:
- `fnixagent/crypto/` (密钥)
- `fnixagent/memory/store.py` (记忆存储)
- `src-tauri/src/capabilities/` (Tauri 权限)

---

## 二、单元测试 / Unit Tests

### Python (pytest)

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "-ra --strict-markers --strict-config"
testpaths = ["tests"]
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "network: requires network access",
    "integration: integration tests",
]
```

#### 测试示例

```python
# tests/test_memory.py
import pytest
from fnixagent.memory import MemoryStore, MemoryChunk

@pytest.fixture
async def memory_store(tmp_path):
    db_path = tmp_path / "memory.sqlite"
    store = MemoryStore(db_path)
    await store.init()
    yield store
    await store.close()

@pytest.mark.asyncio
async def test_add_and_retrieve(memory_store):
    chunk = MemoryChunk(
        type="episodic",
        content="用户喜欢 Rust",
        importance=0.8,
    )
    chunk_id = await memory_store.add(chunk)
    retrieved = await memory_store.get(chunk_id)
    assert retrieved.content == "用户喜欢 Rust"
    assert retrieved.importance == 0.8

@pytest.mark.asyncio
async def test_semantic_search(memory_store):
    await memory_store.add(MemoryChunk(content="Rust 所有权系统很优雅"))
    await memory_store.add(MemoryChunk(content="今天吃火锅"))

    results = await memory_store.search("系统编程语言", k=5)
    assert any("Rust" in r.content for r in results)
```

#### 参数化

```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("", ""),
    ("中文", "中文"),
])
def test_upper(input, expected):
    assert fnixagent.utils.upper(input) == expected
```

#### Mock LLM

```python
# tests/conftest.py
import pytest
from fnixagent.llm import LLMClient

class FakeLLM(LLMClient):
    def __init__(self, responses):
        self.responses = iter(responses)

    async def generate(self, prompt, **kwargs):
        return next(self.responses)

@pytest.fixture
def fake_llm():
    return FakeLLM([
        "Hello!",  # 第 1 次调用返回
        "World!",  # 第 2 次
    ])
```

### TypeScript (Vitest)

```typescript
// apps/workbench/src/lib/skills.test.ts
import { describe, it, expect, vi } from 'vitest'
import { parseSkillFrontmatter } from './skills'

describe('parseSkillFrontmatter', => {
  it('parses valid skill', => {
    const md = `---
skill: code-review
version: 1.0.0
---
# Content`
    const result = parseSkillFrontmatter(md)
    expect(result.frontmatter.skill).toBe('code-review')
    expect(result.content).toContain('# Content')
  })

  it('throws on invalid YAML', => {
    expect(=>
      parseSkillFrontmatter('---\nskill: [invalid\n---\nbody')
    ).toThrow()
  })
})
```

### Rust (cargo test)

```rust
// src-tauri/src/capabilities/allowlist.rs
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_path_in_workspace{
        let allowlist = AllowList::new(&["/home/user/notes"]).unwrap();
        assert!(allowlist.contains("/home/user/notes/file.md"));
        assert!(!allowlist.contains("/etc/passwd"));
    }

    #[test]
    fn test_path_traversal_blocked{
        let allowlist = AllowList::new(&["/home/user/notes"]).unwrap();
        assert!(!allowlist.contains("/home/user/notes/../etc/passwd"));
    }
}
```

---

## 三、集成测试 / Integration Tests

### Testcontainers (Python)

```python
# tests/integration/test_agentd_postgres.py
import pytest
from testcontainers.postgres import PostgresContainer
from fnixagent.db import Database

@pytest.fixture(scope="session")
def postgres():
    with PostgresContainer("postgres:16") as pg:
        yield pg

@pytest.mark.integration
async def test_save_and_load(postgres):
    db = Database(postgres.get_connection_url())
    await db.migrate()

    await db.save({"id": 1, "content": "hello"})
    result = await db.load(1)
    assert result["content"] == "hello"
```

### Tauri E2E (WebDriver)

```typescript
// tests/e2e/startup.spec.ts
import { test, expect } from '@playwright/test'

test('workbench launches and shows home', async ({ page }) => {
  await page.goto('tauri://localhost/')
  await expect(page.getByRole('heading', { name: 'FnixAgent' })).toBeVisible()
})
```

### LLM 集成(用录播)

```python
# tests/integration/test_llm_openai.py
import pytest
from fnixagent.llm import  LLMClient
from vcr import vcr  # 用 VCR.py 录播 HTTP

@vcr.use_cassette("tests/fixtures/openai_chat_completion.yaml")
@pytest.mark.integration
async def test_chat_completion():
    client =  LLMClient(api_key="test")
    result = await client.generate("hello")
    assert "hello" in result.text.loweror len(result.text) > 0
```

---

## 四、端到端测试 / E2E Tests

`tests/e2e/` 用 Playwright:

### 关键场景

```typescript
// tests/e2e/smoke.spec.ts
import { test, expect } from '@playwright/test'

test('user can send a message and get a response', async ({ page }) => {
  await page.goto('tauri://localhost/')

  // 等待 UI 就绪
  await expect(page.getByTestId('chat-input')).toBeVisible()

  // 发送消息
  await page.getByTestId('chat-input').fill('你好')
  await page.getByTestId('send-button').click()

  // 等待响应
  await expect(page.getByTestId('chat-message').last()).toContainText(/./, {
    timeout: 30_000,
  })
})
```

```typescript
// tests/e2e/skill-execution.spec.ts
test('user can run a skill', async ({ page }) => {
  await page.goto('tauri://localhost/')
  await page.getByTestId('skill-palette').click()
  await page.getByTestId('skill-code-review').click()
  await page.getByTestId('skill-run').click()
  await expect(page.getByTestId('skill-result')).toBeVisible()
})
```

---

## 五、属性测试 / Property-Based Testing

用 Hypothesis (Python) / fast-check (TS):

```python
# tests/test_properties.py
from hypothesis import given, strategies as st
from fnixagent.utils import slugify

@given(st.text(min_size=1, max_size=100))
def test_slugify_idempotent(text):
    once = slugify(text)
    twice = slugify(once)
    assert once == twice

@given(st.text(min_size=1, max_size=100))
def test_slugify_lowercase_and_safe(text):
    slug = slugify(text)
    assert slug == slug.lower()
    assert all(c.isalnumor c == '-' for c in slug)
```

---

## 六、回归测试 / Regression Tests

### Snapshot 测试

```python
# tests/snapshots/test_plan_output.py
import pytest
from fnixagent.planning import STPGenerator

def test_stp_snapshot(snapshot):
    generator = STPGenerator(provider="fake")
    plan = generator.generate("Write tests")
    snapshot.assert_match(plan.to_dict())
```

### Golden Master

`tests/golden/` 目录存放真实大模型的输出片段,每次升级对比:

```bash
make test-golden
```

差异超过阈值需要人工 review。

---

## 七、CI 集成 / CI Integration

### 测试矩阵

| OS | Python | Node | Rust | 触发 |
| --- | --- | --- | --- | --- |
| Ubuntu 22.04 | 3.10, 3.11, 3.12, 3.13 | 20, 22 | stable | push / PR |
| macOS 13 | 3.12 | 20, 22 | stable | nightly |
| Windows 2022 | 3.12 | 20, 22 | stable | nightly |

### 必须通过的检查

- [ ] `make lint` — ESLint + Ruff + Clippy
- [ ] `make typecheck` — tsc --noEmit + mypy --strict
- [ ] `make test` — pytest + vitest + cargo test
- [ ] `make coverage` — 覆盖率不下降
- [ ] `make a11y` — axe-core 扫描
- [ ] `make sbom` — SBOM 生成

### 慢测试

`@pytest.mark.slow` 的测试只在 nightly 跑:

```bash
pytest -m "not slow"     # CI 默认
pytest -m "slow"         # nightly
```

---

## 八、覆盖率报告 / Coverage

### 生成报告

```bash
# Python
uv run pytest --cov=fnixagent --cov-report=html --cov-report=xml

# TypeScript
pnpm vitest run --coverage

# Rust
cargo tarpaulin --out Html --output-dir coverage
```

### Codecov 集成

`.github/workflows/coverage.yml`:

```yaml
- uses: codecov/codecov-action@v4
  with:
    files: ./coverage.xml,./coverage-ts.xml,./coverage-rust.tarpaulin.xml
    fail_ci_if_error: true
```

---

## 九、调试失败测试 / Debugging

### 本地复现

```bash
# 跑单个测试
uv run pytest tests/test_memory.py::test_add_and_retrieve -xvs

# 进入 PDB
uv run pytest tests/test_memory.py --pdb
```

### 收集现场数据

```bash
# 保存失败时的数据库、日志
pytest --artifact-dir=artifacts/
```

---

## 十、性能测试 / Performance Tests

见 `docs/development/PERFORMANCE.md`。

---

## 十一、/ References

- [pytest 文档](https://docs.pytest.org/)
- [Vitest 文档](https://vitest.dev/)
- [cargo test](https://doc.rust-lang.org/book/ch11-00-testing.html)
- [Playwright](https://playwright.dev/)
- [Hypothesis](https://hypothesis.readthedocs.io/)

---

© 2024-2026 FnixAgent. Licensed under PolyForm Noncommercial License 1.0.0.