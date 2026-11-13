from copy import deepcopy
import json
import re
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import text

from .config import settings
from .models import ProjectImport
from .schemas import WorkingData
from .service import create_survey, fail, log_action, nodes, save, uid, validate
from .versions import digest

UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def uuid_key(value):
    if not UUID_PATTERN.fullmatch(value) or UUID(value).version != 4:
        fail("Imported identifiers must be UUID v4")
    return value.lower()


def unique_object(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise ValueError("Duplicate JSON key")
    return obj


def validate_json_values(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower().replace("-", "_") in {"api_key", "access_token", "refresh_token", "private_key", "public_access_token"}:
                fail("Project JSON must not contain credentials or access tokens")
            validate_json_values(key)
            validate_json_values(child)
    elif isinstance(value, list):
        for child in value:
            validate_json_values(child)
    elif isinstance(value, str) and "\x00" in value:
        fail("Project JSON contains an unsupported null character")


def parse_project(request, name):
    try:
        raw = json.loads(request.content.lstrip("\ufeff"), object_pairs_hook=unique_object)
        if not isinstance(raw, dict):
            fail("Project JSON must contain an object")
        raw["survey_name"] = name
        # Reject values JSONB cannot store.
        digest(raw)
        validate_json_values(raw)
        return WorkingData.model_validate(raw).model_dump(mode="json")
    except ValidationError as exc:
        fields = [".".join(map(str, error["loc"])) for error in exc.errors(include_input=False)[:5]]
        fail("Invalid Project Schema at " + ", ".join(fields))
    except (ValueError, RecursionError, UnicodeError):
        fail("Invalid JSON syntax or unsupported JSON value")


def remap(data):
    data = deepcopy(data)
    flow = data["flow"]
    flow_nodes = list(nodes(flow["elements"]))
    for entry in flow["trash"]:
        flow_nodes.extend(nodes([entry["element"]]))
    blocks = data["blocks"]
    questions = [question for block in blocks for question in block["questions"]]
    agents = data["ai_configs"]
    branch_groups = [group for node in flow_nodes for group in node["config"]["condition_groups"]]
    question_groups = [group for block in blocks for group in block["question_groups"]]
    all_ids = set()

    def assign(records, field):
        mapping = {}
        for record in records:
            key = uuid_key(record[field])
            if key in all_ids:
                fail("Duplicate UUID in Project JSON")
            all_ids.add(key)
            mapping[key] = record[field] = uid()
        return mapping

    block_ids = assign(blocks, "block_id")
    question_ids = assign(questions, "question_id")
    agent_ids = assign(agents, "ai_config_id")
    node_ids = assign(flow_nodes, "element_id")
    branch_ids = assign(branch_groups, "group_id")
    assign(question_groups, "group_id")

    def resolve(value, mapping, field):
        if value in (None, ""):
            return value
        new_id = mapping.get(uuid_key(value))
        if new_id is None:
            fail("Unknown project reference in " + field)
        return new_id

    for group in question_groups:
        group["question_ids"] = [resolve(value, question_ids, "Question Group") for value in group["question_ids"]]
    for node in flow_nodes:
        node["block_id"] = resolve(node["block_id"], block_ids, "Flow Block")
        node["ai_config_id"] = resolve(node["ai_config_id"], agent_ids, "Flow AI Config")
    from .python_node import REFERENCES
    response_id = re.compile(r"""(response\s*\[\s*)(['"])([a-fA-F0-9-]{36})\2(\s*\])""")
    for node in flow_nodes:
        if node["type"] == "python_code":
            node["config"]["python_code"] = REFERENCES.sub(
                lambda match: "{#" + resolve(match[1], question_ids, "Python Question") + "#}",
                node["config"]["python_code"],
            )
            node["config"]["python_code"] = response_id.sub(
                lambda match: match[1] + repr(resolve(match[3], question_ids, "Python Question")) + match[4],
                node["config"]["python_code"],
            )
    for group in branch_groups:
        for condition in group["conditions"]:
            if condition["source_type"] == "question":
                condition["source_id"] = resolve(condition["source_id"], question_ids, "Branch condition")
            elif condition["source_type"] == "agent":
                condition["source_id"] = resolve(condition["source_id"], agent_ids, "Branch Agent")
    for entry in flow["trash"]:
        entry["parent_id"] = resolve(entry["parent_id"], node_ids, "Flow Trash parent")
        entry["group_id"] = resolve(entry["group_id"], branch_ids, "Flow Trash group")
    options = data["survey_config"]["ai"]
    options["config_id"] = resolve(options["config_id"], agent_ids, "default AI Config")
    for agent in agents:
        source = agent["input_source_config"]
        source["question_id"] = resolve(source["question_id"], question_ids, "AI input Question")
        for field in ("context_template", "user_message_template"):
            def placeholder(match):
                value = match[1]
                if UUID_PATTERN.fullmatch(value):
                    return "{#" + resolve(value, question_ids | agent_ids, "AI template") + "#}"
                return match[0]

            agent[field] = re.sub(r"\{#(.*?)#\}", placeholder, agent[field])
        agent["config_version"] = 1
    validate(data)
    return data


def import_project(db, request):
    name = request.project_name.strip()
    if not 1 <= len(name) <= 100 or "\x00" in name:
        fail("Project Name must contain 1 to 100 characters")
    request_id = uuid_key(request.import_request_id)
    if not request.file_name.lower().endswith(".json"):
        fail("Only .json files are supported")
    if len(request.content.encode("utf-8", errors="surrogatepass")) > 2 * 1024 * 1024:
        fail("Project JSON exceeds 2 MiB", 413)
    try:
        content_hash = digest({"project_name": name, "file_name": request.file_name, "content": request.content})
    except UnicodeError:
        fail("Project JSON contains invalid Unicode")
    user_id = settings.dev_user_id
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": "project-import:" + user_id + ":" + request_id})
    previous = db.get(ProjectImport, (user_id, request_id))
    if previous:
        if previous.content_hash != content_hash:
            fail("Import request ID was already used for different content", 409)
        return {"survey_id": previous.survey_id}
    data = remap(parse_project(request, name))
    survey = create_survey(db, name, imported=True)
    sid = survey.survey_id
    save(db, sid, dict(data, expected_version=survey.working_version, save_type="apply"),
         commit=False, record_action=False)
    db.add(ProjectImport(user_id=user_id, import_request_id=request_id, survey_id=sid, content_hash=content_hash))
    log_action(db, sid, "IMPORT")
    db.commit()
    return {"survey_id": sid}
