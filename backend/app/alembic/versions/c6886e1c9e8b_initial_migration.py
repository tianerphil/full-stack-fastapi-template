"""Initial migration

Revision ID: c6886e1c9e8b
Revises: 
Create Date: 2024-07-04 23:48:29.317454

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from app.models import HttpUrlType


# revision identifiers, used by Alembic.
revision = 'c6886e1c9e8b'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('tag',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_tag_name'), 'tag', ['name'], unique=True)
    op.create_table('user',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.Column('hashed_password', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('is_superuser', sa.Boolean(), nullable=False),
    sa.Column('full_name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
    sa.Column('credit_balance', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_email'), 'user', ['email'], unique=True)
    op.create_table('credittransaction',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('amount', sa.Integer(), nullable=False),
    sa.Column('transaction_type', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
    sa.Column('transaction_date', sa.DateTime(), nullable=False),
    sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('generationjob',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('credits_consumed', sa.Integer(), nullable=False),
    sa.Column('job_type', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('completed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('paymentmethod',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('type', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.Column('last_four', sqlmodel.sql.sqltypes.AutoString(length=4), nullable=True),
    sa.Column('expiry_date', sa.Date(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('subscription',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('plan_name', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=True),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('media',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('media_type', sa.Enum('IMAGE', 'VIDEO', name='mediatype'), nullable=False),
    sa.Column('file_type', sqlmodel.sql.sqltypes.AutoString(length=10), nullable=False),
    sa.Column('positive_prompt', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=False),
    sa.Column('negative_prompt', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
    sa.Column('seed', sa.Integer(), nullable=False),
    sa.Column('sd_model', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
    sa.Column('s3_url', HttpUrlType(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('is_public', sa.Boolean(), nullable=False),
    sa.Column('origin_id', sa.Integer(), nullable=True),
    sa.Column('view_count', sa.Integer(), nullable=True),
    sa.Column('thumb_up_count', sa.Integer(), nullable=True),
    sa.Column('thumb_down_count', sa.Integer(), nullable=True),
    sa.Column('generation_job_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['generation_job_id'], ['generationjob.id'], ),
    sa.ForeignKeyConstraint(['origin_id'], ['media.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('comment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('media_id', sa.Integer(), nullable=False),
    sa.Column('content', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['media_id'], ['media.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mediatag',
    sa.Column('media_id', sa.Integer(), nullable=False),
    sa.Column('tag_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['media_id'], ['media.id'], ),
    sa.ForeignKeyConstraint(['tag_id'], ['tag.id'], ),
    sa.PrimaryKeyConstraint('media_id', 'tag_id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('mediatag')
    op.drop_table('comment')
    op.drop_table('media')
    op.drop_table('subscription')
    op.drop_table('paymentmethod')
    op.drop_table('generationjob')
    op.drop_table('credittransaction')
    op.drop_index(op.f('ix_user_email'), table_name='user')
    op.drop_table('user')
    op.drop_index(op.f('ix_tag_name'), table_name='tag')
    op.drop_table('tag')
    # ### end Alembic commands ###