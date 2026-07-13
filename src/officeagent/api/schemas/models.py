"""
API 请求/响应模型 - Pydantic 数据验证。
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 通用响应
# ---------------------------------------------------------------------------


class BaseResponse(BaseModel):
    """基础响应模型。"""

    success: bool = True
    message: str = ""
    data: Optional[Any] = None
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    """错误响应模型。"""

    success: bool = False
    error: str
    detail: Optional[str] = None
    code: Optional[int] = None


# ---------------------------------------------------------------------------
# 用户与鉴权
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    """创建用户请求。"""

    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_\u4e00-\u9fa5]+$",
                          description="用户名:3-64位,支持字母/数字/下划线/中文")
    email: Optional[str] = Field(None, max_length=128, pattern=r"^[\w.+-]+@[\w-]+\.[\w.-]+$",
                                  description="邮箱(可选,需符合标准格式)")
    password: str = Field(..., min_length=6, max_length=128,
                          description="密码:6-128位")
    role: str = Field("user", pattern="^(user|admin)$")


class UserLogin(BaseModel):
    """用户登录请求。

    Phase 0.4 起 password 字段支持两种格式:
      1. 明文密码(向后兼容,旧客户端 / 测试用)
      2. RSA-2048 加密后的 Base64 密文(新客户端用 /auth/pubkey 公钥加密)
    服务端通过 is_password_encrypted 字段区分。
    """

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=4096)  # 加密后较长
    is_password_encrypted: bool = Field(
        False,
        description="密码是否经 RSA 公钥加密。True 时服务端会先解密再校验。",
    )
    client_uuid: Optional[str] = Field(
        None,
        description="客户端设备 UUID(用于设备指纹绑定,首次登录后由客户端生成并持久化)",
    )


class UserResponse(BaseModel):
    """用户响应。"""

    id: int
    username: str
    email: Optional[str]
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    """Token 响应(向后兼容,仅返回 access_token)。

    Phase 0.4 起新增 refresh_token 与 refresh_expires_in 字段,
    旧客户端可忽略。
    """

    access_token: str
    refresh_token: Optional[str] = None        # Phase 0.4 新增
    token_type: str = "bearer"
    expires_in: int = 2 * 3600                 # Access Token 2h
    refresh_expires_in: Optional[int] = 7 * 24 * 3600  # Refresh Token 7d


class RefreshTokenRequest(BaseModel):
    """Refresh Token 请求(用 Refresh Token 换新 Access Token)。"""

    refresh_token: str = Field(..., min_length=1, max_length=4096)
    client_uuid: Optional[str] = Field(
        None,
        description="客户端设备 UUID(必须与登录时一致,用于设备指纹校验)",
    )


class LDAPLoginRequest(BaseModel):
    """LDAP 域账号登录请求(Phase 2.2)。"""

    username: str = Field(..., min_length=1, max_length=128, description="域账号用户名")
    password: str = Field(..., min_length=1, max_length=4096)
    client_uuid: Optional[str] = Field(None, description="客户端设备 UUID")


# ---------------------------------------------------------------------------
# Phase 2.3: SSO 单点登录(OAuth2.0 / SAML)
# ---------------------------------------------------------------------------


class OAuthAuthorizeRequest(BaseModel):
    """OAuth 授权请求(获取授权 URL)。"""
    provider_code: str = Field(..., min_length=1, max_length=64,
                                description="OAuth provider 标识(github/google/自定义)")
    redirect_uri: Optional[str] = Field(None, max_length=512,
                                         description="回调地址(可选,覆盖配置)")
    client_uuid: Optional[str] = Field(None, description="客户端设备 UUID")


class OAuthCallbackRequest(BaseModel):
    """OAuth 回调请求(用 code 换 token + 拉用户信息)。"""
    provider_code: str = Field(..., min_length=1, max_length=64)
    code: str = Field(..., min_length=1, max_length=4096, description="授权码")
    state: Optional[str] = Field(None, max_length=256, description="state / RelayState")
    client_uuid: Optional[str] = Field(None, description="客户端设备 UUID")


class SAMLLoginRequest(BaseModel):
    """SAML SP 发起登录请求(生成 AuthnRequest)。

    provider_code 在 URL path 中,无需在 body 重复。
    """
    client_uuid: Optional[str] = Field(None, description="客户端设备 UUID")


class SAMLACSRequest(BaseModel):
    """SAML ACS 请求(解析 IdP POST 的 SAMLResponse)。

    provider_code 在 URL path 中,无需在 body 重复。
    """
    saml_response: str = Field(..., min_length=1,
                                description="Base64 编码的 SAMLResponse")
    relay_state: Optional[str] = Field(None, max_length=512,
                                       description="RelayState(CSRF / 回调上下文)")
    client_uuid: Optional[str] = Field(None, description="客户端设备 UUID")


class MFALoginChallengeResponse(BaseModel):
    """登录时返回的 MFA Challenge(指示客户端需完成 MFA)。

    登录接口在检测到用户启用 MFA 后,不再返回 TokenPair,
    而是返回此对象(mfa_required=true + mfa_token + factors)。
    客户端引导用户输入验证码后,调 /auth/mfa/verify 完成登录。
    """
    mfa_required: bool = True
    mfa_token: str = Field(..., description="MFA Challenge Token(5min 有效,用于 /auth/mfa/verify)")
    factors: list[str] = Field(..., description="待验证的因子类型(如 ['totp','recovery'])")
    expires_in: int = Field(300, description="Challenge Token 有效期(秒)")


class MFASetupRequest(BaseModel):
    """MFA 因子初始化(TOTP)。"""
    factor_type: str = Field("totp", pattern="^(totp|sms|email)$",
                              description="因子类型:totp / sms / email")
    account_name: Optional[str] = Field(None, max_length=128,
                                         description="TOTP 显示名(默认用邮箱或用户名)")


class MFASetupResponse(BaseModel):
    """MFA 初始化响应(返回 secret + QR URI,客户端扫码后调 /mfa/enable 确认)。"""
    factor_type: str
    secret: str = Field(..., description="Base32 TOTP secret(只显示一次)")
    qr_uri: str = Field(..., description="otpauth:// URI(供二维码扫描)")
    factors: list[str] = Field(default_factory=list, description="用户已启用的因子列表")


class MFAEnableRequest(BaseModel):
    """启用 MFA 因子(验证首个 code 确认 setup)。"""
    factor_type: str = Field("totp", pattern="^(totp|sms|email)$")
    secret: Optional[str] = Field(None, max_length=128,
                                   description="TOTP secret(setup 时返回)")
    code: str = Field(..., min_length=4, max_length=32,
                      description="验证码(TOTP 6 位 / OTP 6 位)")
    phone: Optional[str] = Field(None, max_length=32,
                                  description="SMS 因子的手机号(setup 时绑定)")
    email: Optional[str] = Field(None, max_length=128,
                                  description="EMAIL 因子的邮箱(setup 时绑定)")


class MFADisableRequest(BaseModel):
    """禁用 MFA 因子(需密码二次确认)。"""
    factor_id: Optional[int] = Field(None, description="指定因子 ID(为空则禁用所有)")
    password: Optional[str] = Field(None, max_length=4096,
                                     description="密码二次确认(防止 session 劫持)")
    is_password_encrypted: bool = Field(False, description="密码是否经 RSA 加密")


class MFAVerifyRequest(BaseModel):
    """MFA 验证(登录流程中完成 MFA)。"""
    mfa_token: str = Field(..., min_length=1, max_length=4096,
                            description="登录时返回的 MFA Challenge Token")
    factor_type: str = Field(..., pattern="^(totp|sms|email|recovery)$",
                              description="本次使用的因子类型")
    code: str = Field(..., min_length=1, max_length=64,
                      description="验证码 / 恢复码")
    challenge_id: Optional[str] = Field(None, max_length=128,
                                         description="OTP challenge ID(短信/邮箱)")
    client_uuid: Optional[str] = Field(None, description="客户端设备 UUID")


class MFASendCodeRequest(BaseModel):
    """发送 OTP(短信/邮箱)。"""
    factor_type: str = Field(..., pattern="^(sms|email)$")
    target: Optional[str] = Field(None, max_length=128,
                                    description="目标手机号/邮箱(为空则用已绑定的)")
    mfa_token: Optional[str] = Field(None, max_length=4096,
                                       description="登录中传递(校验权限)")


class MFAEnforcementRequest(BaseModel):
    """MFA 强制策略配置(管理员)。"""
    role: str = Field(..., min_length=1, max_length=64,
                       description="角色名(如 admin / finance)")
    factor_type: str = Field("any", pattern="^(totp|sms|email|any)$",
                              description="要求的因子类型(any=任意一种即可)")
    enabled: bool = True


# ---------------------------------------------------------------------------
# Phase 3.0: 手机号验证码独立登录(国内)
# ---------------------------------------------------------------------------


class SmsSendCodeRequest(BaseModel):
    """发送短信验证码(手机号登录)。"""

    phone: str = Field(
        ...,
        min_length=11,
        max_length=11,
        pattern=r"^1[3-9]\d{9}$",
        description="中国大陆手机号(11 位)",
    )


class SmsLoginRequest(BaseModel):
    """手机号验证码登录请求。"""

    phone: str = Field(
        ...,
        min_length=11,
        max_length=11,
        pattern=r"^1[3-9]\d{9}$",
        description="中国大陆手机号(11 位)",
    )
    code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6 位数字验证码",
    )
    client_uuid: Optional[str] = Field(None, description="客户端设备 UUID")


class PublicKeyResponse(BaseModel):
    """RSA 公钥响应(供客户端加密密码)。"""

    public_key: str = Field(..., description="PEM 格式 RSA-2048 公钥")
    key_id: str = Field(..., description="密钥 ID(用于轮换时客户端感知)")
    algorithm: str = "RSA-2048-OAEP-SHA256"
    expires_at: Optional[str] = Field(
        None, description="公钥过期时间(ISO 8601),None 表示长期有效"
    )


# ---------------------------------------------------------------------------
# 会话与消息
# ---------------------------------------------------------------------------


class SessionCreate(BaseModel):
    """创建会话请求。"""

    title: Optional[str] = None
    context: Optional[dict] = None


class SessionResponse(BaseModel):
    """会话响应。"""

    id: int
    title: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    """创建消息请求。"""

    session_id: int
    content: str
    content_type: str = "text"


class MessageResponse(BaseModel):
    """消息响应。"""

    id: int
    session_id: int
    role: str
    content: str
    content_type: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Agent 对话
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Agent对话请求。"""

    session_id: Optional[int] = None  # 可选,不传则创建新会话
    user_input: str = Field(..., min_length=1, max_length=10000)
    context: Optional[dict] = None  # 任务上下文
    stream: bool = False  # 是否流式输出


class ChatResponse(BaseModel):
    """Agent对话响应。"""

    session_id: int
    message_id: int
    response: str
    trace_id: str
    duration_ms: float
    stats: dict = Field(default_factory=dict)


class StreamChunk(BaseModel):
    """流式输出块。"""

    chunk_type: str  # text/thought/action/observation
    content: str
    done: bool = False


# ---------------------------------------------------------------------------
# 文档操作
# ---------------------------------------------------------------------------


class DocumentUpload(BaseModel):
    """文档上传请求。"""

    name: str
    doc_type: str  # paper/docx/pdf/markdown/chart
    metadata: Optional[dict] = None


class DocumentResponse(BaseModel):
    """文档响应。"""

    id: int
    name: str
    doc_type: str
    source: str
    object_key: Optional[str]
    created_at: datetime


class DocumentProcess(BaseModel):
    """文档处理请求。"""

    document_id: int
    operation: str  # summarize/extract_tables/convert/...
    params: Optional[dict] = None


# ---------------------------------------------------------------------------
# 任务管理
# ---------------------------------------------------------------------------


class TaskCreate(BaseModel):
    """创建任务请求。"""

    session_id: int = Field(..., ge=1, description="关联会话 ID")
    intent: str = Field(..., min_length=1, max_length=500, description="任务意图描述")
    reasoning_mode: str = Field("react", pattern="^(react|plan_execute|self_reflect)$",
                                description="推理模式")


class TaskResponse(BaseModel):
    """任务响应。"""

    id: int
    session_id: int
    intent: str
    reasoning_mode: str
    status: str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]


class TaskStatus(BaseModel):
    """任务状态查询。"""

    task_id: int
    status: str
    progress: float  # 0.0 - 1.0
    current_step: Optional[int]
    total_steps: Optional[int]


# ---------------------------------------------------------------------------
# 工具管理
# ---------------------------------------------------------------------------


class ToolRegister(BaseModel):
    """注册工具请求。"""

    name: str
    description: str
    category: str
    input_schema: dict
    output_schema: Optional[dict] = None
    permission_level: str = "low"
    timeout_ms: int = 30000
    rate_limit: Optional[int] = None


class ToolResponse(BaseModel):
    """工具响应。"""

    id: int
    name: str
    description: str
    category: str
    enabled: bool
    version: str


class ToolExecutionRequest(BaseModel):
    """工具执行请求。"""

    tool_name: str
    arguments: dict
    task_id: Optional[int] = None
    step_id: Optional[int] = None


class ToolExecutionResponse(BaseModel):
    """工具执行响应。"""

    execution_id: int
    tool_name: str
    status: str
    result: Optional[dict]
    duration_ms: Optional[int]
    error: Optional[str]


# ---------------------------------------------------------------------------
# 反馈与计费
# ---------------------------------------------------------------------------


class FeedbackCreate(BaseModel):
    """创建反馈请求。"""

    message_id: int
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    tags: Optional[list[str]] = None


class BillingQuery(BaseModel):
    """计费查询请求。"""

    user_id: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class BillingResponse(BaseModel):
    """计费响应。"""

    total_tokens_input: int
    total_tokens_output: int
    total_cost: float
    records: list[dict] = Field(default_factory=list)