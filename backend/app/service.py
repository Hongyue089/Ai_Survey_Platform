from uuid import uuid4
from copy import deepcopy
from datetime import timezone
import re
from fastapi import HTTPException
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session
from .models import *
from .schemas import WorkingData
from .config import settings, default_options


def uid():
    return str(uuid4())


def fail(message, code=422):
    raise HTTPException(code, message)


def access(db, sid, write=False, lock=False):
    member = db.get(SurveyMember, (sid, settings.dev_user_id))
    if not member:
        fail("Survey not found", 404)
    if write and member.role not in ("owner", "editor"):
        fail("Edit permission required", 403)
    stmt = select(Survey).where(Survey.survey_id == sid)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    s = db.scalar(stmt)
    if not s:
        fail("Survey not found", 404)
    return s


def dump_row(row, fields):
    return {k: getattr(row, k) for k in fields}


QFIELDS = [
    "question_id",
    "question_name",
    "question_type",
    "question_text",
    "sort_order",
    "required",
    "config",
    "is_deleted",
    "deleted_at",
]
BFIELDS = ["block_id", "block_name", "sort_order", "is_deleted", "deleted_at", "question_groups"]
AFIELDS = [
    "ai_config_id",
    "config_name",
    "config_version",
    "agent_type",
    "agent_name",
    "provider",
    "model",
    "system_prompt",
    "context_template",
    "user_message_template",
    "input_source_config",
    "temperature",
    "top_p",
    "max_output_tokens",
    "max_turns",
    "include_history",
    "history_window",
    "end_condition",
    "timeout_seconds",
    "max_retries",
    "failure_behavior",
    "response_format",
    "logging_config",
]


def iso(value):
    return (
        value.replace(tzinfo=timezone.utc).isoformat()
        if value.tzinfo is None
        else value.isoformat()
    )


def working(db, s):
    blocks = []
    for b in db.scalars(
        select(Block)
        .where(Block.survey_id == s.survey_id)
        .order_by(Block.sort_order, Block.block_id)
    ):
        block = dump_row(b, BFIELDS)
        block["questions"] = [
            dump_row(q, QFIELDS)
            for q in db.scalars(
                select(Question)
                .where(Question.survey_id == s.survey_id, Question.block_id == b.block_id)
                .order_by(Question.sort_order, Question.question_id)
            )
        ]
        blocks.append(block)
    flow = db.scalar(select(SurveyFlow).where(SurveyFlow.survey_id == s.survey_id))
    data = WorkingData(
        survey_name=s.survey_name,
        survey_config=s.survey_config,
        blocks=blocks,
        flow=flow.flow_json if flow else {},
        ai_configs=[
            dump_row(a, AFIELDS)
            for a in db.scalars(
                select(AIConfig).where(AIConfig.survey_id == s.survey_id).order_by(AIConfig.ai_config_id)
            )
        ],
    ).model_dump(mode="json")
    return {
        **data,
        "survey_id": s.survey_id,
        "project_type": s.project_type,
        "status": s.status,
        "working_version": s.working_version,
        "updated_at": iso(s.updated_at),
        "created_at": iso(s.created_at),
        "role": db.get(SurveyMember, (s.survey_id, settings.dev_user_id)).role,
    }


def log_action(db, sid, action, target_type="survey", target_id=None, **details):
    db.add(SurveyChangeLog(
        log_id=uid(), survey_id=sid, user_id=settings.dev_user_id, action_type=action,
        target_type=target_type, target_id=target_id or sid, details_json=details,
    ))


def log_trash_changes(db, sid, previous, data):
    def flags(working_data):
        deleted = {}
        for block in working_data["blocks"]:
            deleted["block", block["block_id"]] = block["is_deleted"]
            for question in block["questions"]:
                deleted["question", question["question_id"]] = question["is_deleted"]
        for entry in working_data["flow"]["trash"]:
            deleted["flow_element", entry["element"]["element_id"]] = True
        for element in nodes(working_data["flow"]["elements"]):
            deleted["flow_element", element["element_id"]] = False
        return deleted

    old = flags(previous)
    for target, is_deleted in flags(data).items():
        if target in old and is_deleted != old[target]:
            log_action(db, sid, "DELETE" if is_deleted else "RESTORE", *target)


def create_survey(db, name="New Survey", *, imported=False):
    if not db.get(User, settings.dev_user_id):
        fail("Run database initialization to create dev_admin", 503)
    sid = uid()
    s = Survey(
        survey_id=sid,
        survey_name=name,
        creator_id=settings.dev_user_id,
        last_modified_by=settings.dev_user_id,
        survey_config=default_options(),
    )
    db.add(s)
    db.flush()
    db.add_all(
        [
            SurveyMember(survey_id=sid, user_id=settings.dev_user_id, role="owner"),
            SurveyFlow(
                flow_id=uid(),
                survey_id=sid,
                flow_json={"schema_version": 1, "elements": [], "trash": []},
                updated_by=settings.dev_user_id,
            ),
        ]
    )
    if imported:
        return s
    db.add(Block(block_id=uid(), survey_id=sid, block_name="Block 1", sort_order=1))
    log_action(db, sid, "CREATE")
    db.commit()
    return working(db, s)


def nodes(elements, depth=0):
    if depth > 30:
        fail("Flow nesting limit exceeded")
    for e in elements:
        yield e
        yield from nodes(e.get("children", []), depth + 1)
        for g in e.get("config", {}).get("condition_groups", []):
            yield from nodes(g.get("children", []), depth + 1)


def collect_ids(value):
    ids = set()
    if isinstance(value, dict):
        for k, v in value.items():
            if k in (
                "block_id",
                "question_id",
                "source_id",
                "ai_config_id",
            ) and isinstance(v, str):
                ids.add(v)
            ids.update(collect_ids(v))
    elif isinstance(value, list):
        for v in value:
            ids.update(collect_ids(v))
    return ids


def agent_output_name(name):
    return "_".join(name.lower().split())


def validate(data, runtime=False):
    blocks = {b["block_id"]: b for b in data["blocks"]}
    questions = {q["question_id"]: q for b in data["blocks"] for q in b["questions"]}
    ais = {a["ai_config_id"]: a for a in data["ai_configs"]}
    ids = (
        [b["block_id"] for b in data["blocks"]]
        + [q["question_id"] for b in data["blocks"] for q in b["questions"]]
        + [a["ai_config_id"] for a in data["ai_configs"]]
    )
    if len(ids) != len(set(ids)):
        fail("Duplicate entity ID")
    for b in data["blocks"]:
        if b["is_deleted"]:
            continue
        member_ids = set()
        group_ids = set()
        valid = {q["question_id"] for q in b["questions"] if not q["is_deleted"]}
        for g in b.get("question_groups", []):
            if g["group_id"] in group_ids or len(g["question_ids"]) != len(set(g["question_ids"])):
                fail("Duplicate Question Group or member")
            group_ids.add(g["group_id"])
            if not set(g["question_ids"]) <= valid or member_ids & set(g["question_ids"]):
                fail("Question Groups must have distinct active Questions in their own Block")
            member_ids.update(g["question_ids"])
            if g["display_mode"] == "random_n" and g["display_count"] > len(g["question_ids"]):
                fail("Question Group display count exceeds member count")
    allnodes = list(nodes(data["flow"]["elements"]))
    for t in data["flow"]["trash"]:
        allnodes.extend(nodes([t["element"]]))
    fids = [e["element_id"] for e in allnodes]
    if len(fids) != len(set(fids)):
        fail("Duplicate Flow element ID / cyclic structure")
    group_ids = [
        g["group_id"] for e in allnodes for g in e["config"]["condition_groups"]
    ]
    if len(group_ids) != len(set(group_ids)):
        fail("Duplicate Branch group ID")
    active = list(nodes(data["flow"]["elements"]))
    active_ais = []
    for e in active:
        if e["type"] == "block":
            if not e["block_id"]:
                if runtime:
                    fail("Choose a Block for each Block element")
            elif e["block_id"] not in blocks:
                fail("Flow references a missing Block")
            elif blocks[e["block_id"]]["is_deleted"]:
                fail(
                    f"Block is referenced by Flow Element {e['element_id']}; remove reference before deletion"
                )
        if e["type"] == "randomizer":
            if any(c["type"] not in ("block", "branch") for c in e["children"]):
                fail("Randomizer children must be Block or Branch")
            if runtime and e["config"]["number_to_present"] > len(e["children"]):
                fail("Randomizer count exceeds child count")
        if e["type"] == "block_randomizer":
            if any(child["type"] != "block" for child in e["children"]):
                fail("Block Randomizer accepts Block elements only")
            if runtime and (not e["children"] or (
                e["config"]["randomization_mode"] != "shuffle"
                and e["config"]["number_to_present"] > len(e["children"])
            )):
                fail("Block Randomizer does not have enough Blocks")
        if e["type"] == "participant_randomizer" and runtime and len(e["config"]["condition_groups"]) < 2:
            fail("Participant Randomizer needs at least two Paths")
        if e["type"] == "python_code" and runtime and not e["config"]["python_code"].strip():
            fail("Enter Python Code before starting Preview")
        if e["type"] == "branch":
            if sum(group["is_default"] for group in e["config"]["condition_groups"]) > 1:
                fail("Branch can have only one Otherwise Path")
            if runtime and not e["config"]["condition_groups"]:
                fail("Branch requires a condition group")
            for g in e["config"]["condition_groups"]:
                if g["is_default"]:
                    continue
                if runtime and not g["conditions"]:
                    fail("Add a condition to each Branch Path")
                for c in g["conditions"]:
                    if c["source_type"] == "question" and c["source_id"]:
                        if (
                            c["source_id"] not in questions
                            or questions[c["source_id"]]["is_deleted"]
                        ):
                            fail(f"Question is referenced by Branch {e['element_id']}; remove reference before deletion")
                    elif c["source_type"] == "agent" and c["source_id"] and c["source_id"] not in ais:
                        fail("Branch references a missing Conversation Agent")
                    elif runtime and not c["source_id"]:
                        fail("Incomplete Branch condition")
        if (
            e["type"] == "embedded_data"
            and runtime
            and not re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*", e["config"]["variable_name"]
            )
        ):
            fail("Variable name must be an identifier")
        if e["type"] == "call_ai":
            a = ais.get(e["ai_config_id"])
            if not a:
                fail("AI Conversation Agent must reference an AI configuration in this Survey")
            if runtime and not all(a[field].strip() for field in ("system_prompt", "user_message_template")):
                fail(f"AI configuration is incomplete for {a['agent_name']}: enter System Prompt and User Message Template")
            active_ais.append(a)
            qid = a["input_source_config"].get("question_id")
            if qid and (qid not in questions or questions[qid]["is_deleted"]):
                fail("AI input references missing/deleted Question")
    if len({a["ai_config_id"] for a in active_ais}) != len(active_ais):
        fail("Each AI Conversation Agent must have an independent AI Config")
    if len({agent_output_name(a["agent_name"]) for a in active_ais}) != len(active_ais):
        fail("AI Conversation Agent names must be unique within this Survey")
    default = data["survey_config"]["ai"]["config_id"]
    if default and default not in ais:
        fail("Default AI Config belongs to another Survey or is missing")
    if runtime:
        active_questions = [
            q
            for b in data["blocks"]
            if not b["is_deleted"]
            for q in b["questions"]
            if not q["is_deleted"]
        ]
        name_to_id = {q["question_name"]: q["question_id"] for q in active_questions}
        if len(name_to_id) != len(active_questions):
            fail("Question Names must be unique for Preview placeholder resolution")

        def available(elements, known):
            known = set(known)
            for e in elements:
                typ = e["type"]
                if typ == "block" and e["block_id"]:
                    known.update(
                        q["question_id"]
                        for q in blocks[e["block_id"]]["questions"]
                        if not q["is_deleted"] and q["question_type"] != "text_graphic"
                    )
                elif typ == "embedded_data":
                    known.add(e["config"]["variable_name"])
                elif typ == "python_code":
                    known.add(None)  # Output dictionary keys are determined at execution.
                elif typ in ("branch", "participant_randomizer"):
                    for g in e["config"]["condition_groups"]:
                        for c in [] if typ == "participant_randomizer" or g.get("is_default") else g["conditions"]:
                            if c["source_id"] not in known and not (c["source_type"] == "variable" and None in known):
                                fail(
                                    "Branch references data unavailable before this Flow position"
                                )
                        available(g["children"], known)
                elif typ in ("randomizer", "block_randomizer"):
                    for c in e["children"]:
                        available([c], known)
                elif typ == "call_ai":
                    a = ais[e["ai_config_id"]]
                    source = a["input_source_config"].get("question_id")
                    if source and source not in known:
                        fail(
                            "AI Input Source references a future or conditional Question"
                        )
                    for placeholder in re.findall(
                        r"\{#(.*?)#\}",
                        a["context_template"] + " " + a["user_message_template"],
                    ):
                        if name_to_id.get(placeholder, placeholder) not in known and None not in known:
                            fail(
                                "AI Context references unavailable data: " + placeholder
                            )
                    known.update((a["ai_config_id"], a["agent_name"], agent_output_name(a["agent_name"]), "ai_" + a["agent_name"]))
                elif typ == "end_survey":
                    break
            return known

        available(data["flow"]["elements"], set())


def check_dependencies(previous, data):
    oldq = {q["question_id"]: q for b in previous["blocks"] for q in b["questions"]}
    newq = {q["question_id"]: q for b in data["blocks"] for q in b["questions"]}
    oldb = {b["block_id"]: b for b in previous["blocks"]}
    newb = {b["block_id"]: b for b in data["blocks"]}
    allnodes = list(nodes(data["flow"]["elements"]))
    for t in data["flow"]["trash"]:
        allnodes.extend(nodes([t["element"]]))
    for e in allnodes:
        references = []
        if e.get("block_id"):
            bid = e["block_id"]
            if bid in oldb and not oldb[bid]["is_deleted"] and (bid not in newb or newb[bid]["is_deleted"]):
                fail(f"Block is referenced by Flow Element {e['element_id']}; remove reference first", 409)
        for g in e["config"]["condition_groups"]:
            references.extend((c["source_id"], c["value"]) for c in g["conditions"] if c["source_type"] == "question")
        if e["type"] == "call_ai":
            a = next((a for a in data["ai_configs"] if a["ai_config_id"] == e["ai_config_id"]), None)
            if a:
                references.append((a["input_source_config"].get("question_id"), None))
                for qid, q in oldq.items():
                    if any("{#" + token + "#}" in a[field] for token in (qid, q["question_name"]) for field in ("context_template", "user_message_template")):
                        references.append((qid, None))
                        if qid in newq and q["question_name"] != newq[qid]["question_name"] and any("{#" + q["question_name"] + "#}" in a[field] for field in ("context_template", "user_message_template")):
                            fail(f"Question name is referenced by AI Flow Element {e['element_id']}; update template first", 409)
        for qid, value in references:
            old, new = oldq.get(qid), newq.get(qid)
            if not old:
                continue
            broken = not new or (not old["is_deleted"] and new["is_deleted"]) or old["question_type"] != new["question_type"]
            if value is not None and old["question_type"] == "multiple_choice":
                choice = next((c for c in old["config"]["choices"] if value in (c["value"], c["choice_id"])), None)
                if choice and new:
                    replacement = next((c for c in new["config"].get("choices", []) if c["choice_id"] == choice["choice_id"]), None)
                    broken |= not replacement or replacement["value"] != choice["value"]
            if broken:
                fail(f"Question / Option {qid} is referenced by Flow Element {e['element_id']}; remove reference first", 409)


def save(db, sid, payload, save_type=None, *, commit=True, record_action=True, base_revision_id=None):
    s = access(db, sid, write=True, lock=True)
    expected = payload["expected_version"]
    if s.working_version != expected:
        fail("Working Version changed in another tab. Reload before saving.", 409)
    kind = save_type or payload["save_type"]
    data = WorkingData.model_validate(
        {k: v for k, v in payload.items() if k not in ("expected_version", "save_type")}
    ).model_dump(mode="json")
    validate(data)
    old = working(db, s)
    previous = WorkingData.model_validate(
        {k: old[k] for k in WorkingData.model_fields}
    ).model_dump(mode="json")
    check_dependencies(previous, data)
    changed = data != previous
    current = db.get(SurveyRevision, s.working_revision_id) if s.working_revision_id else None
    if not changed and (kind == "auto" or (kind == "apply" and current and current.save_type == "apply")):
        return old
    existing_blocks = {
        b.block_id: b for b in db.scalars(select(Block).where(Block.survey_id == sid))
    }
    existing_qs = {
        q.question_id: q
        for q in db.scalars(select(Question).where(Question.survey_id == sid))
    }
    existing_ais = {
        a.ai_config_id: a
        for a in db.scalars(select(AIConfig).where(AIConfig.survey_id == sid))
    }
    new_bid = {b["block_id"] for b in data["blocks"]}
    new_qid = {q["question_id"] for b in data["blocks"] for q in b["questions"]}
    new_aid = {a["ai_config_id"] for a in data["ai_configs"]}
    if kind != "restore" and (
        not set(existing_blocks) <= new_bid
        or not set(existing_qs) <= new_qid
        or not set(existing_ais) <= new_aid
    ):
        fail("Entities cannot be omitted; use soft delete and Restore")

    def own(cls, identifier, existing):
        if identifier not in existing and db.get(cls, identifier):
            fail("Entity ID already belongs to a different Survey", 409)

    for a in data["ai_configs"]:
        own(AIConfig, a["ai_config_id"], existing_ais)
        obj = existing_ais.get(a["ai_config_id"])
        if not obj:
            obj = AIConfig(ai_config_id=a["ai_config_id"], survey_id=sid)
            db.add(obj)
        a = deepcopy(a)
        if obj.ai_config_id in existing_ais:
            orig = dump_row(obj, AFIELDS)
            a["config_version"] = orig["config_version"] + (
                any(orig[k] != a[k] for k in AFIELDS if k != "config_version")
            )
        for k, v in a.items():
            setattr(obj, k, v)
    db.flush()
    for b in data["blocks"]:
        own(Block, b["block_id"], existing_blocks)
        obj = existing_blocks.get(b["block_id"])
        if not obj:
            obj = Block(block_id=b["block_id"], survey_id=sid)
            db.add(obj)
        was_deleted = (
            existing_blocks.get(b["block_id"]).is_deleted
            if b["block_id"] in existing_blocks
            else False
        )
        for k in BFIELDS:
            if k != "deleted_at":
                setattr(obj, k, b[k])
        obj.deleted_at = (obj.deleted_at or now()) if b["is_deleted"] else None
        db.flush()
        for q in b["questions"]:
            own(Question, q["question_id"], existing_qs)
            qo = existing_qs.get(q["question_id"])
            if not qo:
                qo = Question(question_id=q["question_id"], block_id=b["block_id"], survey_id=sid)
                db.add(qo)
            if qo.block_id != b["block_id"]:
                fail("Question cannot move between Blocks in this release")
            if b["is_deleted"] and not q["is_deleted"]:
                fail("Questions inside deleted Blocks must be deleted")
            for k in QFIELDS:
                if k != "deleted_at":
                    setattr(qo, k, q[k])
            qo.deleted_at = (qo.deleted_at or now()) if q["is_deleted"] else None
    if kind == "restore":
        for identifier, obj in existing_qs.items():
            if identifier not in new_qid:
                obj.is_deleted = True
                obj.deleted_at = now()
        for identifier, obj in existing_blocks.items():
            if identifier not in new_bid:
                obj.is_deleted = True
                obj.deleted_at = now()
    f = db.scalar(select(SurveyFlow).where(SurveyFlow.survey_id == sid))
    if f is None:
        f = SurveyFlow(flow_id=uid(), survey_id=sid, flow_version=1, flow_json=previous["flow"])
        db.add(f)
    flow_changed = (
        f.flow_json != data["flow"] or previous["ai_configs"] != data["ai_configs"]
    )
    if flow_changed:
        f.flow_version += 1
        f.flow_json = data["flow"]
        f.updated_by = settings.dev_user_id
    s.survey_name = data["survey_name"]
    s.survey_config = data["survey_config"]
    s.ai_config_id = data["survey_config"]["ai"]["config_id"]
    if changed:
        s.updated_at = now()
        s.last_modified_by = settings.dev_user_id
    if changed or kind == "restore":
        s.working_version += 1
    s.revision_sequence += 1
    db.flush()
    snapshot = working(db, s)
    revision = SurveyRevision(
        revision_id=uid(), survey_id=sid, revision_number=s.revision_sequence,
        survey_json=snapshot, save_type=kind, created_by=settings.dev_user_id,
        base_revision_id=base_revision_id or (
            current.revision_id if kind == "apply" and current and current.save_type == "auto" and not changed else None
        ),
    )
    db.add(revision)
    db.flush()
    s.working_revision_id = revision.revision_id
    if record_action:
        log_trash_changes(db, sid, previous, snapshot)
        log_action(
            db, sid, {"auto": "UPDATE", "apply": "APPLY", "restore": "RESTORE"}[kind],
            "revision", revision.revision_id,
        )
    autos = list(
        db.scalars(
            select(SurveyRevision)
            .where(SurveyRevision.survey_id == sid, SurveyRevision.save_type == "auto")
            .order_by(SurveyRevision.revision_number.desc())
        )
    )
    protected = set(db.scalars(select(SurveyRevision.base_revision_id).where(
        SurveyRevision.survey_id == sid, SurveyRevision.base_revision_id.is_not(None),
    )))
    ordinary_autos = [r for r in autos if r.revision_id not in protected]
    for r in ordinary_autos[20:]:
        db.delete(r)
    if commit:
        db.commit()
    else:
        db.flush()
    return working(db, s)


def permanent_delete(db, sid, kind, identifier):
    access(db, sid, True, True)
    fail("Permanent deletion is disabled in V1; use Restore", 409)
