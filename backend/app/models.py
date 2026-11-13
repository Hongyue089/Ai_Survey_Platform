from datetime import datetime, timezone
from sqlalchemy import (
    String,
    Integer,
    Boolean,
    DateTime,
    Text,
    ForeignKey,
    ForeignKeyConstraint,
    UniqueConstraint,
    CheckConstraint,
    JSON,
    Index,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def now():
    return datetime.now(timezone.utc)


def jt():
    return JSON().with_variant(JSONB(), "postgresql")


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )


class User(Timestamps, Base):
    __tablename__ = "t_user"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)


class Survey(Timestamps, Base):
    __tablename__ = "t_survey"
    survey_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    project_type: Mapped[str] = mapped_column(String(32), default="survey")
    survey_name: Mapped[str] = mapped_column(String(100))
    creator_id: Mapped[str] = mapped_column(
        ForeignKey("t_user.user_id", ondelete="RESTRICT")
    )
    last_modified_by: Mapped[str | None] = mapped_column(
        ForeignKey("t_user.user_id", ondelete="RESTRICT")
    )
    status: Mapped[str] = mapped_column(String(16), default="draft")
    working_version: Mapped[int] = mapped_column(Integer, default=1)
    revision_sequence: Mapped[int] = mapped_column(Integer, default=0)
    working_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("t_survey_revision.revision_id", name="fk_working_revision", use_alter=True, ondelete="SET NULL")
    )
    published_snapshot_id: Mapped[str | None] = mapped_column(
        ForeignKey("t_survey_snapshot.snapshot_id", name="fk_published_snapshot", use_alter=True, ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    survey_config: Mapped[dict] = mapped_column(jt())
    ai_config_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "t_ai_config.ai_config_id",
            name="fk_survey_default_ai",
            use_alter=True,
            ondelete="SET NULL",
        )
    )
    __table_args__ = (
        CheckConstraint("project_type = 'survey'", name="ck_project_type"),
        CheckConstraint(
            "status IN ('draft','published','closed')", name="ck_survey_status"
        ),
    )


class SurveyMember(Base):
    __tablename__ = "t_survey_members"
    survey_id: Mapped[str] = mapped_column(
        ForeignKey("t_survey.survey_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("t_user.user_id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16))
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        CheckConstraint("role IN ('owner','editor','viewer')", name="ck_member_role"),
    )


class Block(Timestamps, Base):
    __tablename__ = "t_block"
    block_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    survey_id: Mapped[str] = mapped_column(
        ForeignKey("t_survey.survey_id", ondelete="CASCADE"), index=True
    )
    question_groups: Mapped[list] = mapped_column(jt(), default=list, server_default="[]")
    block_name: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("survey_id", "block_id", name="uq_block_survey_block"),)


class Question(Timestamps, Base):
    __tablename__ = "t_question"
    question_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    block_id: Mapped[str] = mapped_column(
        ForeignKey("t_block.block_id", ondelete="CASCADE"), index=True
    )
    survey_id: Mapped[str] = mapped_column(ForeignKey("t_survey.survey_id", ondelete="CASCADE"))
    question_name: Mapped[str] = mapped_column(String(255))
    question_type: Mapped[str] = mapped_column(String(32))
    question_text: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    config: Mapped[dict] = mapped_column(jt())
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(["survey_id", "block_id"], ["t_block.survey_id", "t_block.block_id"],
                             name="fk_question_survey_block", ondelete="CASCADE"),
        CheckConstraint(
            "question_type IN ('multiple_choice','text_entry','text_graphic','matrix')",
            name="ck_question_type",
        ),
        CheckConstraint(
            "question_type != 'text_graphic' OR required = false",
            name="ck_graphic_required",
        ),
    )


class SurveyFlow(Timestamps, Base):
    __tablename__ = "t_survey_flow"
    flow_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    survey_id: Mapped[str] = mapped_column(
        ForeignKey("t_survey.survey_id", ondelete="CASCADE"), unique=True
    )
    flow_version: Mapped[int] = mapped_column(Integer, default=1)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    flow_json: Mapped[dict] = mapped_column(jt())
    updated_by: Mapped[str | None] = mapped_column(
        ForeignKey("t_user.user_id", ondelete="RESTRICT")
    )


class SurveyRevision(Base):
    __tablename__ = "t_survey_revision"
    revision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    survey_id: Mapped[str] = mapped_column(
        ForeignKey("t_survey.survey_id", ondelete="CASCADE"), index=True
    )
    revision_number: Mapped[int] = mapped_column(Integer)
    base_revision_id: Mapped[str | None] = mapped_column(ForeignKey("t_survey_revision.revision_id"))
    survey_json: Mapped[dict] = mapped_column(jt())
    save_type: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_by: Mapped[str] = mapped_column(
        ForeignKey("t_user.user_id", ondelete="RESTRICT")
    )
    __table_args__ = (
        UniqueConstraint("survey_id", "revision_number", name="uq_survey_revision"),
        CheckConstraint(
            "save_type IN ('auto','apply','restore')", name="ck_survey_save_type"
        ),
    )


class SurveySnapshot(Base):
    __tablename__ = "t_survey_snapshot"
    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("t_survey.survey_id", ondelete="CASCADE"))
    source_revision_id: Mapped[str] = mapped_column(ForeignKey("t_survey_revision.revision_id"))
    schema_version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    snapshot_json: Mapped[dict] = mapped_column(jt())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_by: Mapped[str] = mapped_column(ForeignKey("t_user.user_id"))
    __table_args__ = (UniqueConstraint("survey_id", "schema_version", "content_hash"),)


class SurveyPublication(Base):
    __tablename__ = "t_survey_publication"
    publication_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("t_survey.survey_id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[str] = mapped_column(ForeignKey("t_survey_revision.revision_id"))
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("t_survey_snapshot.snapshot_id"))
    published_by: Mapped[str] = mapped_column(ForeignKey("t_user.user_id"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SurveyChangeLog(Base):
    __tablename__ = "t_survey_change_log"
    log_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("t_survey.survey_id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("t_user.user_id"))
    action_type: Mapped[str] = mapped_column(String(16))
    target_type: Mapped[str] = mapped_column(String(32), default="survey")
    target_id: Mapped[str] = mapped_column(String(64))
    details_json: Mapped[dict] = mapped_column(jt(), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProjectImport(Base):
    __tablename__ = "t_project_import"
    user_id: Mapped[str] = mapped_column(ForeignKey("t_user.user_id"), primary_key=True)
    import_request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    survey_id: Mapped[str] = mapped_column(ForeignKey("t_survey.survey_id", ondelete="CASCADE"))


class FlowRevision(Base):
    __tablename__ = "t_survey_flow_revision"
    revision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    flow_id: Mapped[str] = mapped_column(
        ForeignKey("t_survey_flow.flow_id", ondelete="CASCADE")
    )
    survey_id: Mapped[str] = mapped_column(
        ForeignKey("t_survey.survey_id", ondelete="CASCADE")
    )
    revision_number: Mapped[int] = mapped_column(Integer)
    flow_json: Mapped[dict] = mapped_column(jt())
    ai_configs_json: Mapped[list] = mapped_column(jt())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    created_by: Mapped[str] = mapped_column(
        ForeignKey("t_user.user_id", ondelete="RESTRICT")
    )
    save_type: Mapped[str] = mapped_column(String(16))
    __table_args__ = (
        UniqueConstraint("flow_id", "revision_number", name="uq_flow_revision"),
    )


class AIConfig(Timestamps, Base):
    __tablename__ = "t_ai_config"
    ai_config_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    survey_id: Mapped[str] = mapped_column(
        ForeignKey("t_survey.survey_id", ondelete="CASCADE"), index=True
    )
    config_name: Mapped[str] = mapped_column(String(255))
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    agent_type: Mapped[str] = mapped_column(String(32), default="conversation", server_default="conversation")
    agent_name: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(32), default="openai")
    model: Mapped[str] = mapped_column(String(128))
    system_prompt: Mapped[str] = mapped_column(Text)
    context_template: Mapped[str] = mapped_column(Text, default="")
    user_message_template: Mapped[str] = mapped_column(Text)
    input_source_config: Mapped[dict] = mapped_column(jt(), default=dict)
    temperature: Mapped[float | None]
    top_p: Mapped[float | None]
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=800)
    max_turns: Mapped[int] = mapped_column(Integer, default=3)
    include_history: Mapped[bool] = mapped_column(Boolean, default=True)
    history_window: Mapped[int | None]
    end_condition: Mapped[str] = mapped_column(String(32), default="max_turns_reached")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    max_retries: Mapped[int] = mapped_column(Integer, default=2)
    failure_behavior: Mapped[str] = mapped_column(String(32), default="show_error")
    response_format: Mapped[str] = mapped_column(String(16), default="text")
    logging_config: Mapped[dict] = mapped_column(jt())
    __table_args__ = (
        CheckConstraint("max_turns > 0 AND max_output_tokens > 0", name="ck_ai_limits"),
        CheckConstraint(
            "temperature IS NULL OR (temperature >= 0 AND temperature <= 1)",
            name="ck_ai_temperature",
        ),
    )


class PreviewSession(Base):
    __tablename__ = "t_preview_session"
    preview_session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    survey_id: Mapped[str] = mapped_column(
        ForeignKey("t_survey.survey_id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("t_user.user_id", ondelete="RESTRICT")
    )
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("t_survey_snapshot.snapshot_id"))
    revision_id: Mapped[str | None] = mapped_column(ForeignKey("t_survey_revision.revision_id"))
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot_json: Mapped[dict] = mapped_column(jt())
    runtime_json: Mapped[dict] = mapped_column(jt())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PreviewResponse(Base):
    __tablename__ = "t_preview_response"
    preview_response_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    preview_session_id: Mapped[str] = mapped_column(ForeignKey("t_preview_session.preview_session_id"), unique=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("t_survey.survey_id", ondelete="CASCADE"), index=True)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("t_survey_snapshot.snapshot_id"))
    response_json: Mapped[dict] = mapped_column(jt())
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AIConversation(Timestamps, Base):
    __tablename__ = "t_ai_conversation"
    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    preview_session_id: Mapped[str] = mapped_column(
        ForeignKey("t_preview_session.preview_session_id", ondelete="CASCADE"),
        index=True,
    )
    survey_id: Mapped[str] = mapped_column(
        ForeignKey("t_survey.survey_id", ondelete="CASCADE")
    )
    snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("t_survey_snapshot.snapshot_id"))
    execution_context: Mapped[str] = mapped_column(String(16), default="preview", server_default="preview")
    flow_element_id: Mapped[str] = mapped_column(String(64))
    ai_config_id: Mapped[str] = mapped_column(
        ForeignKey("t_ai_config.ai_config_id", ondelete="RESTRICT")
    )
    config_version: Mapped[int] = mapped_column(Integer)
    agent_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="running")
    turn_count: Mapped[int] = mapped_column(Integer, default=0)
    end_reason: Mapped[str | None] = mapped_column(String(64))
    ai_conversation_json: Mapped[dict] = mapped_column(jt())
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIRun(Base):
    __tablename__ = "t_ai_run"
    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("t_ai_conversation.conversation_id", ondelete="CASCADE"), index=True
    )
    ai_config_id: Mapped[str] = mapped_column(
        ForeignKey("t_ai_config.ai_config_id", ondelete="RESTRICT")
    )
    config_version: Mapped[int] = mapped_column(Integer)
    flow_element_id: Mapped[str] = mapped_column(String(64))
    turn_number: Mapped[int] = mapped_column(Integer)
    model: Mapped[str] = mapped_column(String(128))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    total_tokens: Mapped[int | None]
    latency_ms: Mapped[int | None]
    status: Mapped[str] = mapped_column(String(16))
    error_message: Mapped[str | None] = mapped_column(Text)
    input_json: Mapped[dict | None] = mapped_column(jt())
    output_json: Mapped[dict | None] = mapped_column(jt())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AIMessage(Base):
    __tablename__ = "t_ai_message"
    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("t_ai_conversation.conversation_id", ondelete="CASCADE")
    )
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("t_ai_run.run_id", ondelete="SET NULL")
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    turn_number: Mapped[int] = mapped_column(Integer)
    sequence_number: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "sequence_number", name="uq_ai_message_order"
        ),
        CheckConstraint(
            "role IN ('system','user','assistant')", name="ck_ai_message_role"
        ),
    )


Index("ix_question_block_order", Question.block_id, Question.sort_order)
