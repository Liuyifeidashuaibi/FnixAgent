"""zhua-crawler 客户端配置(瘦客户端连接信息)。

从环境变量或 YAML 配置文件加载 ZhuaCrawler 系统连接信息。
OfficeAgent 端不存储任何数据,配置仅含连接信息(地址/认证/超时/重试)。

核心约束(瘦客户端,与 config.py 一致):
  - 配置中不含任何数据存储路径
  - 不缓存/不落盘/不本地存储
  - token / operator_token 视为敏感字段(日志脱敏)

加载优先级(load_zhua_config):
  环境变量 → YAML(若 OFFICEAGENT_ZHUA_CONFIG 指向的文件存在)→ overrides 覆盖

环境变量命名约定(前缀 OFFICEAGENT_ZHUA_):
  OFFICEAGENT_ZHUA_BASE_URL
  OFFICEAGENT_ZHUA_TOKEN                已有 JWT(与 operator_token 二选一,优先)
  OFFICEAGENT_ZHUA_OPERATOR_TOKEN       运维静态令牌(自动调 /v1/token 换 JWT)
  OFFICEAGENT_ZHUA_TIMEOUT              HTTP 超时(秒)
  OFFICEAGENT_ZHUA_MAX_RETRIES          5xx 重试次数(不含首次)
  OFFICEAGENT_ZHUA_USER_AGENT           自定义 UA
  OFFICEAGENT_ZHUA_CONFIG               YAML 配置文件路径(可选)

可选依赖:
  - yaml:YAML 配置加载(缺失时 load_zhua_config_from_yaml 抛 ImportError)

Note:
  与 config.py(CrawlerConfig) 平行存在,二者互不影响:
    - CrawlerConfig 对接旧爬虫系统(/api/v1/* 接口,端口 9100)
    - ZhuaConfig   对接 zhua-crawler 系统(/v1/* 接口,端口 8000)
  Agent 可同时使用两套工具(crawler_* 与 zhua_*)。
"""
from __future__ import annotations

import dataclasses
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

# 尝试导入 yaml(与 core/role_loader.py / config.py 一致的降级模式)
try:
    import yaml  # type: ignore
    _HAS_YAML = True
except ImportError:  # pragma: no cover
    _HAS_YAML = False
    yaml = None  # type: ignore

_logger = logging.getLogger(__name__)

# 环境变量前缀(与 config.py 的 CRAWLER_ 区分,避免字段冲突)
_ENV_PREFIX = "OFFICEAGENT_ZHUA_"

# 字段类型分组(用于环境变量类型转换)
_STR_FIELDS = {"base_url", "token", "operator_token", "user_agent"}
_FLOAT_FIELDS = {"timeout"}
_INT_FIELDS = {"max_retries"}


@dataclass
class ZhuaConfig:
    """zhua-crawler 客户端配置。

    所有字段均可从环境变量或 YAML 配置文件加载。
    OfficeAgent 端不存储任何数据,配置仅含连接信息。

    Attributes:
        base_url:        zhua-crawler API 地址(默认 http://localhost:8000)
        token:           已有 JWT(与 operator_token 二选一,优先使用 token)
        operator_token:  运维静态令牌;提供时 SDK 自动调用 /v1/token 换取 JWT
                         (敏感字段:日志脱敏)
        timeout:         HTTP 超时(秒)
        max_retries:     5xx 重试次数(不含首次请求)
        user_agent:      自定义 User-Agent(None 时用 SDK 默认 zhua-client-python/x.y.z)

    Raises:
        ValueError: timeout <= 0, 或 max_retries < 0, 或 base_url 为空
        TypeError:  字段类型不符
    """

    base_url: str = "http://localhost:8000"
    token: Optional[str] = None
    operator_token: Optional[str] = None
    timeout: float = 60.0
    max_retries: int = 3
    user_agent: Optional[str] = None

    def __post_init__(self) -> None:
        """构造后字段范围校验。"""
        if not isinstance(self.base_url, str) or not self.base_url.strip():
            raise ValueError("ZhuaConfig.base_url 必须为非空字符串")
        if not isinstance(self.timeout, (int, float)) or self.timeout <= 0:
            raise ValueError(f"ZhuaConfig.timeout 必须 > 0, 实为 {self.timeout}")
        if not isinstance(self.max_retries, int) or self.max_retries < 0:
            raise ValueError(
                f"ZhuaConfig.max_retries 必须 >= 0, 实为 {self.max_retries}"
            )
        # token / operator_token 允许 None 或非空 str
        for fname in ("token", "operator_token", "user_agent"):
            val = getattr(self, fname)
            if val is not None and not isinstance(val, str):
                raise TypeError(
                    f"ZhuaConfig.{fname} 必须为 str 或 None, "
                    f"实为 {type(val).__name__}"
                )

    def to_client_kwargs(self) -> dict[str, Any]:
        """转换为 ZhuaClient 构造参数(过滤 None 值)。

        Returns:
            ZhuaClient.__init__ 可接受的 kwargs dict
        """
        kwargs: dict[str, Any] = {
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
        }
        if self.token is not None:
            kwargs["token"] = self.token
        if self.operator_token is not None:
            kwargs["operator_token"] = self.operator_token
        if self.user_agent is not None:
            kwargs["headers"] = {"User-Agent": self.user_agent}
        return kwargs

    def __repr__(self) -> str:
        """脱敏 repr(token / operator_token 不回显明文)。"""
        return (
            f"ZhuaConfig(base_url={self.base_url!r}, "
            f"token={'<set>' if self.token else None!r}, "
            f"operator_token={'<set>' if self.operator_token else None!r}, "
            f"timeout={self.timeout}, max_retries={self.max_retries}, "
            f"user_agent={self.user_agent!r})"
        )


# ---------------------------------------------------------------------------
# 内部:环境变量 / YAML → dict
# ---------------------------------------------------------------------------


def _env_to_dict() -> dict[str, Any]:
    """从 OFFICEAGENT_ZHUA_ 前缀环境变量读取配置 dict。

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

    return result


def _yaml_to_dict(path: str) -> dict[str, Any]:
    """从 YAML 文件读取 zhua 配置 dict(仅读取 zhua: 嵌套段)。

    YAML 结构(crawler.yaml 中共存两套配置,通过段落区分):
        # 顶层属 CrawlerConfig(旧爬虫系统,端口 9100)
        base_url: http://crawler:9100
        timeout: 60.0
        ...

        # zhua: 段属 ZhuaConfig(zhua-crawler 系统,端口 8000)
        zhua:
          base_url: http://zhua:8000
          timeout: 60
          operator_token: xxx

    严格只读取 zhua: 段,绝不读取顶层字段(避免 CrawlerConfig 字段污染
    ZhuaConfig,导致 zhua 客户端错误指向端口 9100)。

    Args:
        path: YAML 文件路径

    Returns:
        配置 dict(仅含 ZhuaConfig 已知字段;无 zhua: 段时返回空 dict)

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

    # 严格只读 zhua: 嵌套段(避免顶层 CrawlerConfig 字段污染)
    zhua_section = data.get("zhua")
    if not isinstance(zhua_section, dict):
        return {}

    valid_fields = {f.name for f in dataclasses.fields(ZhuaConfig)}
    return {k: v for k, v in zhua_section.items() if k in valid_fields}


# ---------------------------------------------------------------------------
# 公开加载函数
# ---------------------------------------------------------------------------


def load_zhua_config_from_env() -> ZhuaConfig:
    """从环境变量加载配置。

    未设置的环境变量使用 ZhuaConfig 默认值。

    Returns:
        ZhuaConfig 实例

    Raises:
        ValueError: 环境变量值非法(类型转换失败或范围校验失败)
    """
    return ZhuaConfig(**_env_to_dict())


def load_zhua_config_from_yaml(path: str) -> ZhuaConfig:
    """从 YAML 文件加载配置。

    Args:
        path: YAML 文件路径

    Returns:
        ZhuaConfig 实例

    Raises:
        ImportError: yaml 未安装
        FileNotFoundError: 文件不存在
        ValueError: YAML 格式错误或字段值非法
    """
    return ZhuaConfig(**_yaml_to_dict(path))


def load_zhua_config(**overrides: Any) -> ZhuaConfig:
    """加载配置(综合环境变量 / YAML / overrides)。

    加载顺序(后者覆盖前者):
      1. 环境变量(OFFICEAGENT_ZHUA_*)
      2. YAML(若 OFFICEAGENT_ZHUA_CONFIG 指向的文件存在;
         若未设置则回退到 config/crawler.yaml 的 zhua: 段)
      3. overrides 关键字参数(None 值被忽略)

    Args:
        **overrides: 覆盖字段(如 base_url=..., timeout=...)

    Returns:
        ZhuaConfig 实例

    Raises:
        ValueError: 字段值非法
        ImportError: 指定了 YAML 但 yaml 未安装
    """
    merged: dict[str, Any] = _env_to_dict()

    # 优先:显式指定的 YAML 文件
    yaml_path = os.environ.get(_ENV_PREFIX + "CONFIG", "")
    if yaml_path and yaml_path.strip() and os.path.exists(yaml_path):
        merged.update(_yaml_to_dict(yaml_path))
    else:
        # 回退:项目根目录 config/crawler.yaml 的 zhua: 段
        # (与 config.py 共用同一 YAML,通过 zhua: 段区分)
        # __file__ = .../src/officeagent/business/crawler/zhua_config.py
        # 上溯 5 级 dirname 到项目根 OFFICEAGENT/
        default_yaml = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.dirname(__file__))
            ))),
            "config", "crawler.yaml",
        )
        if os.path.exists(default_yaml):
            try:
                zhua_section = _yaml_to_dict(default_yaml)
                if zhua_section:
                    merged.update(zhua_section)
            except Exception as e:  # pragma: no cover
                _logger.debug("读取 crawler.yaml 的 zhua 段失败: %s", e)

    # overrides 覆盖(None 值忽略,避免覆盖已加载的值)
    for k, v in overrides.items():
        if v is not None:
            merged[k] = v

    return ZhuaConfig(**merged)
