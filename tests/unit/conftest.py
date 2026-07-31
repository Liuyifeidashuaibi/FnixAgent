"""
tests/unit/conftest.py — 全局单元测试用例的存储隔离夹具。

问题背景
--------
项目默认以 standalone 模式运行, 用户存储走 ``JsonUserStore``, 持久化到仓库内的
``data/standalone/users.json``。该文件在多次测试运行 / 同进程多用例之间会累积用户名,
导致固定用户名的夹具在第 2 次创建时返回 "用户名已存在", 进而级联拖垮 auth / security /
rbac / audit / privacy / sso / sms 等几乎所有依赖 ``get_user_store().create()`` 的测试。

修复方式
--------
为单元测试用例注入一个 autouse 夹具: 每次测试都把 standalone 数据目录重定向到独立的
临时目录, 并重置存储单例。这样每个用例都从空存储起步, 互不干扰, 也完全不触碰产品真实的
``data/standalone/users.json``。
"""

from __future__ import annotations

import tempfile

import pytest


@pytest.fixture(scope="session", autouse=True)
def _seed_openssl_entropy_early():
    """在会话最早期(进程熵源尚新鲜时)初始化 OpenSSL DRBG。

    问题背景
    --------
    在部分 Windows / 受限环境下, OpenSSL 3.x 的默认 DRBG 在**首次**调用
    ``RAND_bytes`` 时才惰性实例化; 若该瞬时 Windows 熵源(BCryptGenRandom)
    返回强度不足, 实例化会永久失败并抛出
    ``cryptography.exceptions.InternalError: ... entropy source strength too weak
    / error instantiating drbg``, 导致后续所有 RSA / 加解密测试在整套用例
    (大量 crypto 操作之后) 中连锁失败 —— 而单独运行这些测试则正常。

    缓解方式
    --------
    在会话启动、任何业务测试之前主动 ``ssl.RAND_bytes`` 一次, 趁进程熵源新鲜时
    完成 DRBG 实例化, 避免其在高负载后才首次触发而踩中瞬时弱熵窗口。
    """
    try:
        import ssl

        # 多次尝试, 容忍瞬时弱熵窗口
        for _ in range(5):
            try:
                ssl.RAND_bytes(32)
                break
            except Exception:
                continue
    except Exception:
        # 某些环境下 ssl 模块未编译 RAND 支持, 忽略即可
        pass


@pytest.fixture(autouse=True)
def _isolate_storage_per_test():
    """隔离 standalone JSON 用户存储, 避免固定用户名夹具跨用例/跨运行冲突。"""
    import fnixagent.services.storage as st
    import fnixagent.services.storage_standalone as sa

    tmp_dir = tempfile.mkdtemp(prefix="fnix-test-")
    sa._DEFAULT_DIR = tmp_dir
    sa._store = None
    st.reset_stores()
    try:
        yield
    finally:
        st.reset_stores()
        sa._store = None
