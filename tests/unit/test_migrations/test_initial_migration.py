"""
Phase 0.3 数据库迁移单元测试。

验证 initial migration 的结构正确性:
- revision / down_revision 标识符
- upgrade() / downgrade() 函数存在
- 通过 alembic offline 模式生成 SQL,校验表/索引/约束数量

不依赖真实 PostgreSQL,使用 `alembic upgrade head --sql` 离线生成 SQL,
然后解析 SQL 文本统计 DDL 语句数量。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # FNIXAGENT/
MIGRATION_FILE = (
    PROJECT_ROOT / "migrations" / "versions" / "20260704_2000_0001_initial_initial_schema.py"
)


# ---------------------------------------------------------------------------
# 静态结构校验(不执行迁移,只检查文件内容)
# ---------------------------------------------------------------------------


class TestMigrationStructure:
    """验证 migration 文件的静态结构。"""

    def test_migration_file_exists(self) -> None:
        """迁移文件存在。"""
        assert MIGRATION_FILE.exists(), f"迁移文件不存在: {MIGRATION_FILE}"

    def test_revision_identifier(self) -> None:
        """revision 标识符为 0001_initial。"""
        text = MIGRATION_FILE.read_text(encoding="utf-8")
        assert 'revision: str = "0001_initial"' in text

    def test_down_revision_is_none(self) -> None:
        """down_revision 为 None(初始迁移)。"""
        text = MIGRATION_FILE.read_text(encoding="utf-8")
        assert "down_revision: Union[str, None] = None" in text

    def test_upgrade_function_defined(self) -> None:
        """upgrade() 函数已定义。"""
        text = MIGRATION_FILE.read_text(encoding="utf-8")
        assert "def upgrade()" in text

    def test_downgrade_function_defined(self) -> None:
        """downgrade() 函数已定义。"""
        text = MIGRATION_FILE.read_text(encoding="utf-8")
        assert "def downgrade()" in text

    def test_all_18_tables_present_in_upgrade(self) -> None:
        """upgrade() 中包含全部 18 张表的 create_table 调用。"""
        text = MIGRATION_FILE.read_text(encoding="utf-8")
        expected_tables = [
            "tenants",
            "users",
            "api_credentials",
            "sessions",
            "messages",
            "tasks",
            "task_steps",
            "tool_executions",
            "tools",
            "documents",
            "knowledge_chunks",
            "entities",
            "entity_relations",
            "reflection_logs",
            "audit_logs",
            "prompt_templates",
            "billing_records",
            "feedbacks",
        ]
        for table in expected_tables:
            # op.create_table("table_name", ...) 或 op.create_table(\n    "table_name",
            assert f'"{table}"' in text, f"表 {table} 未在 upgrade() 中创建"

    def test_all_8_indexes_present_in_upgrade(self) -> None:
        """upgrade() 中包含全部 8 个索引的 create_index 调用。"""
        text = MIGRATION_FILE.read_text(encoding="utf-8")
        expected_indexes = [
            "idx_sessions_user",
            "idx_messages_session",
            "idx_tasks_user_status",
            "idx_tool_exec_task",
            "idx_tool_exec_name_time",
            "idx_docs_user_type",
            "idx_chunks_doc",
            "idx_entities_user_type",
        ]
        for idx in expected_indexes:
            assert idx in text, f"索引 {idx} 未在 upgrade() 中创建"

    def test_all_4_unique_constraints_present(self) -> None:
        """upgrade() 中包含全部 4 个命名唯一约束。"""
        text = MIGRATION_FILE.read_text(encoding="utf-8")
        expected_constraints = [
            "uq_tenant_username",
            "uq_tenant_entity",
            "uq_entity_relation",
            "uq_prompt_template",
        ]
        for uc in expected_constraints:
            assert uc in text, f"唯一约束 {uc} 未在 upgrade() 中创建"

    def test_downgrade_drops_all_tables(self) -> None:
        """downgrade() 中包含全部 18 张表的 drop_table 调用。"""
        text = MIGRATION_FILE.read_text(encoding="utf-8")
        expected_drops = [
            "feedbacks",
            "billing_records",
            "prompt_templates",
            "audit_logs",
            "reflection_logs",
            "entity_relations",
            "entities",
            "knowledge_chunks",
            "documents",
            "tools",
            "tool_executions",
            "task_steps",
            "tasks",
            "messages",
            "sessions",
            "api_credentials",
            "users",
            "tenants",
        ]
        for table in expected_drops:
            assert f'drop_table("{table}")' in text, f"表 {table} 未在 downgrade() 中删除"


# ---------------------------------------------------------------------------
# Alembic 配置文件校验
# ---------------------------------------------------------------------------


class TestAlembicConfig:
    """验证 alembic.ini 配置文件。"""

    def test_alembic_ini_exists(self) -> None:
        """alembic.ini 存在于项目根。"""
        assert (PROJECT_ROOT / "alembic.ini").exists()

    def test_script_location(self) -> None:
        """script_location 指向 migrations 目录。"""
        text = (PROJECT_ROOT / "alembic.ini").read_text(encoding="utf-8")
        assert "script_location = migrations" in text

    def test_env_py_exists(self) -> None:
        """migrations/env.py 存在。"""
        assert (PROJECT_ROOT / "migrations" / "env.py").exists()

    def test_script_template_exists(self) -> None:
        """migrations/script.py.mako 模板存在。"""
        assert (PROJECT_ROOT / "migrations" / "script.py.mako").exists()

    def test_makefile_has_migrate_targets(self) -> None:
        """Makefile 包含 migrate 相关 target。"""
        makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
        for target in ["migrate", "migrate-upgrade", "migrate-downgrade", "migrate-create"]:
            assert f"{target}:" in makefile, f"Makefile 缺少 target: {target}"


# ---------------------------------------------------------------------------
# 离线 SQL 生成校验(需要 alembic 已安装)
# ---------------------------------------------------------------------------

alembic_available = pytest.importorskip("alembic", reason="alembic 未安装")


@pytest.fixture(scope="module")
def upgrade_sql() -> str:
    """运行 alembic upgrade head --sql,返回生成的 SQL 文本。"""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    # alembic 把 INFO 日志输出到 stderr,SQL 输出到 stdout
    assert result.returncode == 0, f"alembic upgrade --sql 失败:\n{result.stderr}"
    return result.stdout


@pytest.fixture(scope="module")
def downgrade_sql() -> str:
    """运行 alembic downgrade head:base --sql,返回 SQL 文本(完整回滚到 base)。"""
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "head:base", "--sql"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    assert result.returncode == 0, f"alembic downgrade --sql 失败:\n{result.stderr}"
    return result.stdout


class TestOfflineSqlGeneration:
    """通过 alembic --sql 离线生成 DDL,校验 SQL 语句数量与结构。

    不需要真实 PostgreSQL 数据库,仅验证迁移逻辑能正确生成 DDL。
    采用「升级/回滚对称」校验: upgrade 创建的表数量应与 downgrade 删除的
    表数量一致(迁移可逆),索引则校验关键索引存在 + 数量下限。
    """

    # 关键业务表(初始 18 张 + RBAC 6 张)
    KEY_TABLES = [
        "tenants",
        "users",
        "api_credentials",
        "sessions",
        "messages",
        "tasks",
        "task_steps",
        "tool_executions",
        "tools",
        "documents",
        "knowledge_chunks",
        "entities",
        "entity_relations",
        "reflection_logs",
        "audit_logs",
        "prompt_templates",
        "billing_records",
        "feedbacks",
        "roles",
        "permissions",
        "departments",
        "positions",
    ]

    # 关键索引
    KEY_INDEXES = [
        "idx_sessions_user",
        "idx_messages_session",
        "idx_tasks_user_status",
        "idx_tool_exec_task",
        "idx_tool_exec_name_time",
        "idx_docs_user_type",
        "idx_chunks_doc",
        "idx_entities_user_type",
    ]

    def test_upgrade_creates_expected_tables(self, upgrade_sql: str, downgrade_sql: str) -> None:
        """upgrade 创建的表数量应与 downgrade 删除的表数量一致(迁移可逆)。"""
        created = upgrade_sql.count("CREATE TABLE")
        dropped = downgrade_sql.count("DROP TABLE")
        assert created == dropped, (
            f"upgrade CREATE TABLE ({created}) 与 downgrade DROP TABLE ({dropped}) 数量不一致"
        )
        assert created >= 19, f"期望至少 19 张表,实际 {created}"
        normalized = upgrade_sql.replace('"', "")
        for t in self.KEY_TABLES:
            assert f"CREATE TABLE {t}" in normalized, f"upgrade 缺少表 {t}"

    def test_upgrade_creates_indexes(self, upgrade_sql: str) -> None:
        """upgrade SQL 包含全部关键索引(数量下限 8)。"""
        count = upgrade_sql.count("CREATE INDEX")
        assert count >= 8, f"期望至少 8 个 CREATE INDEX,实际 {count}"
        for idx in self.KEY_INDEXES:
            assert idx in upgrade_sql, f"upgrade 缺少索引 {idx}"

    def test_upgrade_includes_postgres_array_type(self, upgrade_sql: str) -> None:
        """upgrade SQL 包含 PostgreSQL ARRAY 类型(TEXT[] / SMALLINT[])。"""
        assert "TEXT[]" in upgrade_sql, "未使用 PostgreSQL TEXT[] 数组类型"
        assert "SMALLINT[]" in upgrade_sql, "未使用 PostgreSQL SMALLINT[] 数组类型"

    def test_upgrade_includes_cascade_fks(self, upgrade_sql: str) -> None:
        """upgrade SQL 包含 ON DELETE CASCADE 外键(task_steps, knowledge_chunks, entity_relations)。"""
        cascade_count = upgrade_sql.count("ON DELETE CASCADE")
        assert cascade_count >= 3, f"expected >=3 ON DELETE CASCADE, got {cascade_count}"

    def test_downgrade_drops_all_tables(self, upgrade_sql: str, downgrade_sql: str) -> None:
        """downgrade 删除的表数量应与 upgrade 创建的表数量一致(可逆)。"""
        created = upgrade_sql.count("CREATE TABLE")
        dropped = downgrade_sql.count("DROP TABLE")
        assert dropped == created, (
            f"downgrade DROP TABLE ({dropped}) 与 upgrade CREATE TABLE ({created}) 数量不一致"
        )

    def test_downgrade_drops_indexes(self, downgrade_sql: str) -> None:
        """downgrade SQL 至少删除 8 个索引。"""
        count = downgrade_sql.count("DROP INDEX")
        assert count >= 8, f"expected >=8 DROP INDEX, got {count}"
