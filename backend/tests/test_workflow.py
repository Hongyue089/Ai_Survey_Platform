import os

os.environ["DATABASE_URL"] = "sqlite://"
from copy import deepcopy
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app.db import Base, get_db
from app.models import User
from app.main import app


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def fks(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions() as db:
        db.add(User(user_id="dev_admin"))
        db.commit()

    def dependency():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = dependency
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


def payload(s):
    return {
        **{
            k: s[k]
            for k in ["survey_name", "survey_config", "blocks", "flow", "ai_configs"]
        },
        "expected_version": s["working_version"],
        "save_type": "apply",
    }


def save(c, s):
    r = c.put("/api/surveys/" + s["survey_id"] + "/working", json=payload(s))
    assert r.status_code == 200, r.text
    return r.json()


def question(identifier="q1", typ="text_entry"):
    return {
        "question_id": identifier,
        "question_name": identifier,
        "question_type": typ,
        "question_text": "Question",
        "sort_order": 1,
        "required": True,
        "config": {
            "input_type": "single_line",
            "placeholder": "",
            "max_characters": 10,
        },
        "is_deleted": False,
        "deleted_at": None,
    }


def element(identifier, typ, **kwargs):
    return {"element_id": identifier, "type": typ, "sort_order": 1, **kwargs}


def test_linear_preview_required_and_revision(client):
    c = client
    s = c.post("/api/projects").json()
    assert len(s["blocks"]) == 1 and s["blocks"][0]["questions"] == []
    assert s["project_type"] == "survey"
    s["blocks"][0]["questions"] = [question()]
    s["flow"]["elements"] = [element("show", "block", block_id=s["blocks"][0]["block_id"])]
    s = save(c, s)
    view = c.post(f"/api/surveys/{s['survey_id']}/preview-sessions").json()
    pid = view["preview_session_id"]
    assert view["page"]["kind"] == "block"
    assert (
        c.post(
            "/api/preview-sessions/" + pid + "/next", json={"answers": {}}
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/preview-sessions/" + pid + "/next", json={"answers": {"q1": "hello"}}
        ).json()["page"]["kind"]
        == "end"
    )
    assert c.get("/api/projects").json()["items"][0]["response_count"] == 0
    old = deepcopy(s)
    s["survey_name"] = "Changed"
    s = save(c, s)
    r = c.put(f"/api/surveys/{s['survey_id']}/working", json=payload(old))
    assert r.status_code == 409
    revisions = c.get(f"/api/surveys/{s['survey_id']}/revisions").json()
    assert len(revisions) == 2
    r = c.post(
        f"/api/surveys/{s['survey_id']}/revisions/{revisions[-1]['revision_id']}/restore",
        json={"expected_version": s["working_version"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["survey_name"] == "New Survey"


def test_flow_branch_variable_and_end(client):
    c = client
    s = c.post("/api/projects").json()
    b = s["blocks"][0]
    b["questions"] = [question()]
    s["flow"]["elements"] = [
        element(
            "v",
            "embedded_data",
            config={"variable_name": "condition", "value": "treatment"},
        ),
        element(
            "branch",
            "branch",
            config={
                "condition_groups": [
                    {
                        "group_id": "g",
                        "conditions": [
                            {
                                "source_type": "variable",
                                "source_id": "condition",
                                "operator": "equals",
                                "value": "treatment",
                            }
                        ],
                        "children": [
                            element("b", "block", block_id=b["block_id"]),
                            element("end", "end_survey"),
                        ],
                    }
                ]
            },
        ),
        element("later", "block", block_id=b["block_id"]),
    ]
    s = save(c, s)
    v = c.post(f"/api/surveys/{s['survey_id']}/preview-sessions").json()
    assert v["page"]["kind"] == "block"
    v = c.post(
        "/api/preview-sessions/" + v["preview_session_id"] + "/next",
        json={"answers": {"q1": "ok"}},
    ).json()
    assert v["page"]["kind"] == "end"


def test_references_permissions_and_deletion(client):
    c = client
    a = c.post("/api/projects").json()
    b = c.post("/api/projects").json()
    a["blocks"][0]["questions"] = [question()]
    a = save(c, a)
    a["flow"]["elements"] = [
        element("flow", "block", block_id=b["blocks"][0]["block_id"])
    ]
    assert (
        c.put(f"/api/surveys/{a['survey_id']}/working", json=payload(a)).status_code
        == 422
    )
    a["flow"]["elements"] = [
        element("flow", "block", block_id=a["blocks"][0]["block_id"])
    ]
    a = save(c, a)
    a["blocks"][0]["is_deleted"] = True
    a["blocks"][0]["questions"][0]["is_deleted"] = True
    assert (
        c.put(f"/api/surveys/{a['survey_id']}/working", json=payload(a)).status_code
        == 422
    )
    assert c.get("/api/surveys/unowned/working").status_code == 404


def test_randomizer_and_back_no_reroll(client):
    c = client
    s = c.post("/api/projects").json()
    s["blocks"][0]["questions"] = [question()]
    s["blocks"].append(
        {
            "block_id": "b2",
            "block_name": "Second",
            "sort_order": 2,
            "questions": [question("q2")],
            "is_deleted": False,
            "deleted_at": None,
        }
    )
    s["flow"]["elements"] = [
        element(
            "r",
            "randomizer",
            config={"number_to_present": 1, "evenly_present": True},
            children=[
                element("b1", "block", block_id=s["blocks"][0]["block_id"]),
                element("b2", "block", block_id="b2"),
            ],
        )
    ]
    s = save(c, s)
    v = c.post(f"/api/surveys/{s['survey_id']}/preview-sessions").json()
    pid = v["preview_session_id"]
    bid = v["page"]["block"]["block_id"]
    qid = v["page"]["block"]["questions"][0]["question_id"]
    assert (
        c.post(
            "/api/preview-sessions/" + pid + "/next", json={"answers": {qid: "answer"}}
        ).json()["page"]["kind"]
        == "end"
    )
    assert (
        c.post("/api/preview-sessions/" + pid + "/back").json()["page"]["block"][
            "block_id"
        ]
        == bid
    )
    second = c.post(f"/api/surveys/{s['survey_id']}/preview-sessions").json()
    assert second["page"]["block"]["block_id"] != bid


def test_bad_config_and_draft_flow(client):
    c = client
    s = c.post("/api/projects").json()
    s["flow"]["elements"] = [element("b", "block")]
    s = save(c, s)
    assert c.post(f"/api/surveys/{s['survey_id']}/preview-sessions").status_code == 422
    s["blocks"][0]["questions"] = [question()]
    s["blocks"][0]["questions"][0]["config"]["max_characters"] = -1
    assert (
        c.put(f"/api/surveys/{s['survey_id']}/working", json=payload(s)).status_code
        == 422
    )


def test_ai_opening_not_turn_and_no_formal_data(client, monkeypatch):
    from app import preview

    async def mock(a, messages):
        return (
            "Real provider test double",
            {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            "test-model",
        )

    monkeypatch.setattr(preview, "ai_request", mock)
    c = client
    s = c.post("/api/projects").json()
    s["ai_configs"] = [
        {
            "ai_config_id": "ai1",
            "agent_name": "Agent",
            "model": "test-model",
            "system_prompt": "Role",
            "user_message_template": "Task",
            "max_turns": 1,
        }
    ]
    s["flow"]["elements"] = [element("a", "call_ai", ai_config_id="ai1")]
    s = save(c, s)
    v = c.post(f"/api/surveys/{s['survey_id']}/preview-sessions").json()
    pid = v["preview_session_id"]
    v = c.post("/api/preview-sessions/" + pid + "/chat", json={"message": ""}).json()
    assert v["page"]["turn_count"] == 0 and not v["page"]["done"]
    v = c.post(
        "/api/preview-sessions/" + pid + "/chat", json={"message": "hello"}
    ).json()
    assert v["page"]["turn_count"] == 1 and v["page"]["done"]
    assert c.get("/api/projects").json()["items"][0]["response_count"] == 0
    assert c.delete("/api/preview-sessions/" + pid).status_code == 204


def test_pagination_literal_search_and_actual_modify_time(client):
    c = client
    s = c.post("/api/projects").json()
    initial = s["updated_at"]
    assert (
        c.get(f"/api/surveys/{s['survey_id']}/working").json()["updated_at"] == initial
    )
    c.post(f"/api/surveys/{s['survey_id']}/preview-sessions")
    assert (
        c.get(f"/api/surveys/{s['survey_id']}/working").json()["updated_at"] == initial
    )
    s["survey_name"] = "100% Research"
    s = save(c, s)
    other = c.post("/api/projects").json()
    other["survey_name"] = "Alpha"
    save(c, other)
    r = c.get("/api/projects", params={"search_keyword": "%"}).json()
    assert r["total"] == 1 and r["items"][0]["survey_id"] == s["survey_id"]
    r = c.get(
        "/api/projects", params={"page_size": 1, "page": 2, "sort_option": "name_az"}
    ).json()
    assert r["total"] == 2 and len(r["items"]) == 1
    assert (
        c.get("/api/projects", params={"sort_option": "creator_id"}).status_code == 422
    )


def test_flow_ai_revision_restores_configuration(client):
    c = client
    s = c.post("/api/projects").json()
    s["ai_configs"] = [
        {
            "ai_config_id": "ai1",
            "agent_name": "Agent",
            "model": "test-model",
            "system_prompt": "Original",
            "user_message_template": "Task",
        }
    ]
    s["flow"]["elements"] = [element("a", "call_ai", ai_config_id="ai1")]
    s = save(c, s)
    r = c.get(f"/api/surveys/{s['survey_id']}/revisions?module=flow").json()[0]
    s["ai_configs"][0]["system_prompt"] = "Changed"
    s = save(c, s)
    assert s["ai_configs"][0]["config_version"] == 2
    restored = c.post(
        f"/api/surveys/{s['survey_id']}/revisions/{r['revision_id']}/restore?module=flow",
        json={"expected_version": s["working_version"]},
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["ai_configs"][0]["system_prompt"] == "Original"
    assert restored.json()["ai_configs"][0]["config_version"] == 3


def test_future_ai_input_blocked(client):
    c = client
    s = c.post("/api/projects").json()
    s["blocks"][0]["questions"] = [question()]
    s["ai_configs"] = [
        {
            "ai_config_id": "ai1",
            "agent_name": "Agent",
            "system_prompt": "Role",
            "user_message_template": "Task",
            "input_source_config": {"question_id": "q1"},
        }
    ]
    s["flow"]["elements"] = [
        element("a", "call_ai", ai_config_id="ai1"),
        element("b", "block", block_id=s["blocks"][0]["block_id"]),
    ]
    s = save(c, s)
    r = c.post(f"/api/surveys/{s['survey_id']}/preview-sessions")
    assert r.status_code == 422 and "future" in r.text


def test_matrix_values_and_required_rows(client):
    c = client
    s = c.post("/api/projects").json()
    q = question("matrixq")
    q["question_type"] = "matrix"
    q["config"] = {
        "matrix_type": "likert",
        "answer_type": "multiple",
        "statements": [{"statement_id": "s1", "label": "Statement"}],
        "scale_points": [
            {"choice_id": "c1", "value": 1, "label": "Agree"},
            {"choice_id": "c2", "value": 2, "label": "Disagree"},
        ],
    }
    s["blocks"][0]["questions"] = [q]
    s["flow"]["elements"] = [element("show", "block", block_id=s["blocks"][0]["block_id"])]
    s = save(c, s)
    v = c.post(f"/api/surveys/{s['survey_id']}/preview-sessions").json()
    pid = v["preview_session_id"]
    assert (
        c.post(
            "/api/preview-sessions/" + pid + "/next",
            json={"answers": {"matrixq": {"s1": []}}},
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/preview-sessions/" + pid + "/next",
            json={"answers": {"matrixq": {"s1": [999]}}},
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/api/preview-sessions/" + pid + "/next",
            json={"answers": {"matrixq": {"s1": [1, 2]}}},
        ).json()["page"]["kind"]
        == "end"
    )
