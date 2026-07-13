"""爬虫客户端配置。

从环境变量或 YAML 配置文件加载爬虫系统连接信息。
OfficeAgent 端不存储任何数据,配置仅含连接信息(地址/认证/超时/重试)。

核心约束(瘦客户端):
  - 配置中不含任何数据存储路径
  - 不缓存/不落盘/不本地存储

加载优先级(load_config):
  环境变量 → YAML(若 OFFICEAGENT_CRAWLER_CONFIG 指向的文件存在)→ overrides 覆盖

环境变量命名约定:
  OFFICEAGENT_CRAWLER_BASE_URL
  OFFICEAGENT_CRAWLER_API_KEY
  OFFICEAGENT_CRAWLER_API_KEY_HEADER
  OFFICEAGENT_CRAWLER_API_KEY_PREFIX
  OFFICEAGENT_CRAWLER_TIMEOUT
  OFFICEAGENT_CRAWLER_CONNECT_TIMEOUT
  OFFICEAGENT_CRAWLER_MAX_RETRIES
  OFFICEAGENT_CRAWLER_RETRY_BACKOFF
  OFFICEAGENT_CRAWLER_RETRY_MAX_DELAY
  OFFICEAGENT_CRAWLER_RETRY_ON_STATUS   (逗号分隔,如 "500,502,503")
  OFFICEAGENT_CRAWLER_VERIFY_SSL        (1/true/yes/on)
  OFFICEAGENT_CRAWLER_USER_AGENT
  OFFICEAGENT_CRAWLER_MAX_RESPONSE_SIZE
  OFFICEAGENT_CRAWLER_CONFIG            (YAML 配置文件路径,可选)

可选依赖:
  - yaml:YAML 配置加载(缺失时 load_config_from_yaml 抛 ImportError)
"""
from __future__ import annotations

import dataclasses
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

# 尝试导入 yaml(与 core/role_loader.py 一致的降级模式)
try:
    import yaml  # type: ignore
    _HAS_YAML = True
except ImportError:  # pragma: no cover
    _HAS_YAML = False
    yaml = None  # type: ignore

_logger = logging.getLogger(__name__)

# 环境变量前缀
_ENV_PREFIX = "CRAWLER_"

# 字段类型分组(用于环境变量类型转换)
_STR_FIELDS = {
    "base_url",
    "api_key",
    "api_key_header",
    "api_key_prefix",
    "user_agent",
}
_FLOAT_FIELDS = {"timeout", "connect_timeout", "retry_backoff", "retry_max_delay"}
_INT_FIELDS = {"max_retries", "max_response_size"}
_BOOL_FIELDS = {"verify_ssl"}


@dataclass
class CrawlerConfig:
    """爬虫系统客户端配置。

    所有字段均可从环境变量或 YAML 配置文件加载。
    OfficeAgent 端不存储任何数据,配置仅含连接信息。

    Attributes:
        base_url:           爬虫系统 API 地址
        api_key:            Bearer Token 认证(敏感:日志脱敏)
        api_key_header:     认证头名称
        api_key_prefix:     认证前缀(如 "Bearer")
        timeout:            请求超时(秒)
        connect_timeout:    连接超时(秒)
        max_retries:        最大重试次数(不含首次请求)
        retry_backoff:      指数退避起始(秒)
        retry_max_delay:    重试最大延迟(秒)
        retry_on_status:    触发重试的状态码
        verify_ssl:         是否校验 SSL 证书
        user_agent:         User-Agent 字符串
        max_response_size:  响应体上限(字节,防 OOM)

    Raises:
        ValueError: timeout/connect_timeout/retry_max_delay/max_response_size <= 0,
                    或 max_retries < 0,或 base_url 为空
    """

    base_url: str = "http://localhost:9100"
    api_key: Optional[str] = None
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer"
    timeout: float = 60.0
    connect_timeout: float = 10.0
    max_retries: int = 3
    retry_backoff: float = 0.5
    retry_max_delay: float = 30.0
    retry_on_status: tuple[int, ...] = (500, 502, 503, 504, 429)
    verify_ssl: bool = True
    user_agent: str = "OfficeAgent-Crawler/1.0"
    max_response_size: int = 50 * 1024 * 1024  # 50MB

    def __post_init__(self) -> None:
        """构造后字段范围校验。"""
        if not isinstance(self.base_url, str) or not self.base_url.strip():
            raise ValueError("CrawlerConfig.base_url 必须为非空字符串")
        if not isinstance(self.timeout, (int, float)) or self.timeout <= 0:
            raise ValueError(f"CrawlerConfig.timeout 必须 > 0, 实为 {self.timeout}")
        if not isinstance(self.connect_timeout, (int, float)) or self.connect_timeout <= 0:
            raise ValueError(
                f"CrawlerConfig.connect_timeout 必须 > 0, 实为 {self.connect_timeout}"
            )
        if not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise ValueError(
                f"CrawlerConfig.max_retries 必须 >= 0, 实为 {self.max_retries}"
            )
        if not isinstance(self.retry_backoff, (int, float)) or self.retry_backoff < 0:
            raise ValueError(
                f"CrawlerConfig.retry_backoff 必须 >= 0, 实为 {self.retry_backoff}"
            )
        if not isinstance(self.retry_max_delay, (int, float)) or self.retry_max_delay <= 0:
            raise ValueError(
                f"CrawlerConfig.retry_max_delay 必须 > 0, 实为 {self.retry_max_delay}"
            )
        if not isinstance(self.max_response_size, int) or self.max_response_size <= 0:
            raise ValueError(
                f"CrawlerConfig.max_response_size 必须为正整数, 实为 {self.max_response_size}"
            )
        if not isinstance(self.retry_on_status, (tuple, list)):
            raise TypeError(
                f"CrawlerConfig.retry_on_status 必须为 tuple/list, 实为 {type(self.retry_on_status).__name__}"
            )
        # YAML 加载时可能是 list,自动转换为 tuple(不可变)
        if isinstance(self.retry_on_status, list):
            object.__setattr__(self, "retry_on_status", tuple(self.retry_on_status))


# ---------------------------------------------------------------------------
# 内部:环境变量 / YAML → dict
# ---------------------------------------------------------------------------


def _coerce_bool(value: str) -> bool:
    """字符串 → bool(与 core/config.py 一致)。"""
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_to_dict() -> dict[str, Any]:
    """从 OFFICEAGENT_CRAWLER_ 前缀环境变量读取配置 dict。

    仅返回显式设置的字段(未设置的环境变量不进入 dict)。
    """
    result: dict[str, Any] = {}

    for name in _STR_FIELDS:
        raw = os.environ.get(_ENV_PREFIX + name.upper())
        if raw is not None:
            result[name] = raw

    for name in _FLOAT_FIELDS:
        raw = os.environ.get(_ENV_PREFIX + name.upper())
        if raw is not None and raw.strip():
            try:
                result[name] = float(raw)
            except ValueError as e:
                raise ValueError(
                    f"环境变量 {_ENV_PREFIX}{name.upper()}='{raw}' 无法转为 float"
                ) from e

    for name in _INT_FIELDS:
        raw = os.environ.get(_ENV_PREFIX + name.upper())
        if raw is not None and raw.strip():
            try:
                result[name] = int(raw)
            except ValueError as e:
                raise ValueError(
                    f"环境变量 {_ENV_PREFIX}{name.upper()}='{raw}' 无法转为 int"
                ) from e

    for name in _BOOL_FIELDS:
        raw = os.environ.get(_ENV_PREFIX + name.upper())
        if raw is not None:
            result[name] = _coerce_bool(raw)

    # retry_on_status:逗号分隔的状态码
    raw = os.environ.get(_ENV_PREFIX + "RETRY_ON_STATUS")
    if raw is not None and raw.strip():
        try:
            result["retry_on_status"] = tuple(
                int(x.strip()) for x in raw.split(",") if x.strip()
            )
        except ValueError as e:
            raise ValueError(
                f"环境变量 {_ENV_PREFIX}RETRY_ON_STATUS='{raw}' 必须为逗号分隔的整数"
            ) from e

    return result


def _yaml_to_dict(path: str) -> dict[str, Any]:
    """从 YAML 文件读取配置 dict(过滤未知字段)。

    Args:
        path: YAML 文件路径

    Returns:
        配置 dict(仅含 CrawlerConfig 已知字段)

    Raises:
        ImportError: yaml 未安装
        FileNotFoundError: 文件不存在
        ValueError: YAML 顶层不是 mapping
    """
    if not _HAS_YAML:
        raise ImportError(
            "yaml 未安装,无法加载 YAML 配置(请安装 PyYAML 或 yaml 包)"
        )
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)  # type: ignore
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(
            f"YAML 配置必须是 mapping, 实为 {type(data).__name__}: {path}"
        )
    valid_fields = {f.name for f in dataclasses.fields(CrawlerConfig)}
    return {k: v for k, v in data.items() if k in valid_fields}


# ---------------------------------------------------------------------------
# 公开加载函数
# ---------------------------------------------------------------------------


def load_config_from_env() -> CrawlerConfig:
    """从环境变量加载配置。

    未设置的环境变量使用 CrawlerConfig 默认值。

    Returns:
        CrawlerConfig 实例

    Raises:
        ValueError: 环境变量值非法(类型转换失败或范围校验失败)
    """
    return CrawlerConfig(**_env_to_dict())


def load_config_from_yaml(path: str) -> CrawlerConfig:
    """从 YAML 文件加载配置。

    Args:
        path: YAML 文件路径

    Returns:
        CrawlerConfig 实例

    Raises:
        ImportError: yaml 未安装
        FileNotFoundError: 文件不存在
        ValueError: YAML 格式错误或字段值非法
    """
    return CrawlerConfig(**_yaml_to_dict(path))


def load_config(**overrides: Any) -> CrawlerConfig:
    """加载配置(综合环境变量 / YAML / overrides)。

    加载顺序(后者覆盖前者):
      1. 环境变量(OFFICEAGENT_CRAWLER_*)
      2. YAML(若 OFFICEAGENT_CRAWLER_CONFIG 指向的文件存在)
      3. overrides 关键字参数(None 值被忽略)

    Args:
        **overrides: 覆盖字段(如 base_url=..., timeout=...)

    Returns:
        CrawlerConfig 实例

    Raises:
        ValueError: 字段值非法
        ImportError: 指定了 YAML 但 yaml 未安装
    """
    merged: dict[str, Any] = _env_to_dict()

    yaml_path = os.environ.get(_ENV_PREFIX + "CONFIG", "")
    if yaml_path and yaml_path.strip() and os.path.exists(yaml_path):
        merged.update(_yaml_to_dict(yaml_path))

    # overrides 覆盖(None 值忽略,避免覆盖已加载的值)
    for k, v in overrides.items():
        if v is not None:
            merged[k] = v

    return CrawlerConfig(**merged)
