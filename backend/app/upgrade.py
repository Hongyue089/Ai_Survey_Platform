"""Non-destructive upgrade for already initialized V2 development databases."""
from sqlalchemy import create_engine, text, inspect
from .config import settings
from .models import Base, ProjectImport, PreviewResponse, SurveyChangeLog, SurveyPublication, SurveySnapshot


def upgrade(engine):
    if engine.dialect.name != "postgresql":
        raise RuntimeError("This upgrade targets PostgreSQL")
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL search_path TO public"))
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('survey-platform-schema-upgrade'))"))
        inspector = inspect(conn)
        if "t_block" not in inspector.get_table_names(schema="public"):
            raise RuntimeError("V2 database is not initialized; upgrade does not create or reset tables")
        columns = {c["name"] for c in inspector.get_columns("t_block", schema="public")}
        if not {"block_id", "survey_id", "block_name", "sort_order", "is_deleted"} <= columns:
            raise RuntimeError("t_block does not match V2 project schema")

        Base.metadata.create_all(conn, tables=[
            SurveySnapshot.__table__, SurveyPublication.__table__, SurveyChangeLog.__table__,
            ProjectImport.__table__, PreviewResponse.__table__,
        ])
        statements = [
            "ALTER TABLE t_block ADD COLUMN IF NOT EXISTS question_groups JSONB NOT NULL DEFAULT '[]'::jsonb",
            "ALTER TABLE t_question ADD COLUMN IF NOT EXISTS survey_id varchar(64) REFERENCES t_survey(survey_id) ON DELETE CASCADE",
            "UPDATE t_question q SET survey_id = b.survey_id FROM t_block b WHERE q.block_id = b.block_id AND q.survey_id IS NULL",
            "ALTER TABLE t_question ALTER COLUMN survey_id SET NOT NULL",
            """DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_block_survey_block' AND conrelid='t_block'::regclass) THEN
                    ALTER TABLE t_block ADD CONSTRAINT uq_block_survey_block UNIQUE (survey_id, block_id);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_question_survey_block' AND conrelid='t_question'::regclass) THEN
                    ALTER TABLE t_question ADD CONSTRAINT fk_question_survey_block
                        FOREIGN KEY (survey_id, block_id) REFERENCES t_block (survey_id, block_id) ON DELETE CASCADE;
                END IF;
            END $$""",
            """ALTER TABLE t_survey
                ADD COLUMN IF NOT EXISTS working_revision_id varchar(64)
                    CONSTRAINT fk_working_revision REFERENCES t_survey_revision(revision_id) ON DELETE SET NULL,
                ADD COLUMN IF NOT EXISTS published_snapshot_id varchar(64)
                    CONSTRAINT fk_published_snapshot REFERENCES t_survey_snapshot(snapshot_id) ON DELETE SET NULL,
                ADD COLUMN IF NOT EXISTS published_at timestamptz""",
            """UPDATE t_survey s SET working_revision_id = r.revision_id
                FROM t_survey_revision r
                WHERE s.working_revision_id IS NULL AND r.survey_id = s.survey_id
                    AND r.revision_number = s.revision_sequence
                    AND (r.survey_json->>'working_version') = s.working_version::text""",
            """ALTER TABLE t_survey_revision ADD COLUMN IF NOT EXISTS base_revision_id varchar(64)
                REFERENCES t_survey_revision(revision_id)""",
            """ALTER TABLE t_ai_config ADD COLUMN IF NOT EXISTS agent_type varchar(32)
                NOT NULL DEFAULT 'conversation'""",
            """ALTER TABLE t_ai_conversation
                ADD COLUMN IF NOT EXISTS snapshot_id varchar(64) REFERENCES t_survey_snapshot(snapshot_id),
                ADD COLUMN IF NOT EXISTS execution_context varchar(16) NOT NULL DEFAULT 'preview'""",
            """ALTER TABLE t_preview_session
                ADD COLUMN IF NOT EXISTS snapshot_id varchar(64) REFERENCES t_survey_snapshot(snapshot_id),
                ADD COLUMN IF NOT EXISTS revision_id varchar(64) REFERENCES t_survey_revision(revision_id),
                ADD COLUMN IF NOT EXISTS status varchar(16) NOT NULL DEFAULT 'active',
                ADD COLUMN IF NOT EXISTS ended_at timestamptz""",
        ]
        for statement in statements:
            conn.execute(text(statement))
    print("V2 upgrade complete. Existing surveys, history and responses retained.")


if __name__ == "__main__":
    engine = create_engine(settings.database_url)
    try:
        upgrade(engine)
    finally:
        engine.dispose()
