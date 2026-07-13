# ====================================================================
# OfficeAgent OPA 策略(AgentOS 治理层)
# ====================================================================
# 2026 共识:"智能体必须关进制度的笼子里"
# 用 Rego 语言定义 Agent 操作边界,非技术合规人员可配置
# 参考: AWS Cedar 策略格式(未来支持)
# ====================================================================

# ------------------------------------------------------------------
# 包声明
# ------------------------------------------------------------------
package officeagent.agentos

# ------------------------------------------------------------------
# 默认策略:默认拒绝(最小权限原则)
# ------------------------------------------------------------------
default allow = false

# ------------------------------------------------------------------
# 输入结构
# ------------------------------------------------------------------
# input = {
#   "syscall": "fs.read",
#   "args": {"path": "/context/agent-001/..."},
#   "caller_pid": "agent-001",
#   "caller_priority": 15,
#   "caller_capabilities": ["fs.read", "tool.invoke"],
#   "caller_parent_pid": "agent-000",
#   "timestamp": "2026-07-13T..."
# }

# ------------------------------------------------------------------
# 规则1:允许读取自己上下文目录
# ------------------------------------------------------------------
allow {
    input.syscall == "fs.read"
    startswith(input.args.path, concat("/", ["/context", input.caller_pid]))
}

# ------------------------------------------------------------------
# 规则2:允许写入自己上下文目录
# ------------------------------------------------------------------
allow {
    input.syscall == "fs.write"
    startswith(input.args.path, concat("/", ["/context", input.caller_pid]))
}

# ------------------------------------------------------------------
# 规则3:INTERACTIVE 优先级 Agent 可调用 LLM
# ------------------------------------------------------------------
allow {
    input.syscall == "llm.complete"
    input.caller_priority >= 10
}

# ------------------------------------------------------------------
# 规则4:REALTIME 优先级 Agent 可流式推理
# ------------------------------------------------------------------
allow {
    input.syscall == "llm.stream"
    input.caller_priority >= 15
}

# ------------------------------------------------------------------
# 规则5:INTERACTIVE+ 可调用计算机使用(高危)
# ------------------------------------------------------------------
allow {
    input.syscall == "computer.use"
    input.caller_priority >= 15
    "computer.use" in input.caller_capabilities
}

# ------------------------------------------------------------------
# 规则6:BACKGROUND Agent 禁止 shell 执行
# ------------------------------------------------------------------
deny[msg] {
    input.syscall == "shell.exec"
    input.caller_priority < 10
    msg := sprintf("BACKGROUND agent %s cannot execute shell", [input.caller_pid])
}

# ------------------------------------------------------------------
# 规则7:子 Agent 不能超越父 Agent 能力
# ------------------------------------------------------------------
deny[msg] {
    input.syscall == "tool.invoke"
    tool := input.args.tool
    not tool in input.caller_capabilities
    msg := sprintf("Agent %s lacks capability for tool %s", [input.caller_pid, tool])
}

# ------------------------------------------------------------------
# 规则8:网络访问需显式能力
# ------------------------------------------------------------------
allow {
    input.syscall == "web.search"
    "web.search" in input.caller_capabilities
}

allow {
    input.syscall == "web.fetch"
    "web.fetch" in input.caller_capabilities
}

# ------------------------------------------------------------------
# 规则9:Agent 间通信(A2A)需注册
# ------------------------------------------------------------------
allow {
    input.syscall == "ipc.send"
    input.args.target in registered_agents
}

# 注册的 Agent 列表(运行时动态更新)
registered_agents := {
    "officeagent-doc-parser",
    "officeagent-knowledge",
    "officeagent-agent-runner",
    "officeagent-tool-executor",
}

# ------------------------------------------------------------------
# 规则10:Durable Execution 检查点不受限(系统级)
# ------------------------------------------------------------------
allow {
    input.syscall == "schedule"
    input.caller_pid == "kernel"
}

# ------------------------------------------------------------------
# 辅助:综合决策
# ------------------------------------------------------------------
decision := {
    "allow": allow,
    "deny": deny,
}
