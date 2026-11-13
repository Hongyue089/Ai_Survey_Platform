"""Run only against a fresh disposable PostgreSQL development test database."""

import json
from sqlalchemy import text, inspect
from app.db import engine, Base
from app.initialize import inspect_project, reset_tables
from app.models import User
from app.main import app
from fastapi.testclient import TestClient

with engine.begin() as conn:
    Base.metadata.create_all(conn)
    conn.execute(
        text(
            "INSERT INTO t_user(user_id,created_at,updated_at) VALUES('dev_admin',now(),now())"
        )
    )
with TestClient(app) as c:
    assert c.get("/health").status_code == 200
    response = c.post("/api/projects")
    assert response.status_code == 201, response.text
    survey = response.json()
    assert survey["project_type"] == "survey"
    assert c.get("/api/projects").json()["items"][0]["question_count"] == 0
    survey["flow"]["elements"] = [
        {"element_id": "show", "type": "block", "sort_order": 1,
         "block_id": survey["blocks"][0]["block_id"]},
    ]
    body = {key: survey[key] for key in ("survey_name", "survey_config", "blocks", "flow", "ai_configs")}
    saved = c.put(f"/api/surveys/{survey['survey_id']}/working", json=dict(body, expected_version=survey["working_version"]))
    assert saved.status_code == 200, saved.text
    p = c.post(f"/api/surveys/{survey['survey_id']}/preview-sessions")
    assert p.status_code == 201, p.text
    print("FastAPI + SQLAlchemy + PostgreSQL JSONB request chain passed.")
with engine.begin() as conn:
    conn.execute(text("CREATE TABLE unrelated_keep (id INTEGER PRIMARY KEY)"))
    conn.execute(
        text(
            "CREATE TABLE unrelated_ref (id INTEGER PRIMARY KEY, survey_id VARCHAR REFERENCES t_survey(survey_id))"
        )
    )
    try:
        inspect_project(conn)
    except RuntimeError as e:
        assert "External dependency" in str(e)
        print("Unknown external dependency correctly refused.")
    else:
        raise AssertionError("External dependency was not blocked")
    conn.execute(text("DROP TABLE unrelated_ref"))
    present, detail = inspect_project(conn)
    order = reset_tables(conn, present)
    print("Verified dependency drop order:", order)
    assert "unrelated_keep" in inspect(conn).get_table_names()
    Base.metadata.create_all(conn)
    conn.execute(
        text(
            "INSERT INTO t_user(user_id,created_at,updated_at) VALUES('dev_admin',now(),now())"
        )
    )
    present, _ = inspect_project(conn)
    reset_tables(conn, present)
    Base.metadata.create_all(conn)
    conn.execute(
        text(
            "INSERT INTO t_user(user_id,created_at,updated_at) VALUES('dev_admin',now(),now())"
        )
    )
    print("Repeated transactional reset and init passed; unrelated table retained.")
with engine.connect() as conn:
    assert (
        conn.scalar(text("SELECT count(*) FROM t_user WHERE user_id='dev_admin'")) == 1
    )
    assert conn.scalar(text("SELECT count(*) FROM t_survey")) == 0
