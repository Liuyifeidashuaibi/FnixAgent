"""缓存适配器。

延迟导入 redis 适配器：standalone 默认不安装 redis（见 requirements-optional.txt），
缺包时 CacheAdapter 置为 None，仅在显式访问时抛出可读错误，不影响 Desktop / CLI 启动。
"""

try:
    from fnixagent.adapters.cache.redis import CacheAdapter
except ImportError:  # redis 未安装（standalone 默认）
    CacheAdapter = None  # type: ignore[assignment]

__all__ = ["CacheAdapter"]
