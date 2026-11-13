-- Run after schema.sql. Safe to repeat.
INSERT INTO t_user (user_id, created_at, updated_at)
VALUES ('dev_admin', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (user_id) DO NOTHING;
