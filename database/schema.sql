-- Generated from authoritative SQLAlchemy models. DO NOT edit independently.

BEGIN;

CREATE TABLE t_user (
	user_id VARCHAR(64) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (user_id)
);

CREATE TABLE t_survey (
	survey_id VARCHAR(64) NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	project_type VARCHAR(32) NOT NULL,
	survey_name VARCHAR(100) NOT NULL,
	creator_id VARCHAR(64) NOT NULL,
	last_modified_by VARCHAR(64),
	status VARCHAR(16) NOT NULL,
	working_version INTEGER NOT NULL,
	revision_sequence INTEGER NOT NULL,
	working_revision_id VARCHAR(64),
	published_snapshot_id VARCHAR(64),
	published_at TIMESTAMP WITH TIME ZONE,
	survey_config JSONB NOT NULL,
	ai_config_id VARCHAR(64),
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (survey_id),
	CONSTRAINT ck_project_type CHECK (project_type = 'survey'),
	CONSTRAINT ck_survey_status CHECK (status IN ('draft','published','closed')),
	FOREIGN KEY(creator_id) REFERENCES t_user (user_id) ON DELETE RESTRICT,
	FOREIGN KEY(last_modified_by) REFERENCES t_user (user_id) ON DELETE RESTRICT
);

CREATE TABLE t_ai_config (
	ai_config_id VARCHAR(64) NOT NULL,
	survey_id VARCHAR(64) NOT NULL,
	config_name VARCHAR(255) NOT NULL,
	config_version INTEGER NOT NULL,
	agent_type VARCHAR(32) DEFAULT 'conversation' NOT NULL,
	agent_name VARCHAR(255) NOT NULL,
	provider VARCHAR(32) NOT NULL,
	model VARCHAR(128) NOT NULL,
	system_prompt TEXT NOT NULL,
	context_template TEXT NOT NULL,
	user_message_template TEXT NOT NULL,
	input_source_config JSONB NOT NULL,
	temperature DOUBLE PRECISION,
	top_p DOUBLE PRECISION,
	max_output_tokens INTEGER NOT NULL,
	max_turns INTEGER NOT NULL,
	include_history BOOLEAN NOT NULL,
	history_window INTEGER,
	end_condition VARCHAR(32) NOT NULL,
	timeout_seconds INTEGER NOT NULL,
	max_retries INTEGER NOT NULL,
	failure_behavior VARCHAR(32) NOT NULL,
	response_format VARCHAR(16) NOT NULL,
	logging_config JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (ai_config_id),
	CONSTRAINT ck_ai_limits CHECK (max_turns > 0 AND max_output_tokens > 0),
	CONSTRAINT ck_ai_temperature CHECK (temperature IS NULL OR (temperature >= 0 AND temperature <= 1)),
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE
);

CREATE TABLE t_block (
	block_id VARCHAR(64) NOT NULL,
	survey_id VARCHAR(64) NOT NULL,
	question_groups JSONB DEFAULT '[]' NOT NULL,
	block_name VARCHAR(255) NOT NULL,
	sort_order INTEGER NOT NULL,
	is_deleted BOOLEAN NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (block_id),
	CONSTRAINT uq_block_survey_block UNIQUE (survey_id, block_id),
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE
);

CREATE TABLE t_project_import (
	user_id VARCHAR(64) NOT NULL,
	import_request_id VARCHAR(64) NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	survey_id VARCHAR(64) NOT NULL,
	PRIMARY KEY (user_id, import_request_id),
	FOREIGN KEY(user_id) REFERENCES t_user (user_id),
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE
);

CREATE TABLE t_survey_change_log (
	log_id VARCHAR(64) NOT NULL,
	survey_id VARCHAR(64) NOT NULL,
	user_id VARCHAR(64) NOT NULL,
	action_type VARCHAR(16) NOT NULL,
	target_type VARCHAR(32) NOT NULL,
	target_id VARCHAR(64) NOT NULL,
	details_json JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (log_id),
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE,
	FOREIGN KEY(user_id) REFERENCES t_user (user_id)
);

CREATE TABLE t_survey_flow (
	flow_id VARCHAR(64) NOT NULL,
	survey_id VARCHAR(64) NOT NULL,
	flow_version INTEGER NOT NULL,
	schema_version INTEGER NOT NULL,
	flow_json JSONB NOT NULL,
	updated_by VARCHAR(64),
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (flow_id),
	UNIQUE (survey_id),
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE,
	FOREIGN KEY(updated_by) REFERENCES t_user (user_id) ON DELETE RESTRICT
);

CREATE TABLE t_survey_members (
	survey_id VARCHAR(64) NOT NULL,
	user_id VARCHAR(64) NOT NULL,
	role VARCHAR(16) NOT NULL,
	joined_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (survey_id, user_id),
	CONSTRAINT ck_member_role CHECK (role IN ('owner','editor','viewer')),
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE,
	FOREIGN KEY(user_id) REFERENCES t_user (user_id) ON DELETE RESTRICT
);

CREATE TABLE t_survey_revision (
	revision_id VARCHAR(64) NOT NULL,
	survey_id VARCHAR(64) NOT NULL,
	revision_number INTEGER NOT NULL,
	base_revision_id VARCHAR(64),
	survey_json JSONB NOT NULL,
	save_type VARCHAR(16) NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	created_by VARCHAR(64) NOT NULL,
	PRIMARY KEY (revision_id),
	CONSTRAINT uq_survey_revision UNIQUE (survey_id, revision_number),
	CONSTRAINT ck_survey_save_type CHECK (save_type IN ('auto','apply','restore')),
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE,
	FOREIGN KEY(base_revision_id) REFERENCES t_survey_revision (revision_id),
	FOREIGN KEY(created_by) REFERENCES t_user (user_id) ON DELETE RESTRICT
);

CREATE TABLE t_question (
	question_id VARCHAR(64) NOT NULL,
	block_id VARCHAR(64) NOT NULL,
	survey_id VARCHAR(64) NOT NULL,
	question_name VARCHAR(255) NOT NULL,
	question_type VARCHAR(32) NOT NULL,
	question_text TEXT NOT NULL,
	sort_order INTEGER NOT NULL,
	required BOOLEAN NOT NULL,
	config JSONB NOT NULL,
	is_deleted BOOLEAN NOT NULL,
	deleted_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (question_id),
	CONSTRAINT fk_question_survey_block FOREIGN KEY(survey_id, block_id) REFERENCES t_block (survey_id, block_id) ON DELETE CASCADE,
	CONSTRAINT ck_question_type CHECK (question_type IN ('multiple_choice','text_entry','text_graphic','matrix')),
	CONSTRAINT ck_graphic_required CHECK (question_type != 'text_graphic' OR required = false),
	FOREIGN KEY(block_id) REFERENCES t_block (block_id) ON DELETE CASCADE,
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE
);

CREATE TABLE t_survey_flow_revision (
	revision_id VARCHAR(64) NOT NULL,
	flow_id VARCHAR(64) NOT NULL,
	survey_id VARCHAR(64) NOT NULL,
	revision_number INTEGER NOT NULL,
	flow_json JSONB NOT NULL,
	ai_configs_json JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	created_by VARCHAR(64) NOT NULL,
	save_type VARCHAR(16) NOT NULL,
	PRIMARY KEY (revision_id),
	CONSTRAINT uq_flow_revision UNIQUE (flow_id, revision_number),
	FOREIGN KEY(flow_id) REFERENCES t_survey_flow (flow_id) ON DELETE CASCADE,
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE,
	FOREIGN KEY(created_by) REFERENCES t_user (user_id) ON DELETE RESTRICT
);

CREATE TABLE t_survey_snapshot (
	snapshot_id VARCHAR(64) NOT NULL,
	survey_id VARCHAR(64) NOT NULL,
	source_revision_id VARCHAR(64) NOT NULL,
	schema_version INTEGER NOT NULL,
	content_hash VARCHAR(64) NOT NULL,
	snapshot_json JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	created_by VARCHAR(64) NOT NULL,
	PRIMARY KEY (snapshot_id),
	UNIQUE (survey_id, schema_version, content_hash),
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE,
	FOREIGN KEY(source_revision_id) REFERENCES t_survey_revision (revision_id),
	FOREIGN KEY(created_by) REFERENCES t_user (user_id)
);

CREATE TABLE t_preview_session (
	preview_session_id VARCHAR(64) NOT NULL,
	survey_id VARCHAR(64) NOT NULL,
	user_id VARCHAR(64) NOT NULL,
	snapshot_id VARCHAR(64),
	revision_id VARCHAR(64),
	status VARCHAR(16) DEFAULT 'active' NOT NULL,
	ended_at TIMESTAMP WITH TIME ZONE,
	snapshot_json JSONB NOT NULL,
	runtime_json JSONB NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (preview_session_id),
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE,
	FOREIGN KEY(user_id) REFERENCES t_user (user_id) ON DELETE RESTRICT,
	FOREIGN KEY(snapshot_id) REFERENCES t_survey_snapshot (snapshot_id),
	FOREIGN KEY(revision_id) REFERENCES t_survey_revision (revision_id)
);

CREATE TABLE t_survey_publication (
	publication_id VARCHAR(64) NOT NULL,
	survey_id VARCHAR(64) NOT NULL,
	revision_id VARCHAR(64) NOT NULL,
	snapshot_id VARCHAR(64) NOT NULL,
	published_by VARCHAR(64) NOT NULL,
	published_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (publication_id),
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE,
	FOREIGN KEY(revision_id) REFERENCES t_survey_revision (revision_id),
	FOREIGN KEY(snapshot_id) REFERENCES t_survey_snapshot (snapshot_id),
	FOREIGN KEY(published_by) REFERENCES t_user (user_id)
);

CREATE TABLE t_ai_conversation (
	conversation_id VARCHAR(64) NOT NULL,
	preview_session_id VARCHAR(64) NOT NULL,
	survey_id VARCHAR(64) NOT NULL,
	snapshot_id VARCHAR(64),
	execution_context VARCHAR(16) DEFAULT 'preview' NOT NULL,
	flow_element_id VARCHAR(64) NOT NULL,
	ai_config_id VARCHAR(64) NOT NULL,
	config_version INTEGER NOT NULL,
	agent_name VARCHAR(255) NOT NULL,
	status VARCHAR(16) NOT NULL,
	turn_count INTEGER NOT NULL,
	end_reason VARCHAR(64),
	ai_conversation_json JSONB NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	ended_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (conversation_id),
	FOREIGN KEY(preview_session_id) REFERENCES t_preview_session (preview_session_id) ON DELETE CASCADE,
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE,
	FOREIGN KEY(snapshot_id) REFERENCES t_survey_snapshot (snapshot_id),
	FOREIGN KEY(ai_config_id) REFERENCES t_ai_config (ai_config_id) ON DELETE RESTRICT
);

CREATE TABLE t_preview_response (
	preview_response_id VARCHAR(64) NOT NULL,
	preview_session_id VARCHAR(64) NOT NULL,
	survey_id VARCHAR(64) NOT NULL,
	snapshot_id VARCHAR(64) NOT NULL,
	response_json JSONB NOT NULL,
	submitted_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (preview_response_id),
	UNIQUE (preview_session_id),
	FOREIGN KEY(preview_session_id) REFERENCES t_preview_session (preview_session_id),
	FOREIGN KEY(survey_id) REFERENCES t_survey (survey_id) ON DELETE CASCADE,
	FOREIGN KEY(snapshot_id) REFERENCES t_survey_snapshot (snapshot_id)
);

CREATE TABLE t_ai_run (
	run_id VARCHAR(64) NOT NULL,
	conversation_id VARCHAR(64) NOT NULL,
	ai_config_id VARCHAR(64) NOT NULL,
	config_version INTEGER NOT NULL,
	flow_element_id VARCHAR(64) NOT NULL,
	turn_number INTEGER NOT NULL,
	model VARCHAR(128) NOT NULL,
	input_tokens INTEGER,
	output_tokens INTEGER,
	total_tokens INTEGER,
	latency_ms INTEGER,
	status VARCHAR(16) NOT NULL,
	error_message TEXT,
	input_json JSONB,
	output_json JSONB,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (run_id),
	FOREIGN KEY(conversation_id) REFERENCES t_ai_conversation (conversation_id) ON DELETE CASCADE,
	FOREIGN KEY(ai_config_id) REFERENCES t_ai_config (ai_config_id) ON DELETE RESTRICT
);

CREATE TABLE t_ai_message (
	message_id VARCHAR(64) NOT NULL,
	conversation_id VARCHAR(64) NOT NULL,
	run_id VARCHAR(64),
	role VARCHAR(16) NOT NULL,
	content TEXT NOT NULL,
	turn_number INTEGER NOT NULL,
	sequence_number INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (message_id),
	CONSTRAINT uq_ai_message_order UNIQUE (conversation_id, sequence_number),
	CONSTRAINT ck_ai_message_role CHECK (role IN ('system','user','assistant')),
	FOREIGN KEY(conversation_id) REFERENCES t_ai_conversation (conversation_id) ON DELETE CASCADE,
	FOREIGN KEY(run_id) REFERENCES t_ai_run (run_id) ON DELETE SET NULL
);

ALTER TABLE t_survey ADD CONSTRAINT fk_published_snapshot FOREIGN KEY(published_snapshot_id) REFERENCES t_survey_snapshot (snapshot_id) ON DELETE SET NULL;

ALTER TABLE t_survey ADD CONSTRAINT fk_survey_default_ai FOREIGN KEY(ai_config_id) REFERENCES t_ai_config (ai_config_id) ON DELETE SET NULL;

ALTER TABLE t_survey ADD CONSTRAINT fk_working_revision FOREIGN KEY(working_revision_id) REFERENCES t_survey_revision (revision_id) ON DELETE SET NULL;

CREATE INDEX ix_t_ai_config_survey_id ON t_ai_config (survey_id);

CREATE INDEX ix_t_block_survey_id ON t_block (survey_id);

CREATE INDEX ix_t_survey_change_log_survey_id ON t_survey_change_log (survey_id);

CREATE INDEX ix_t_survey_revision_survey_id ON t_survey_revision (survey_id);

CREATE INDEX ix_question_block_order ON t_question (block_id, sort_order);

CREATE INDEX ix_t_question_block_id ON t_question (block_id);

CREATE INDEX ix_t_preview_session_survey_id ON t_preview_session (survey_id);

CREATE INDEX ix_t_preview_session_expires_at ON t_preview_session (expires_at);

CREATE INDEX ix_t_survey_publication_survey_id ON t_survey_publication (survey_id);

CREATE INDEX ix_t_ai_conversation_preview_session_id ON t_ai_conversation (preview_session_id);

CREATE INDEX ix_t_preview_response_survey_id ON t_preview_response (survey_id);

CREATE INDEX ix_t_ai_run_conversation_id ON t_ai_run (conversation_id);

COMMIT;
