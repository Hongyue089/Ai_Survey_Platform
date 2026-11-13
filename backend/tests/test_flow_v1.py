from test_workflow import client, element, question, save
from app.python_node import run_python


def start(client, survey):
    response = client.post(f"/api/surveys/{survey['survey_id']}/preview-sessions")
    assert response.status_code == 201, response.text
    return response.json()


def test_python_result_routes_preview_and_reports_safe_errors(client):
    s = client.post("/api/projects").json()
    s["blocks"][0]["questions"] = [question("q1")]
    show = element("ask", "block", block_id=s["blocks"][0]["block_id"])
    calculate = element("score", "python_code", config={
        "name": "Score", "python_code": 'result = {"score": int({#q1#}) + 2}',
    })
    route = element("route", "branch", config={"routing_mode": "first", "condition_groups": [
        {"group_id": "match", "logic": "AND", "conditions": [
            {"source_type": "variable", "source_id": "score", "operator": "greater_equal", "value": "40"},
        ], "children": [element("matched", "end_survey", config={"end_information": "Matched"})]},
        {"group_id": "other", "is_default": True, "conditions": [],
         "children": [element("fallback", "end_survey", config={"end_information": "Fallback"})]},
    ]})
    s["flow"]["elements"] = [show, calculate, route]
    s = save(client, s)
    for answer, expected in [("38", "Matched"), ("30", "Fallback")]:
        session = start(client, s)["preview_session_id"]
        page = client.post(f"/api/preview-sessions/{session}/next", json={"answers": {"q1": answer}}).json()["page"]
        assert page["end_information"] == expected

    session = start(client, s)["preview_session_id"]
    base = f"/api/preview-sessions/{session}"
    error = client.post(base + "/next", json={"answers": {"q1": "invalid"}}).json()["page"]
    assert error["kind"] == "python_error"
    assert error["name"] == "Score" and error["line"] == 1
    assert client.post(base + "/next", json={"answers": {}}).json()["page"] == error
    assert run_python('import os\nresult = {}', {})["error"] == "ValueError"
    assert run_python('result = {"answer": {#qid#}}', {"qid": '"quoted"'})["result"] == {"answer": '"quoted"'}


def test_randomizers_choose_paths_and_preserve_allocation(client):
    s = client.post("/api/projects").json()
    first = s["blocks"][0]["block_id"]
    s["blocks"].append(dict(s["blocks"][0], block_id="second", block_name="Second"))
    s["flow"]["elements"] = [element("participants", "participant_randomizer", config={
        "randomization_mode": "balanced",
        "condition_groups": [
            {"group_id": "a", "conditions": [], "children": [element("a-block", "block", block_id=first)]},
            {"group_id": "b", "conditions": [], "children": [element("b-block", "block", block_id="second")]},
        ],
    }), element("blocks", "block_randomizer", config={"randomization_mode": "shuffle"}, children=[
        element("pick-first", "block", block_id=first),
        element("pick-second", "block", block_id="second"),
    ])]
    s = save(client, s)
    seen = set()
    for _ in range(2):
        preview = start(client, s)
        seen.add(preview["page"]["element_id"])
        base = f"/api/preview-sessions/{preview['preview_session_id']}"
        assert client.get(base).json()["page"]["element_id"] == preview["page"]["element_id"]
        picked = [client.post(base + "/next", json={"answers": {}}).json()["page"]["element_id"] for _ in range(2)]
        assert set(picked) == {"pick-first", "pick-second"}
        assert client.post(base + "/next", json={"answers": {}}).json()["page"]["kind"] == "end"
        assert client.post(base + "/submit").status_code == 200
    assert seen == {"a-block", "b-block"}


def test_conversation_history_and_quit_stay_within_preview(client, monkeypatch):
    from app import preview

    calls = []

    async def reply(config, messages):
        calls.append(messages)
        return config["agent_name"] + " opening", {}, "test-model"

    monkeypatch.setattr(preview, "ai_request", reply)
    s = client.post("/api/projects").json()
    s["ai_configs"] = [
        {"ai_config_id": "first", "agent_name": "First agent", "system_prompt": "First", "user_message_template": "Start"},
        {"ai_config_id": "second", "agent_name": "Second agent", "system_prompt": "Second", "user_message_template": "Start",
         "input_source_config": {"include_previous_conversation": True, "allow_participant_quit": False}},
    ]
    s["flow"]["elements"] = [element(agent, "call_ai", ai_config_id=agent) for agent in ("first", "second")]
    s = save(client, s)
    base = "/api/preview-sessions/" + start(client, s)["preview_session_id"]
    assert client.post(base + "/chat", json={"message": ""}).json()["page"]["can_quit"]
    assert client.post(base + "/quit-conversation").json()["page"]["done"]
    assert client.post(base + "/next", json={"answers": {}}).json()["page"]["kind"] == "ai"
    assert not client.post(base + "/chat", json={"message": ""}).json()["page"]["can_quit"]
    assert "First agent opening" in calls[1][0]["content"]
    assert client.post(base + "/quit-conversation").status_code == 409
