"""
合规与安全引擎 (Security Engine)。

统一安全入口,组合四大子模块:
  - SensitiveDetector: 敏感词检测(DFA 自动机)
  - InjectionGuard: Prompt 注入防护(多策略正则)
  - ContentModerator: 输出内容审核(有害内容/PII 泄露)
  - Desensitizer: 数据脱敏(手机/邮箱/身份证等)
  - SecurityEngine: 总控,串联输入安全与输出审核

P0 安全模块扩展(参考 Anthropic 三层防御 + OWASP ASI Top 10):
  - SandboxExecutor: 跨平台 OS 级执行沙箱(Windows Job Object / Linux bwrap)
  - ToolAuditor: 工具语义审计层(路径越界/破坏性关键词/参数类型校验)
  - ImpactTracker: 影响溯源系统(before/after 快照 + 一键回滚)
  - SecretManager: 凭证治理(环境变量/轮换/dev fallback)
  - KDFManager: 主密钥分离(HKDF-SHA256 派生 + LRU 缓存)

P1 安全模块:
  - LLMJudge:        LLM 输出侧裁判(注入检测 / 工具调用审查 / 数据外泄防护)
  - ToolWhitelist:   任务粒度工具白名单(基于 task_type 限制可调用工具)
  - DocumentSigner:  OOXML 文档数字签名(RSA-2048-SHA256 / SHA256-checksum 降级)

P2 密码与签名模块(参考 GmSSL/pyca-cryptography/OWASP ASI06/ASI07):
  - CryptoProvider:  国密双栈密码学接口(SM2/SM3/SM4 与 RSA/SHA256/AES 运行时切换)
  - MemorySigner:    记忆层签名防污染(HMAC 签名 + 速率限制 + 验签审计)
  - A2ASigner:       A2A 通信签名(nonce + timestamp 防 replay + trust store)

P2 安全模块(检测引擎,参考 Elastic ML / Sigma / Gitleaks):
  - BehaviorAnalyzer: UEBA 行为基线引擎(IsolationForest + 统计降级,触发 step-up MFA)
  - RuleEngine:       Sigma 风格规则引擎(YAML 声明式 + watchdog 热加载 + MITRE 标签)
  - SecretScanner:    密钥泄露扫描(正则规则集 + 香农熵 + 自动脱敏)

P2/P3 安全模块(响应与合规,参考 Shuffle SOAR / MyDLP / auditd / SLSA):
  - PlaybookEngine:     SOAR 响应剧本引擎(YAML 声明式 + 人工审批 + 异步执行)
  - DLPGateway:         DLP 出口拦截(PII 检测 + 关键词词典 + 脱敏/阻断/告警)
  - AuditChain:         链式哈希审计 + WORM(Merkle 树批量校验 + 签名快照)
  - SupplyChainVerifier: 插件供应链校验(SHA256 + RSA 签名 + SBOM + pip-audit CVE)

P2 安全模块(沙箱与零信任增强,参考 OpenAI Codex Sandbox / SPIFFE / HashiCorp Vault):
  - SandboxLevel:    分层沙箱档位(ALLOW/CONFIRM/UNTRUSTED + MicroVM 降级)
  - IdentityBroker:  SPIFFE 风格工作负载身份(x509-SVID + JWT 降级 + 自动旋转)
  - LeaseManager:    密钥租约 + Cubbyhole(单次 token + 绑定 task_id + 惰性清理)
"""
from fnixagent.core.security.sensitive import SensitiveDetector
from fnixagent.core.security.injection import InjectionGuard, InjectionCheckResult
from fnixagent.core.security.moderation import ContentModerator, ModerationResult
from fnixagent.core.security.desensitize import Desensitizer
from fnixagent.core.security.engine import (
    SecurityEngine,
    SecurityCheckResult,
)
# P0 安全模块
from fnixagent.core.security.sandbox import (
    SandboxConfig,
    SandboxResult,
    SandboxExecutor,
    SandboxLevel,
)
from fnixagent.core.security.auditor import (
    AuditRecord,
    AuditReport,
    ToolAuditor,
)
from fnixagent.core.security.impact import (
    Snapshot,
    ImpactRecord,
    ImpactTracker,
)
from fnixagent.core.security.secrets import (
    SecretSource,
    SecretValue,
    SecretManager,
)
from fnixagent.core.security.kdf import (
    DerivedKey,
    KDFManager,
)
# P1 安全模块
from fnixagent.core.security.judge import (
    JudgeVerdict,
    JudgeConfig,
    LLMJudge,
)
from fnixagent.core.security.whitelist import (
    ToolGrant,
    WhitelistDecision,
    ToolWhitelist,
    DEFAULT_TASK_TOOLS,
)
from fnixagent.core.security.signing import (
    SignatureInfo,
    VerifyResult,
    DocumentSigner,
)
# P2 安全模块(检测引擎)
from fnixagent.core.security.behavior import (
    BehaviorFeatures,
    BehaviorBaseline,
    AnomalyScore,
    BehaviorAnalyzer,
)
from fnixagent.core.security.rules import (
    SigmaRule,
    RuleMatch,
    RuleEngine,
)
from fnixagent.core.security.secret_scan import (
    SecretFinding,
    ScanResult,
    SecretScanner,
)
# P2/P3 安全模块(响应与合规)
from fnixagent.core.security.soar import (
    PlaybookAction,
    PlaybookStep,
    Playbook,
    PlaybookExecution,
    PlaybookEngine,
)
from fnixagent.core.security.dlp import (
    DLPAction,
    DLPPolicy,
    DLPDetection,
    DLPResult,
    DLPGateway,
)
from fnixagent.core.security.audit_chain import (
    ChainEntry,
    MerkleProof,
    ChainSnapshot,
    AuditChain,
)
from fnixagent.core.security.supply_chain import (
    PackageInfo,
    VerificationResult,
    SBOMEntry,
    SupplyChainVerifier,
)
# P2 安全模块(沙箱与零信任增强)
from fnixagent.core.security.identity import (
    SVID,
    AgentIdentity,
    NetworkPolicy,
    IdentityBroker,
)
from fnixagent.core.security.leases import (
    LeasedSecret,
    CubbyholeToken,
    LeaseManager,
    LeaseExpiredError,
)
# P2 密码与签名模块(国密双栈 + 记忆防污染 + A2A 通信签名)
from fnixagent.core.security.crypto_provider import (
    AlgorithmSuite,
    CryptoConfig,
    CryptoProvider,
)
from fnixagent.core.security.memory_signing import (
    SignedMemory,
    MemorySignerConfig,
    MemorySigner,
)
from fnixagent.core.security.a2a_signing import (
    SignedEnvelope,
    AgentIdentity as A2AAgentIdentity,  # 别名避免与 identity.AgentIdentity 冲突
    A2ASigner,
)

__all__ = [
    # 基础安全
    "SensitiveDetector",
    "InjectionGuard",
    "InjectionCheckResult",
    "ContentModerator",
    "ModerationResult",
    "Desensitizer",
    "SecurityEngine",
    "SecurityCheckResult",
    # P0-1: OS 级执行沙箱
    "SandboxConfig",
    "SandboxResult",
    "SandboxExecutor",
    "SandboxLevel",
    # P0-2: 工具语义审计
    "AuditRecord",
    "AuditReport",
    "ToolAuditor",
    # P0-3: 影响溯源
    "Snapshot",
    "ImpactRecord",
    "ImpactTracker",
    # P0-4: 凭证治理
    "SecretSource",
    "SecretValue",
    "SecretManager",
    # P0-5: KDK 分离
    "DerivedKey",
    "KDFManager",
    # P1-1: LLM 输出裁判
    "JudgeVerdict",
    "JudgeConfig",
    "LLMJudge",
    # P1-2: 任务粒度工具白名单
    "ToolGrant",
    "WhitelistDecision",
    "ToolWhitelist",
    "DEFAULT_TASK_TOOLS",
    # P1-3: OOXML 文档数字签名
    "SignatureInfo",
    "VerifyResult",
    "DocumentSigner",
    # P2-1: UEBA 行为基线引擎
    "BehaviorFeatures",
    "BehaviorBaseline",
    "AnomalyScore",
    "BehaviorAnalyzer",
    # P2-2: Sigma 风格规则引擎
    "SigmaRule",
    "RuleMatch",
    "RuleEngine",
    # P2-3: 密钥泄露扫描
    "SecretFinding",
    "ScanResult",
    "SecretScanner",
    # P2-4: SPIFFE 风格工作负载身份
    "SVID",
    "AgentIdentity",
    "NetworkPolicy",
    "IdentityBroker",
    # P2-5: 密钥租约 + Cubbyhole
    "LeasedSecret",
    "CubbyholeToken",
    "LeaseManager",
    "LeaseExpiredError",
    # P2/P3-1: SOAR 响应剧本引擎
    "PlaybookAction",
    "PlaybookStep",
    "Playbook",
    "PlaybookExecution",
    "PlaybookEngine",
    # P2/P3-2: DLP 出口拦截
    "DLPAction",
    "DLPPolicy",
    "DLPDetection",
    "DLPResult",
    "DLPGateway",
    # P2/P3-3: 链式哈希审计 + WORM
    "ChainEntry",
    "MerkleProof",
    "ChainSnapshot",
    "AuditChain",
    # P2/P3-4: 插件供应链校验
    "PackageInfo",
    "VerificationResult",
    "SBOMEntry",
    "SupplyChainVerifier",
    # P2-6: 国密双栈密码学接口
    "AlgorithmSuite",
    "CryptoConfig",
    "CryptoProvider",
    # P2-7: 记忆层签名防污染
    "SignedMemory",
    "MemorySignerConfig",
    "MemorySigner",
    # P2-8: A2A 通信签名
    "SignedEnvelope",
    "A2AAgentIdentity",
    "A2ASigner",
]
