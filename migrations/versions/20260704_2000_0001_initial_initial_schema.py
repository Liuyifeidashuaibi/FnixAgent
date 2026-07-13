"""initial schema: 全部 18 张表

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-04 20:00:00

本迁移把 src/officeagent/models/db/models.py 中定义的全部 ORM 模型转换为
数据库表结构,包括:
    - 账号与租户:tenants / users / api_credentials
    - 会话与消息:sessions / messages
    - 任务与规划:tasks / task_steps / tool_executions / tools
    - 文档与知识库:documents / knowledge_chunks
    - 实体记忆:entities / entity_relations
    - 反思与安全:reflection_logs / audit_logs / prompt_templates
    - 计费与反馈:billing_records / feedbacks

注意:
    - ARRAY 类型仅 PostgreSQL 支持(本项目目标 DB 即 PG)
    - 时间字段统一使用 TIMESTAMP(不带时区,与 ORM 模型一致)
    - 外键约束保留 ON DELETE CASCADE(级联删除)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建全部 18 张表(按 FK 依赖顺序)。"""

    # ------------------------------------------------------------------
    # 1. tenants(无 FK,根表)
    # ------------------------------------------------------------------
    op.create_table(
        "tenants",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("plan", sa.String(length=32), nullable=False, server_default="free"),
        sa.Column("quota_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 2. users(FK -> tenants)
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=128), unique=True),
        sa.Column("password_hash", sa.String(length=255)),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="user"),
        sa.Column("profile", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "username", name="uq_tenant_username"),
    )

    # ------------------------------------------------------------------
    # 3. api_credentials(FK -> users)
    # ------------------------------------------------------------------
    op.create_table(
        "api_credentials",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("api_key_hash", sa.String(length=255), nullable=False),
        sa.Column("scopes", sa.ARRAY(sa.TEXT()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("expires_at", sa.TIMESTAMP()),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.TIMESTAMP()),
    )

    # ------------------------------------------------------------------
    # 4. sessions(FK -> tenants, users)
    # ------------------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=255)),
        sa.Column("context", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("idx_sessions_user", "sessions", ["user_id", "status"])

    # ------------------------------------------------------------------
    # 5. messages(FK -> sessions, self-ref)
    # ------------------------------------------------------------------
    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_id", sa.BigInteger(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.TEXT(), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False, server_default="text"),
        sa.Column("parent_id", sa.BigInteger(), sa.ForeignKey("messages.id")),
        sa.Column("token_input", sa.SmallInteger()),
        sa.Column("token_output", sa.SmallInteger()),
        sa.Column("model", sa.String(length=64)),
        sa.Column("trace_id", sa.String(length=64)),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_messages_session", "messages", ["session_id", "created_at"])

    # ------------------------------------------------------------------
    # 6. tasks(FK -> sessions, users)
    # ------------------------------------------------------------------
    op.create_table(
        "tasks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("session_id", sa.BigInteger(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("intent", sa.String(length=128)),
        sa.Column("reasoning_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("plan", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("result", sa.JSON()),
        sa.Column("error", sa.TEXT()),
        sa.Column("started_at", sa.TIMESTAMP()),
        sa.Column("finished_at", sa.TIMESTAMP()),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_tasks_user_status", "tasks", ["user_id", "status"])

    # ------------------------------------------------------------------
    # 7. task_steps(FK -> tasks, ON DELETE CASCADE)
    # ------------------------------------------------------------------
    op.create_table(
        "task_steps",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "task_id",
            sa.BigInteger(),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_no", sa.SmallInteger(), nullable=False),
        sa.Column("description", sa.TEXT(), nullable=False),
        sa.Column("tool_name", sa.String(length=128)),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column(
            "depends_on",
            sa.ARRAY(sa.SmallInteger()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("started_at", sa.TIMESTAMP()),
        sa.Column("finished_at", sa.TIMESTAMP()),
    )

    # ------------------------------------------------------------------
    # 8. tool_executions(FK -> tasks, task_steps)
    # ------------------------------------------------------------------
    op.create_table(
        "tool_executions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("tasks.id")),
        sa.Column("step_id", sa.BigInteger(), sa.ForeignKey("task_steps.id")),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("tool_version", sa.String(length=32)),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON()),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error", sa.TEXT()),
        sa.Column("duration_ms", sa.SmallInteger()),
        sa.Column("sandbox_id", sa.String(length=64)),
        sa.Column("permission_level", sa.String(length=32), server_default="low"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_tool_exec_task", "tool_executions", ["task_id"])
    op.create_index("idx_tool_exec_name_time", "tool_executions", ["tool_name", "created_at"])

    # ------------------------------------------------------------------
    # 9. tools(无 FK,工具元数据)
    # ------------------------------------------------------------------
    op.create_table(
        "tools",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(length=128), unique=True, nullable=False),
        sa.Column("description", sa.TEXT(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("output_schema", sa.JSON()),
        sa.Column("permission_level", sa.String(length=32), nullable=False, server_default="low"),
        sa.Column("timeout_ms", sa.SmallInteger(), nullable=False, server_default="30000"),
        sa.Column("rate_limit", sa.SmallInteger()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="1.0.0"),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 10. documents(tenant_id/user_id 不带 FK,软隔离)
    # ------------------------------------------------------------------
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("doc_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("object_key", sa.String(length=512)),
        sa.Column("mime_type", sa.String(length=128)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("checksum", sa.String(length=64)),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.TIMESTAMP()),
    )
    op.create_index("idx_docs_user_type", "documents", ["user_id", "doc_type"])

    # ------------------------------------------------------------------
    # 11. knowledge_chunks(FK -> documents, ON DELETE CASCADE)
    # ------------------------------------------------------------------
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.SmallInteger(), nullable=False),
        sa.Column("content", sa.TEXT(), nullable=False),
        sa.Column("vector_id", sa.String(length=128)),
        sa.Column("token_count", sa.SmallInteger()),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_chunks_doc", "knowledge_chunks", ["document_id"])

    # ------------------------------------------------------------------
    # 12. entities(tenant_id/user_id 不带 FK)
    # ------------------------------------------------------------------
    op.create_table(
        "entities",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger()),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("tenant_id", "entity_type", "name", name="uq_tenant_entity"),
    )
    op.create_index("idx_entities_user_type", "entities", ["user_id", "entity_type"])

    # ------------------------------------------------------------------
    # 13. entity_relations(FK -> entities x2, ON DELETE CASCADE)
    # ------------------------------------------------------------------
    op.create_table(
        "entity_relations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "source_id",
            sa.BigInteger(),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            sa.BigInteger(),
            sa.ForeignKey("entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation", sa.String(length=64), nullable=False),
        sa.Column("weight", sa.Numeric(precision=12, scale=6), nullable=False, server_default="1.0"),
        sa.UniqueConstraint("source_id", "target_id", "relation", name="uq_entity_relation"),
    )

    # ------------------------------------------------------------------
    # 14. reflection_logs(FK -> tasks, task_steps)
    # ------------------------------------------------------------------
    op.create_table(
        "reflection_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("tasks.id")),
        sa.Column("step_id", sa.BigInteger(), sa.ForeignKey("task_steps.id")),
        sa.Column("check_type", sa.String(length=64), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.TEXT()),
        sa.Column("suggestion", sa.TEXT()),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 15. audit_logs(无 FK,审计独立)
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger()),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("trace_id", sa.String(length=64)),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 16. prompt_templates(无 FK)
    # ------------------------------------------------------------------
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("layer", sa.String(length=32), nullable=False),
        sa.Column("content", sa.TEXT(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", "version", name="uq_prompt_template"),
    )

    # ------------------------------------------------------------------
    # 17. billing_records(无 FK)
    # ------------------------------------------------------------------
    op.create_table(
        "billing_records",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("token_input", sa.SmallInteger(), nullable=False),
        sa.Column("token_output", sa.SmallInteger(), nullable=False),
        sa.Column("cost", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("trace_id", sa.String(length=64)),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # 18. feedbacks(FK -> messages)
    # ------------------------------------------------------------------
    op.create_table(
        "feedbacks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("message_id", sa.BigInteger(), sa.ForeignKey("messages.id")),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.TEXT()),
        sa.Column("tags", sa.ARRAY(sa.TEXT())),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    """回滚:按 FK 依赖反向顺序删除全部 18 张表。"""
    # 反向顺序(与 upgrade 相反)
    op.drop_table("feedbacks")
    op.drop_table("billing_records")
    op.drop_table("prompt_templates")
    op.drop_table("audit_logs")
    op.drop_table("reflection_logs")
    op.drop_table("entity_relations")
    op.drop_index("idx_entities_user_type", table_name="entities")
    op.drop_table("entities")
    op.drop_index("idx_chunks_doc", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index("idx_docs_user_type", table_name="documents")
    op.drop_table("documents")
    op.drop_table("tools")
    op.drop_index("idx_tool_exec_name_time", table_name="tool_executions")
    op.drop_index("idx_tool_exec_task", table_name="tool_executions")
    op.drop_table("tool_executions")
    op.drop_table("task_steps")
    op.drop_index("idx_tasks_user_status", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("idx_messages_session", table_name="messages")
    op.drop_table("messages")
    op.drop_index("idx_sessions_user", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("api_credentials")
    op.drop_table("users")
    op.drop_table("tenants")
