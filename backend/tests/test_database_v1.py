import json
from uuid import uuid4

from test_workflow import client, element, payload, question, save


def draft_import():
    block, qid, node, branch, group, nested, agent = (str(uuid4()) for _ in range(7))
    return {
        "blocks": [{"block_id": block, "block_name": "Imported", "sort_order": 1,
                    "questions": [question(qid)]}],
        "flow": {"elements": [
            {"node_id": node, "type": "block", "sort_order": 1, "block_id": block},
            element(branch, "branch", config={"condition_groups": [{
                "group_id": group,
                "conditions": [{"source_id": qid, "value": "yes"}],
                "children": [element(nested, "call_ai", ai_config_id=agent)],
            }]}),
        ]},
        "ai_configs": [{"ai_config_id": agent, "system_prompt": "Role",
                        "user_message_template": "Ask {#" + qid + "#}",
                        "input_source_config": {"question_id": qid}}],
    }


def test_import_maps_references_and_retries_only_same_request(client):
    project = draft_import()
    endpoint = "/api/projects/import"
    body = {"import_request_id": str(uuid4()), "project_name": "First",
            "file_name": "project.json", "content": json.dumps(project)}
    response = client.post(endpoint, json=body)
    assert response.status_code == 201, response.text
    first = response.json()["survey_id"]
    assert client.post(endpoint, json=body).json()["survey_id"] == first
    assert client.post(endpoint, json=dict(body, project_name="Different")).status_code == 409
    second = client.post(endpoint, json=dict(body, import_request_id=str(uuid4()))).json()["survey_id"]
    assert first != second
    assert client.get("/api/projects").json()["total"] == 2

    imported = client.get(f"/api/surveys/{first}/working").json()
    block = imported["blocks"][0]
    qid = block["questions"][0]["question_id"]
    show, branch = imported["flow"]["elements"]
    group = branch["config"]["condition_groups"][0]
    agent = imported["ai_configs"][0]
    assert block["block_id"] != project["blocks"][0]["block_id"]
    assert show["block_id"] == block["block_id"]
    assert group["conditions"][0]["source_id"] == qid
    assert group["children"][0]["ai_config_id"] == agent["ai_config_id"]
    assert agent["input_source_config"]["question_id"] == qid
    assert "{#" + qid + "#}" in agent["user_message_template"]
    assert client.post(f"/api/surveys/{first}/preview-sessions").status_code == 201

    project["flow"]["elements"][0]["block_id"] = str(uuid4())
    invalid = client.post(endpoint, json=dict(body, import_request_id=str(uuid4()), content=json.dumps(project)))
    assert invalid.status_code == 422
    assert client.get("/api/projects").json()["total"] == 2


def test_preview_and_publish_pin_revision_while_reusing_snapshot(client):
    survey = client.post("/api/projects").json()
    base = f"/api/surveys/{survey['survey_id']}"
    assert "No Flow configured" in client.post(base + "/preview-sessions").text
    survey["blocks"][0]["questions"] = [question()]
    survey["flow"]["elements"] = [element("show", "block", block_id=survey["blocks"][0]["block_id"])]
    saved = client.put(base + "/working", json=dict(payload(survey), save_type="auto")).json()
    assert client.post(base + "/preview-sessions", params={"expected_version": survey["working_version"]}).status_code == 409
    first = client.post(base + "/preview-sessions", params={"expected_version": saved["working_version"]}).json()
    for _ in range(2):
        published = client.post(base + "/publish", json={"expected_version": saved["working_version"]})
        assert published.status_code == 200, published.text
    history = client.get(base + "/revisions?module=flow").json()
    publications = [item for item in history if item["save_type"] == "published"]
    assert len({item["revision_id"] for item in publications}) == 2

    changed = client.get(base + "/working").json()
    changed["survey_name"] = "New draft"
    changed = save(client, changed)
    new = client.post(base + "/preview-sessions").json()
    assert new["snapshot_id"] != first["snapshot_id"]
    assert client.get(f"/api/preview-sessions/{first['preview_session_id']}").json()["survey_name"] == survey["survey_name"]

    restored = client.post(base + f"/revisions/{publications[0]['revision_id']}/restore",
                           json={"expected_version": changed["working_version"]}).json()
    assert restored["survey_name"] == survey["survey_name"]
    reused = client.post(base + "/preview-sessions").json()
    assert reused["snapshot_id"] == first["snapshot_id"]
    assert reused["revision_id"] != first["revision_id"]


def test_preview_submit_archives_ai_and_excludes_old_branch(client, monkeypatch):
    from app import preview

    async def reply(config, messages):
        return "AI answer", {}, "test-model"

    monkeypatch.setattr(preview, "ai_request", reply)
    s = client.post("/api/projects").json()
    first = s["blocks"][0]
    first["questions"] = [question("route")]
    second = dict(first, block_id="second", sort_order=2, questions=[question("optional")])
    s["blocks"].append(second)
    s["ai_configs"] = [{"ai_config_id": "ai", "system_prompt": "Role",
                        "user_message_template": "Task", "max_turns": 1}]
    s["flow"]["elements"] = [
        element("show", "block", block_id=first["block_id"]),
        element("branch", "branch", config={"condition_groups": [{
            "group_id": "yes", "conditions": [{"source_id": "route", "value": "yes"}],
            "children": [element("details", "block", block_id="second"),
                         element("talk", "call_ai", ai_config_id="ai")],
        }]}),
    ]
    s = save(client, s)
    base = f"/api/surveys/{s['survey_id']}"
    initial = client.post(base + "/preview-sessions").json()
    snapshot = initial["snapshot_id"]
    data_url = base + f"/preview-data/{snapshot}"

    def take_branch(view):
        url = "/api/preview-sessions/" + view["preview_session_id"]
        assert client.post(url + "/submit").status_code == 409
        assert client.post(url + "/next", json={"answers": {"route": "yes"}}).json()["page"]["kind"] == "block"
        assert client.post(url + "/next", json={"answers": {"optional": "obsolete"}}).json()["page"]["kind"] == "ai"
        assert client.post(url + "/chat", json={"message": ""}).status_code == 200
        assert client.post(url + "/chat", json={"message": "participant text"}).json()["page"]["done"]
        assert client.post(url + "/next", json={"answers": {}}).json()["page"]["kind"] == "end"
        return url

    first_url = take_branch(initial)
    assert client.get(data_url).json()["total"] == 0
    for _ in range(3):
        assert client.post(first_url + "/back").status_code == 200
    end = client.post(first_url + "/next", json={"answers": {"route": "no"}}).json()
    assert end["page"]["kind"] == "end"
    assert end["answers"] == {"route": "no"}
    assert client.post(first_url + "/submit").json()["submitted"]
    assert client.post(first_url + "/submit").json()["submitted"]
    rows = client.get(data_url).json()["items"]
    assert len(rows) == 1 and rows[0]["content"] == []

    second_url = take_branch(client.post(base + "/preview-sessions").json())
    assert client.post(second_url + "/submit").json()["submitted"]
    assert client.delete(second_url).status_code == 204
    items = client.get(data_url).json()["items"]
    assert len(items) == 2
    assert items[0]["content"][0]["messages"][1]["content"] == "participant text"
    assert "participant text" in client.get(data_url + "/csv").text
    assert client.get("/api/projects").json()["items"][0]["response_count"] == 0
