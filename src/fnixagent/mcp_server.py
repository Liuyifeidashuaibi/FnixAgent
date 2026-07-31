"""FnixAgent MCP Server — 对外暴露 Agent 能力为 MCP 工具（Spec 7）。

基于官方 MCP Python SDK 的 FastMCP（modelcontextprotocol/python-sdk）：
  - @mcp.tool() 装饰器自动从 type hints 推导 JSON Schema
  - run(transport="stdio") 给 Cursor/Trae/Claude Desktop 子进程
  - run(transport="sse") 或 sse_app() 挂载到 uvicorn 给远程调用

工具列表:
  - work_stream    触发 Work 流水线（ask/plan/craft）
  - ask            快速问答（不进入 Work 流水线）
  - skill_list     列出 .fnix/skills/*.md + HERA 自动捕获技能
  - skill_detail   读取指定技能完整内容
  - memory_search  长期记忆检索
  - artifact_read  读取 .fnix/artifacts/ 产物
  - evolution_status  当前 KTG/STP/MFP 状态
  - self_optimizing_stats  Self-Optimizing 示例库统计

三端配置见 docs/superpowers/specs/2026-07-20-fnix-top-tier-design.md Spec 7 章节。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 确保项目 src 在 sys.path 中（MCP 子进程可能不继承 PYTHONPATH）
_WORKSPACE = os.getenv("FNIX_WORKSPACE", ".")
_SRC = Path(_WORKSPACE).resolve() / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    sys.stderr.write(
        f"[fnix-mcp] 缺少 mcp 包，请执行: pip install 'mcp[cli]>=1.6.0'\n原始错误: {e}\n"
    )
    raise

import httpx

# 延迟导入 fnixagent 模块（避免 MCP 子进程启动时硬依赖）

API_BASE = os.getenv("FNIX_API_BASE", "http://127.0.0.1:8003")
WORKSPACE = os.path.normpath(os.path.abspath(_WORKSPACE))

mcp = FastMCP(
    "fnix-agent",
    instructions=(
        "FnixAgent MCP — Long-Horizon Software Engineering Labor Platform. "
        "Tools: work_stream (Work pipeline), ask (quick Q&A), "
        "skill_list/skill_detail (skills), memory_search (long-term memory), "
        "artifact_read (read deliverables), evolution_status (KTG/STP/MFP), "
        "self_optimizing_stats (few-shot library)."
    ),
)


def _api_post(path: str, **kwargs) -> httpx.Response:
    """调用 FnixAgent HTTP API（8003 端口）。"""
    with httpx.Client(base_url=API_BASE, timeout=120.0) as client:
        return client.post(path, json=kwargs)


def _api_get(path: str, **params) -> httpx.Response:
    """GET 请求 FnixAgent HTTP API。"""
    with httpx.Client(base_url=API_BASE, timeout=30.0) as client:
        return client.get(path, params=params)


@mcp.tool()
def work_stream(
    user_input: str,
    work_mode: str = "craft",
    workspace: str | None = None,
) -> str:
    """触发 FnixAgent Work 流水线（ask/plan/craft）。

    Args:
        user_input: 用户任务描述（自然语言）
        work_mode: 执行模式 — ask（问答）/ plan（规划）/ craft（执行，默认）
        workspace: 工作空间绝对路径，不填则用 FNIX_WORKSPACE 环境变量

    Returns:
        Work 流水线的最终文本输出（聚合 NDJSON stream 的 text chunk）
    """
    ws = workspace or WORKSPACE
    try:
        # work_stream 返回 NDJSON，需要聚合 text chunk
        with (
            httpx.Client(base_url=API_BASE, timeout=300.0) as client,
            client.stream(
                "POST",
                "/api/v1/work/stream",
                json={
                    "user_input": user_input,
                    "workspace": ws,
                    "work_mode": work_mode,
                },
            ) as resp,
        ):
            resp.raise_for_status()
            texts: list[str] = []
            for line in resp.iter_lines():
                line = line.strip()
                if not line:
                    continue
                try:
                    import json

                    obj = json.loads(line)
                except ValueError:
                    continue
                chunk = str(obj.get("chunk_type") or obj.get("type") or "")
                if chunk == "text":
                    content = obj.get("content", "")
                    if isinstance(content, str) and content:
                        texts.append(content)
                elif chunk == "error":
                    return f"[error] {obj.get('content', '')}"
            return "".join(texts) if texts else "[work_stream completed with no text output]"
    except httpx.HTTPError as e:
        return f"[http error] {e}"


@mcp.tool()
def ask(prompt: str, workspace: str | None = None) -> str:
    """快速向 Agent 提问（不进入 Work 流水线，轻量问答）。

    Args:
        prompt: 用户问题
        workspace: 工作空间路径

    Returns:
        Agent 的回答文本
    """
    ws = workspace or WORKSPACE
    try:
        r = _api_post("/api/v1/chat/agent", prompt=prompt, workspace=ws)
        r.raise_for_status()
        data = r.json()
        return str(data.get("response") or data.get("text") or "")
    except httpx.HTTPError as e:
        return f"[http error] {e}"


@mcp.tool()
def skill_list(workspace: str | None = None) -> list[dict]:
    """列出工作空间的技能定义。

    包含两个来源：
      1. 用户手写的 .fnix/skills/*.md（静态技能）
      2. HERA 自动捕获的成功轨迹（动态技能，存于 .fnix/skill_library/）

    Args:
        workspace: 工作空间路径

    Returns:
        技能列表，每项含 name/path/preview/auto 等字段
    """
    ws = workspace or WORKSPACE
    result: list[dict] = []
    try:
        from fnixagent.harness.skills_loader import load_workspace_skills

        for s in load_workspace_skills(ws):
            result.append(
                {
                    "name": s.name,
                    "path": s.path,
                    "preview": s.content[:200],
                    "auto": False,
                }
            )
    except Exception as e:
        result.append({"name": "_error_user_skills", "error": str(e)})

    try:
        from fnixagent.core.skills import SkillLibrary

        lib = SkillLibrary(ws)
        for sk in lib.skills[:50]:
            result.append(
                {
                    "name": sk.skill_id,
                    "task_signature": sk.task_signature,
                    "preview": sk.solution_summary[:200],
                    "workspace_kind": sk.workspace_kind,
                    "usage_count": sk.usage_count,
                    "auto": True,
                }
            )
    except Exception as e:
        result.append({"name": "_error_hera_skills", "error": str(e)})

    return result


@mcp.tool()
def skill_detail(name: str, workspace: str | None = None) -> str:
    """读取指定技能的完整内容。

    Args:
        name: 技能名（来自 skill_list 的 name 字段）
        workspace: 工作空间路径

    Returns:
        技能的完整 Markdown 文本（用户技能）或 JSON（HERA 技能）
    """
    ws = workspace or WORKSPACE
    try:
        from fnixagent.harness.skills_loader import load_workspace_skills

        for s in load_workspace_skills(ws):
            if s.name == name:
                return s.content
    except Exception:
        pass

    try:
        from fnixagent.core.skills import SkillLibrary

        lib = SkillLibrary(ws)
        for sk in lib.skills:
            if sk.skill_id == name:
                from dataclasses import asdict

                return str(asdict(sk))
    except Exception:
        pass

    return f"skill not found: {name}"


@mcp.tool()
def memory_search(query: str, top_k: int = 5, workspace: str | None = None) -> list[dict]:
    """从 FnixAgent 长期记忆检索相关条目。

    Args:
        query: 检索查询（自然语言）
        top_k: 返回条目数上限（默认 5，最大 20）
        workspace: 工作空间路径

    Returns:
        命中的记忆条目列表，每项含 content/score/source 等字段
    """
    ws = workspace or WORKSPACE
    top_k = max(1, min(20, int(top_k)))
    try:
        r = _api_post(
            "/api/v1/memory/search",
            query=query,
            top_k=top_k,
            workspace=ws,
        )
        r.raise_for_status()
        data = r.json()
        hits = data.get("hits") or data.get("results") or []
        return list(hits)[:top_k]
    except httpx.HTTPError as e:
        return [{"error": str(e)}]


@mcp.tool()
def artifact_read(
    artifact_path: str,
    max_chars: int = 20000,
    workspace: str | None = None,
) -> str:
    """读取 .fnix/artifacts/ 下的产物（文档/表格/代码）。

    路径安全：仅允许读取 workspace/.fnix/artifacts/ 下的文件，防止越权访问。

    Args:
        artifact_path: 产物相对路径（如 "hello/index.html"）或绝对路径
        max_chars: 最大返回字符数（默认 20000，防止超大文件）
        workspace: 工作空间路径

    Returns:
        产物文件内容（文本）
    """
    ws = workspace or WORKSPACE
    ws_root = Path(ws).expanduser().resolve()
    art_root = ws_root / ".fnix" / "artifacts"

    # 路径规范化：相对路径拼接，绝对路径提取 .fnix/artifacts/ 后缀
    p = str(artifact_path).strip().replace("\\", "/").lstrip("/")
    if not p:
        return "[error] empty artifact_path"

    # 处理绝对路径或 .fnix/artifacts/ 前缀
    if ".fnix/artifacts/" in p.lower():
        idx = p.lower().find(".fnix/artifacts/")
        p = p[idx + len(".fnix/artifacts/") :]

    full = (art_root / p).resolve()
    try:
        full.relative_to(art_root)
    except ValueError:
        return f"[error] path outside artifacts: {p}"

    if not full.is_file():
        return f"[error] artifact not found: {p}"

    try:
        return full.read_text(encoding="utf-8", errors="replace")[:max_chars]
    except OSError as e:
        return f"[error] read failed: {e}"


@mcp.tool()
def evolution_status(workspace: str | None = None) -> dict:
    """获取 FnixAgent 进化状态快照（KTG/STP/MFP）。

    KTG = Knowledge Topology Graph（知识拓扑图）
    STP = Skill Training Pipeline（技能训练管线）
    MFP = Memory Fixation Pipeline（记忆固化管线）

    Args:
        workspace: 工作空间路径

    Returns:
        含 ktg_paths/ktg_nodes/concepts/memory 等字段的进化状态字典
    """
    ws = workspace or WORKSPACE
    try:
        r = _api_get("/api/v1/harness/status", workspace=ws)
        r.raise_for_status()
        return dict(r.json())
    except httpx.HTTPError as e:
        return {"error": str(e)}


@mcp.tool()
def self_optimizing_stats(workspace: str | None = None) -> dict:
    """获取 Self-Optimizing few-shot 示例库统计。

    返回示例总数、平均 score、按 workspace_kind 分布。

    Args:
        workspace: 工作空间路径

    Returns:
        统计字典
    """
    ws = workspace or WORKSPACE
    try:
        from fnixagent.core.intelligence.self_optimizing import SelfOptimizingLibrary

        lib = SelfOptimizingLibrary(ws)
        return lib.stats()
    except Exception as e:
        return {"error": str(e)}


# ── 资源（Resources）—— IDE 可直接读取 ──


@mcp.resource("fnix://skills/{name}")
def skill_resource(name: str) -> str:
    """技能完整内容（IDE 可作为 resource 读取）。"""
    return skill_detail(name)


@mcp.resource("fnix://status")
def status_resource() -> str:
    """FnixAgent 当前状态（人类可读）。"""
    try:
        st = evolution_status()
        lines = [f"FnixAgent Status (workspace={WORKSPACE})"]
        lines.append(f"API: {API_BASE}")
        lines.append(f"KTG paths: {st.get('ktg_paths', 'n/a')}")
        lines.append(f"KTG nodes: {st.get('ktg_nodes', 'n/a')}")
        return "\n".join(lines)
    except Exception as e:
        return f"status error: {e}"


def main() -> None:
    """MCP Server 入口。

    传输模式:
      - stdio（默认）：给 Cursor/Trae/Claude Desktop 作为子进程
      - sse：启动 HTTP+SSE server，给远程客户端
      - http：streamable HTTP（mcp>=1.6，2025-06 规范）
    """
    parser = argparse.ArgumentParser(description="FnixAgent MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default="stdio",
        help="传输模式（默认 stdio）",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP/SSE 监听地址")
    parser.add_argument("--port", type=int, default=8765, help="HTTP/SSE 监听端口")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        try:
            import uvicorn

            uvicorn.run(mcp.sse_app(), host=args.host, port=args.port)
        except ImportError:
            sys.stderr.write("[fnix-mcp] sse 模式需要 uvicorn: pip install uvicorn\n")
            raise
    else:  # http
        try:
            import uvicorn

            # streamable_http_app 是 mcp>=1.6 的新传输
            app = mcp.streamable_http_app()
            uvicorn.run(app, host=args.host, port=args.port)
        except (ImportError, AttributeError):
            # 回退到 sse
            sys.stderr.write("[fnix-mcp] streamable HTTP 不可用，回退到 sse\n")
            import uvicorn

            uvicorn.run(mcp.sse_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
