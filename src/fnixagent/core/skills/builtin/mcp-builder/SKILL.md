---
name: mcp-builder
description: MCP 服务器构建指南 — 注册工具/资源/提示，对齐 Model Context Protocol
version: 1.0.0
license: Apache-2.0
level: META
output_format: py
tags:
  - mcp
  - model-context-protocol
  - server
  - code
  - integration
resources:
  - core/mcp/server.py
  - core/mcp/registry.py
  - core/mcp/types.py
---

# MCP Builder Skill

MCP (Model Context Protocol) 服务器构建技能。指导用户构建对齐 MCP 标准的服务器：注册工具 (tools) / 资源 (resources) / 提示 (prompts)，对接 Fnix MCP 客户端。

## 何时使用

- 用户要构建自定义 MCP 服务器（暴露工具给 AI 调用）
- 用户要把已有 API / 服务封装成 MCP 工具
- 用户要为 Fnix 注册新的 MCP 资源（如内部知识库）
- 用户要做 MCP 服务器测试 / 调试

不要用于：构建普通 Python 包（用普通 scaffold）、构建 Web 服务（用 frontend-design）。

## 工作流程

1. **意图识别**：从用户输入提取要暴露的能力（工具名 / 资源 URI / 提示模板）。
2. **设计**：输出 MCP server 草图 — server name / version / tools list（含 input schema）/ resources list / prompts list；让用户确认。
3. **实现**：用 `fnixagent.core.mcp.server` 框架生成 server.py；每个工具用 `@mcp.tool()` 装饰器，input schema 用 pydantic 模型。
4. **测试**：用 `fnixagent.core.mcp.client.MCPClient` 做本地连通性测试（list_tools / call_tool / get_resource）。
5. **注册**：通过 `fnixagent.core.mcp.registry.ToolRegistry.register` 把 MCP server 注册到 Fnix；trust 策略用 `core/mcp/trust.py`。
6. **交付**：写入 `.fnix/artifacts/<slug>/server.py` + `manifest.json`，返回路径与工具清单。

## 输出契约

- `output_format: py`（含 `server.py` + `manifest.json`）
- 产物路径：`.fnix/artifacts/<task_slug>/server.py` + `.fnix/artifacts/<task_slug>/manifest.json`
- manifest schema：
  ```json
  {
    "server_name": str,
    "version": str,
    "tools": [{"name": str, "description": str, "input_schema": {...}}],
    "resources": [{"uri": str, "mime_type": str}],
    "prompts": [{"name": str, "template": str}]
  }
  ```
- 安全约束：所有工具必须有 input_schema（pydantic 模型）；禁止 `Any` 类型参数
- Trust：新 MCP server 默认 `trust_level="untrusted"`，需用户在配置中显式提升
- 失败时不写盘，返回错误说明

## Fnix 集成点

- 底层实现：`fnixagent.core.mcp.server` + `fnixagent.core.mcp.registry.ToolRegistry`
- 工具注册：`mcp-builder.scaffold` / `mcp-builder.add_tool` / `mcp-builder.add_resource` / `mcp-builder.add_prompt` / `mcp-builder.test` / `mcp-builder.register`
- Trust：`core/mcp/trust.py` 管理 MCP server 信任级别
- 客户端：`core/mcp/client.py` 的 `MCPClient` 用于本地测试
- 模式：Code 模式 — 写盘前 diff 给用户审阅；产物落 `.fnix/artifacts/`
- 与 SkillInstaller 协作：MCP server 可作为 skill 通过 market 安装

## 示例

**用户**：构建一个 MCP server，暴露「查询天气」和「查询股票」两个工具。

**Skill 执行**：
1. `mcp-builder.scaffold(name="finance-mcp", version="1.0.0")`
2. 设计 tools：
   - `get_weather(city: str) -> WeatherInfo`
   - `get_stock(symbol: str) -> StockInfo`
3. `mcp-builder.add_tool(name="get_weather", input_schema=WeatherQuery, handler=...)`
4. `mcp-builder.add_tool(name="get_stock", input_schema=StockQuery, handler=...)`
5. `mcp-builder.test()` 用 MCPClient 调 `list_tools` / `call_tool("get_weather", {"city": "上海"})`
6. `mcp-builder.register(trust_level="trusted")` 注册到 Fnix
7. 返回 `.fnix/artifacts/finance-mcp/server.py` + `manifest.json`
