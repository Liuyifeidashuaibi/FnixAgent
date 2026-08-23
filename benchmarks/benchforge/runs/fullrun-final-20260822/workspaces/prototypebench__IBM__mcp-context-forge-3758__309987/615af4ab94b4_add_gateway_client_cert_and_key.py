import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "615af4ab94b4"
down_revision = "20a0e0538ac5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Idempotent upgrade: adds columns only if missing."""
    inspector = sa.inspect(op.get_bind())
    
    if "gateways" not in inspector.get_table_names():
        return  # Fresh DB: model creates columns
    
    columns = [col["name"] for col in inspector.get_columns("gateways")]
    
    if "client_cert" not in columns:
        op.add_column("gateways", sa.Column("client_cert", sa.Text(), nullable=True))
    
    if "client_key" not in columns:
        op.add_column("gateways", sa.Column("client_key", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade: remove columns if they exist."""
    inspector = sa.inspect(op.get_bind())
    
    if "gateways" not in inspector.get_table_names():
        return
    
    columns = [col["name"] for col in inspector.get_columns("gateways")]
    
    if "client_cert" in columns:
        op.drop_column("gateways", "client_cert")
    
    if "client_key" in columns:
        op.drop_column("gateways", "client_key")
