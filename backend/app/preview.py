from .python_node import run_python
from decimal import Decimal, InvalidOperation
import operator
from copy import deepcopy
from datetime import timedelta
import random, json, re, time
import httpx
from sqlalchemy import select, delete, func
from .models import *
from .service import uid, fail, access, agent_output_name
from .config import settings
from .versions import prepare_execution


# Preview state lives in PostgreSQL; sessions are frozen and never formal Responses.
def new_session(db, sid, expected_version=None):
    _, revision, snapshot = prepare_execution(db, sid, expected_version)
    elements = deepcopy(snapshot.snapshot_json["flow"]["elements"])
    runtime = {
        "queue": elements,
        "answers": {},
        "variables": {},
        "allocations": {},
        "history": [],
        "cursor": -1,
        "ended": False,
        "visited": [],
    }
    session = PreviewSession(
        preview_session_id=uid(),
        survey_id=sid,
        user_id=settings.dev_user_id,
        snapshot_id=snapshot.snapshot_id,
        revision_id=revision.revision_id,
        snapshot_json={},  # Old installations store an inline copy here.
        runtime_json=deepcopy(runtime),
        expires_at=now() + timedelta(hours=2),
    )
    db.add(session)
    db.flush()
    advance(db, session, runtime)
    session.runtime_json = deepcopy(runtime)
    db.commit()
    return view(db, session)


def cleanup_expired(db):
    expired = db.scalars(
        select(PreviewSession).where(
            PreviewSession.expires_at < now(), PreviewSession.runtime_json != {}
        ).order_by(PreviewSession.expires_at).limit(200).with_for_update(skip_locked=True)
    ).all()
    if not expired:
        return
    identifiers = [session.preview_session_id for session in expired]
    db.execute(delete(AIConversation).where(AIConversation.preview_session_id.in_(identifiers)))
    for session in expired:
        if session.snapshot_id:
            if session.status == "active":
                session.status = "failed" if session.runtime_json.get("failed") else "terminated"
                session.ended_at = now()
            session.runtime_json = {}
        else:
            db.delete(session)


def execution_data(db, session):
    if session.snapshot_id:
        return db.get(SurveySnapshot, session.snapshot_id).snapshot_json
    return session.snapshot_json


def load_session(db, identifier):
    session = db.scalar(
        select(PreviewSession)
        .where(PreviewSession.preview_session_id == identifier)
        .with_for_update()
    )
    if not session or session.user_id != settings.dev_user_id:
        fail("Preview Session not found", 404)
    access(db, session.survey_id, write=True)
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=now().tzinfo)
    if expires < now() or not session.runtime_json:
        fail("Preview Session expired or ended. Restart Preview.", 410)
    return session


def fold(values, connectors):
    if not values:
        return False
    result = values[0]
    for val, connector in zip(values[1:], connectors[1:]):
        result = (result and val) if connector == "AND" else (result or val)
    return result


def condition_match(c, state, snapshot):
    source = {"question": state["answers"], "variable": state["variables"],
              "agent": state.get("agent_outputs", {})}[c["source_type"]]
    if c["source_id"] not in source:
        return False  # Randomly omitted Questions have no response; neither comparison matches.
    actual = source.get(c["source_id"])
    expected = c["value"]
    # Flow may store stable choice IDs; respondent answers use Choice values.
    if c["source_type"] == "question":
        q = next(
            (
                q
                for b in snapshot["blocks"]
                for q in b["questions"]
                if q["question_id"] == c["source_id"]
            ),
            None,
        )
        if q:
            choice = next(
                (
                    v
                    for v in q["config"].get("choices", [])
                    if v["choice_id"] == expected
                ),
                None,
            )
            if choice:
                expected = choice["value"]
    op = c["operator"]
    if c["source_type"] == "variable" and type(actual) in (int, float) and isinstance(expected, str):
        try:
            expected = Decimal(expected)
        except InvalidOperation:
            pass
    if op in ("equals", "not_equals"):
        equals = expected in actual if isinstance(actual, list) else actual == expected
        return equals if op == "equals" else not equals
    if op in ("contains", "not_contains"):
        if isinstance(actual, str):
            contains = str(expected) in actual
        elif isinstance(actual, (list, dict)):
            try:
                contains = expected in actual
                if c["source_type"] == "agent" and isinstance(expected, str):
                    contains = any(expected in message["content"] for message in actual)
            except TypeError:
                return False
        else:
            return False
        return contains if op == "contains" else not contains
    comparisons = {"greater": operator.gt, "greater_equal": operator.ge,
                   "less": operator.lt, "less_equal": operator.le}
    try:
        left, right = Decimal(str(actual)), Decimal(str(expected))
        return left.is_finite() and right.is_finite() and comparisons[op](left, right)
    except InvalidOperation:
        return False


def branch_children(config, state, snapshot):
    groups = config["condition_groups"]
    candidates = [group for group in groups if not group.get("is_default")]
    mode = config.get("routing_mode")
    matches = []
    for group in candidates:
        values = [condition_match(c, state, snapshot) for c in group["conditions"]]
        logic = group.get("logic")
        matches.append(
            bool(values) and (all(values) if logic == "AND" else any(values)) if logic
            else fold(values, [c["connector"] for c in group["conditions"]])
        )
    selected = [group for group, match in zip(candidates, matches) if match]
    if mode is None and not fold(matches, [group["connector"] for group in candidates]):
        selected = []
    if not selected:
        selected = [group for group in groups if group.get("is_default")][:1]
    if mode == "first":
        selected = selected[:1]
    return [child for group in selected for child in group["children"]]


def participant_children(db, session, state, element):
    paths = {group["group_id"]: group for group in element["config"]["condition_groups"]}
    node_id = element["element_id"]
    assigned = state["allocations"].get(node_id)
    if assigned:
        return paths[assigned[0]]["children"]
    choices = list(paths)
    if element["config"].get("randomization_mode") == "balanced":
        if db.bind.dialect.name == "postgresql":
            from sqlalchemy import text
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                       {"key": session.survey_id + node_id})
        counts = dict.fromkeys(choices, 0)
        active = db.scalars(select(PreviewSession.runtime_json).where(
            PreviewSession.survey_id == session.survey_id,
            PreviewSession.status == "active",
            PreviewSession.preview_session_id != session.preview_session_id,
            PreviewSession.expires_at > now(),
        ))
        completed = db.scalars(select(PreviewResponse.response_json).where(
            PreviewResponse.survey_id == session.survey_id,
        ))
        for record in [*active, *completed]:
            for path_id in record.get("allocations", {}).get(node_id, []):
                if path_id in counts:
                    counts[path_id] += 1
        choices = [path_id for path_id in choices if counts[path_id] == min(counts.values())]
    path_id = random.choice(choices)
    state["allocations"][node_id] = [path_id]
    return paths[path_id]["children"]


def block_pages(block, state):
    key = "block:" + block["block_id"]
    qs = sorted((q for q in block["questions"] if not q["is_deleted"]), key=lambda q: q["sort_order"])
    if key not in state["allocations"]:
        byid = {q["question_id"]: q for q in qs}
        groups = block.get("question_groups", [])
        memberships = {qid: g for g in groups for qid in g["question_ids"]}
        seen, ordered = set(), []
        for q in qs:
            g = memberships.get(q["question_id"])
            if not g:
                ordered.append(q["question_id"])
                continue
            if g["group_id"] in seen:
                continue
            seen.add(g["group_id"])
            ids = [x["question_id"] for x in qs if x["question_id"] in g["question_ids"]]
            if g["display_mode"] == "random_n":
                chosen = set(random.sample(ids, g["display_count"]))
                ids = [qid for qid in ids if qid in chosen]
            if g["question_order"] == "random":
                random.shuffle(ids)
            ordered.extend(ids)
        state["allocations"][key] = ordered
    byid = {q["question_id"]: q for q in qs}
    ordered = [byid[qid] for qid in state["allocations"][key]]
    pages, batch = [], []
    for q in ordered:
        rt = q["question_type"] == "multiple_choice" and q["config"].get("response_time", {}).get("enabled")
        if rt:
            if batch:
                pages.append(batch)
                batch = []
            pages.append([q])
        else:
            batch.append(q)
    if batch or not pages:
        pages.append(batch)
    return [{**deepcopy(block), "questions": questions} for questions in pages]


def advance(db, session, state):
    snapshot = execution_data(db, session)
    blocks = {b["block_id"]: b for b in snapshot["blocks"]}
    while state["queue"]:
        e = state["queue"].pop(0)
        typ = e["type"]
        cfg = e.get("config", {})
        if typ != "display_page":
            labels = {"branch": "Branch", "randomizer": "Randomizer", "embedded_data": "Embedded Data",
                      "call_ai": "Conversation Agent", "end_survey": "End of Survey",
                      "block_randomizer": "Block Randomizer", "participant_randomizer": "Participant Randomizer",
                      "python_code": "Python Code"}
            label = blocks[e["block_id"]]["block_name"] if typ == "block" else cfg.get("name") or labels.get(typ, typ)
            state.setdefault("visited", []).append({"element_id": e["element_id"], "label": label})
        if typ == "block":
            b = blocks[e["block_id"]]
            if not b["is_deleted"]:
                pages = block_pages(b, state)
                state["queue"] = [{"type": "display_page", "element_id": e["element_id"], "block": page} for page in pages] + state["queue"]
        elif typ == "display_page":
            page = {"kind": "block", "element_id": e["element_id"], "page_id": uid(), "block": e["block"]}
            page["checkpoint"] = {
                "queue": deepcopy(state["queue"]),
                "answers": deepcopy(state["answers"]),
                "variables": deepcopy(state["variables"]),
                "agent_outputs": deepcopy(state.get("agent_outputs", {})),
                "visited_count": len(state.get("visited", [])),
            }
            state["history"].append(page)
            state["cursor"] = len(state["history"]) - 1
            return
        elif typ == "branch":
            state["queue"] = branch_children(cfg, state, snapshot) + state["queue"]
        elif typ == "participant_randomizer":
            state["queue"] = participant_children(db, session, state, e) + state["queue"]
        elif typ in ("randomizer", "block_randomizer"):
            children = e["children"]
            n = len(children) if cfg.get("randomization_mode") == "shuffle" else cfg["number_to_present"]
            prior_allocation = state["allocations"].get(e["element_id"])
            if prior_allocation is not None:
                chosen = [next(c for c in children if c["element_id"] == identifier) for identifier in prior_allocation]
            elif typ == "randomizer" and cfg["evenly_present"]:
                # Transactional preview-only balancing across unexpired sessions.
                if db.bind.dialect.name == "postgresql":
                    from sqlalchemy import text

                    db.execute(
                        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                        {"key": session.survey_id + e["element_id"]},
                    )
                counts = {c["element_id"]: 0 for c in children}
                for prior in db.scalars(
                    select(PreviewSession).where(
                        PreviewSession.survey_id == session.survey_id,
                        PreviewSession.preview_session_id != session.preview_session_id,
                        PreviewSession.expires_at > now(),
                    )
                ):
                    for chosen in prior.runtime_json.get("allocations", {}).get(
                        e["element_id"], []
                    ):
                        if chosen in counts:
                            counts[chosen] += 1
                random.shuffle(children)
                chosen = sorted(children, key=lambda c: counts[c["element_id"]])[:n]
                random.shuffle(chosen)
            else:
                chosen = random.sample(children, n)
            state["allocations"][e["element_id"]] = [c["element_id"] for c in chosen]
            state["queue"] = chosen + state["queue"]
        elif typ == "python_code":
            answers = dict(state["answers"])
            for block in snapshot["blocks"]:
                for question in block["questions"]:
                    if question["question_id"] in state["answers"]:
                        answers.setdefault(question["question_name"], state["answers"][question["question_id"]])
            outcome = run_python(cfg.get("python_code", ""), answers)
            if "error" in outcome:
                state["history"].append({"kind": "python_error", "element_id": e["element_id"],
                                         "name": cfg.get("name") or "Python Code", "node": e, **outcome})
                state["cursor"] = len(state["history"]) - 1
                return
            state["variables"].update(outcome["result"])
        elif typ == "embedded_data":
            state["variables"][cfg["variable_name"]] = cfg["value"]
        elif typ == "end_survey":
            state["queue"] = []
            state["end_information"] = cfg.get("end_information", "")
            break
        elif typ == "call_ai":
            a = next(
                a
                for a in snapshot["ai_configs"]
                if a["ai_config_id"] == e["ai_config_id"]
            )
            conv = AIConversation(
                conversation_id=uid(),
                preview_session_id=session.preview_session_id,
                survey_id=session.survey_id,
                snapshot_id=session.snapshot_id,
                flow_element_id=e["element_id"],
                ai_config_id=a["ai_config_id"],
                config_version=a["config_version"],
                agent_name=a["agent_name"],
                ai_conversation_json={
                    "agent_name": a["agent_name"],
                    "max_turns": a["max_turns"],
                    "turns": [],
                },
            )
            db.add(conv)
            db.flush()
            page = {
                "kind": "ai",
                "element_id": e["element_id"],
                "conversation_id": conv.conversation_id,
                "config": a,
                "messages": [],
                "turn_count": 0,
                "done": False,
                "error": None,
            }
            state["history"].append(page)
            state["cursor"] = len(state["history"]) - 1
            return
    state["ended"] = True
    state["history"].append({"kind": "end", "end_information": state.get("end_information", "")})
    state["cursor"] = len(state["history"]) - 1


def view(db, session):
    state = session.runtime_json
    page = deepcopy(state["history"][state["cursor"]])
    snapshot = execution_data(db, session)
    page.pop("checkpoint", None)
    page.pop("submitted_answers", None)
    page.pop("node", None)
    # Prompts stay on the server, even in respondent UI.
    if page["kind"] == "ai":
        page["can_quit"] = page["config"]["input_source_config"].get("allow_participant_quit", True) and not page["done"]
        page["config"] = {
            k: page["config"][k]
            for k in ("agent_name", "max_turns", "failure_behavior")
        }
    return {
        "preview_session_id": session.preview_session_id,
        "survey_id": session.survey_id,
        "page": page,
        "answers": state["answers"],
        "survey_config": snapshot["survey_config"],
        "survey_name": snapshot["survey_name"],
        "can_back": session.status == "active" and state["cursor"] > 0
        and snapshot["survey_config"]["responses"]["allow_back_button"],
        "can_continue": state["cursor"] < len(state["history"]) - 1,
        "working_version": (
            db.get(SurveyRevision, session.revision_id).survey_json["working_version"]
            if session.revision_id else snapshot["working_version"]
        ),
        "snapshot_id": session.snapshot_id,
        "revision_id": session.revision_id,
        "submitted": session.status == "completed",
        "failed": bool(state.get("failed")),
        "execution_path": state.get("visited", []),

        "expires_at": session.expires_at.isoformat(),
        "timing_debug": state.get("timing_records", []),
    }


def validate_answers(page, answers):
    allowed = {
        q["question_id"]: q
        for q in page["block"]["questions"]
        if not q["is_deleted"] and q["question_type"] != "text_graphic"
    }
    if set(answers) - set(allowed):
        fail("Answers contain Questions outside current Preview page")
    for qid, q in allowed.items():
        value = answers.get(qid)
        cfg = q["config"]
        empty = value is None or value == "" or value == [] or value == {}
        if q["required"] and empty:
            fail("Required Question: " + q["question_name"])
        if empty:
            continue
        typ = q["question_type"]
        if typ == "text_entry":
            if not isinstance(value, str) or len(value) > cfg["max_characters"]:
                fail("Invalid text length: " + q["question_name"])
        elif typ == "multiple_choice":
            values = {c["value"] for c in cfg["choices"]}
            if cfg["answer_type"] == "single":
                if type(value) != int or value not in values:
                    fail("Invalid Choice value")
            elif (
                not isinstance(value, list)
                or any(type(v) != int or v not in values for v in value)
                or len(value) != len(set(value))
                or not cfg["min_selection"] <= len(value) <= cfg["max_selection"]
            ):
                fail("Invalid multiple selection range")
        elif typ == "matrix":
            if not isinstance(value, dict):
                fail("Matrix Answer must be an object")
            sids = {s["statement_id"] for s in cfg["statements"]}
            values = {c["value"] for c in cfg["scale_points"]}
            if set(value) - sids:
                fail("Unknown Matrix statement")
            for sid in sids:
                v = value.get(sid)
                if v is None or v == []:
                    if q["required"]:
                        fail("Required Matrix statement")
                    continue
                if cfg["answer_type"] == "single":
                    if type(v) != int or v not in values:
                        fail("Invalid Matrix selection")
                elif (
                    not isinstance(v, list)
                    or any(type(x) != int or x not in values for x in v)
                    or len(v) != len(set(v))
                ):
                    fail("Invalid Matrix multiple selection")


def record_timings(session, state, page, timings):
    allowed = {q["question_id"]: q for q in page["block"]["questions"] if q["question_type"] == "multiple_choice" and q["config"].get("response_time", {}).get("enabled")}
    if len({t["question_id"] for t in timings}) != len(timings):
        fail("Duplicate timing payload")
    if set(allowed) != {t["question_id"] for t in timings}:
        fail("Current RT page requires timing events")
    records = []
    for timing in timings:
        qid = timing["question_id"]
        if qid not in allowed:
            fail("Timing Question is outside the current RT page")
        events = timing["events"]
        if not events or events[0]["event"] != "question_displayed" or events[-1]["event"] != "page_submitted":
            fail("Timing requires display and submission events")
        from datetime import datetime
        previous = -1
        previous_at = None
        for event in events:
            at = datetime.fromisoformat(event["at"])
            if event["question_id"] != qid or event["elapsed_ms"] < previous or at.tzinfo is None or (previous_at and at < previous_at):
                fail("Invalid timing event sequence")
            previous, previous_at = event["elapsed_ms"], at
        if events[0]["elapsed_ms"] != 0 or any(e["event"] != "option_selected" for e in events[1:-1]):
            fail("Invalid timing event lifecycle")
        first = next((e for e in events if e["event"] == "option_selected"), None)
        records.append({
            "session_id": session.preview_session_id, "survey_id": session.survey_id,
            "question_id": qid, "page_id": page["page_id"], "preview_only": True,
            "page_displayed_at": events[0]["at"],
            "first_interaction_at": first["at"] if first else None,
            "response_submitted_at": events[-1]["at"],
            "first_interaction_rt_ms": first["elapsed_ms"] if first else None,
            "final_response_rt_ms": events[-1]["elapsed_ms"],
            "selected_rt_metric": allowed[qid]["config"]["response_time"]["end_timing"],
            "events": events,
        })
    state.setdefault("timing_records", []).extend(records)


def next_page(db, identifier, answers=None, timings=None):
    session = load_session(db, identifier)
    if session.status != "active":
        fail("Preview has already ended", 409)
    state = deepcopy(session.runtime_json)
    page = state["history"][state["cursor"]]
    if page["kind"] == "block":
        answers = answers or {}
        validate_answers(page, answers)
        revisiting = state["cursor"] < len(state["history"]) - 1
        if revisiting and answers != page.get("submitted_answers", answers):
            checkpoint = deepcopy(page["checkpoint"])
            state["queue"] = checkpoint["queue"]
            state["answers"] = checkpoint["answers"]
            state["variables"] = checkpoint["variables"]
            state["agent_outputs"] = checkpoint.get("agent_outputs", {})
            state["visited"] = state["visited"][:checkpoint["visited_count"]]
            state["history"] = state["history"][:state["cursor"] + 1]
            state["ended"] = False
            state.pop("failed", None)
            state.pop("end_information", None)
        valid_pages = {item.get("page_id") for item in state["history"]}
        state["timing_records"] = [
            record for record in state.get("timing_records", [])
            if record["page_id"] in valid_pages and record["page_id"] != page["page_id"]
        ]
        record_timings(session, state, page, timings or [])
        if not revisiting or "checkpoint" in page:
            page["submitted_answers"] = deepcopy(answers)
        for q in page["block"]["questions"]:
            state["answers"].pop(q["question_id"], None)
        state["answers"].update(answers)
    elif page["kind"] == "python_error":
        state["history"].pop(state["cursor"])
        state["queue"].insert(0, page["node"])
        if state.get("visited") and state["visited"][-1]["element_id"] == page["element_id"]:
            state["visited"].pop()
    elif page["kind"] == "ai" and not page["done"]:
        fail("Complete the AI Conversation before continuing", 409)
    if state["cursor"] < len(state["history"]) - 1:
        state["cursor"] += 1
    elif page["kind"] != "end":
        advance(db, session, state)
    session.runtime_json = state
    db.commit()
    return view(db, session)


def back_page(db, identifier):
    session = load_session(db, identifier)
    state = deepcopy(session.runtime_json)
    if (
        session.status != "active"
        or not execution_data(db, session)["survey_config"]["responses"]["allow_back_button"]
        or state["cursor"] <= 0
    ):
        fail("Back is unavailable", 409)
    state["cursor"] -= 1
    session.runtime_json = state
    db.commit()
    return view(db, session)


def submit(db, identifier):
    session = load_session(db, identifier)
    if session.status == "completed":
        return view(db, session)
    state = session.runtime_json
    if session.status != "active" or state.get("failed") or state["history"][state["cursor"]]["kind"] != "end":
        fail("Reach the end of Preview before submitting", 409)
    if not session.snapshot_id:
        fail("Restart this legacy Preview before submitting", 409)
    conversations = [
        {
            "conversation_id": page["conversation_id"], "flow_node_id": page["element_id"],
            "agent_name": page["config"]["agent_name"], "messages": page["messages"],
        }
        for page in state["history"] if page["kind"] == "ai" and page["done"] and page["messages"]
    ]
    response = PreviewResponse(
        preview_response_id=uid(), preview_session_id=identifier,
        survey_id=session.survey_id, snapshot_id=session.snapshot_id,
        response_json={"answers": state["answers"], "content": conversations,
                       "timing": state.get("timing_records", []),
                       "allocations": state["allocations"]},
    )
    db.add(response)
    session.status = "completed"
    session.ended_at = now()
    db.commit()
    return view(db, session)


def end(db, identifier):
    session = load_session(db, identifier)
    if not session.snapshot_id:
        db.delete(session)
    else:
        db.execute(delete(AIConversation).where(AIConversation.preview_session_id == identifier))
        if session.status != "completed":
            session.status = "failed" if session.runtime_json.get("failed") else "terminated"
            session.ended_at = now()
        session.runtime_json = {}
    db.commit()


def resolve(template, state, snapshot):
    names = {
        q["question_name"]: q["question_id"]
        for b in snapshot["blocks"]
        if not b["is_deleted"]
        for q in b["questions"]
        if not q["is_deleted"]
    }

    def sub(match):
        name = match.group(1)
        key = names.get(name, name)
        if key in state["answers"]:
            value = state["answers"][key]
        elif key in state["variables"]:
            value = state["variables"][key]
        else:
            fail("Context input is unavailable: " + name)
        return (
            value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        )

    return re.sub(r"\{#(.*?)#\}", sub, template)


async def ai_request(config, messages):
    if not settings.openai_api_key:
        raise RuntimeError("Server OPENAI_API_KEY is not configured")
    model = config["model"] or settings.ai_model
    if not model:
        raise RuntimeError("AI model is not configured")
    body = {
        "model": model,
        "messages": messages,
        "temperature": config["temperature"],
        "max_completion_tokens": config["max_output_tokens"],
    }
    if config["top_p"] is not None:
        body["top_p"] = config["top_p"]
    if config["response_format"] == "json":
        body["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=config["timeout_seconds"]) as client:
        for attempt in range(config["max_retries"] + 1):
            try:
                r = await client.post(
                    settings.ai_api_url,
                    headers={"Authorization": "Bearer " + settings.openai_api_key},
                    json=body,
                )
                if r.status_code >= 400:
                    raise RuntimeError(
                        "AI provider returned HTTP " + str(r.status_code)
                    )
                data = r.json()
                return (
                    data["choices"][0]["message"]["content"],
                    data.get("usage", {}),
                    model,
                )
            except (httpx.HTTPError, RuntimeError, KeyError, ValueError):
                if attempt >= config["max_retries"]:
                    raise


async def chat(db, identifier, message):
    session = load_session(db, identifier)
    state = deepcopy(session.runtime_json)
    page = state["history"][state["cursor"]]
    if session.status != "active" or page["kind"] != "ai" or page["done"]:
        fail("No active AI Conversation", 409)
    if state["cursor"] != len(state["history"]) - 1:
        fail("Cannot execute AI from historical Preview pages", 409)
    a = page["config"]
    opening = not page["messages"]
    if not opening and not message.strip():
        fail("Participant message is empty")
    if opening and message:
        fail("Opening request must not contain a participant message")
    if not a["system_prompt"].strip() or not a["user_message_template"].strip():
        page["error"] = "AI configuration is incomplete. Complete System Prompt and User Message Template in Builder, then restart Preview."
        session.runtime_json = state
        db.commit()
        return view(db, session)
    context = resolve(a["context_template"], state, execution_data(db, session))
    if a["input_source_config"].get("include_previous_conversation"):
        explicit = set(re.findall(r"\{#(.*?)#\}", a["context_template"] + " " + a["user_message_template"]))
        prior = [
            {"agent": previous["config"]["agent_name"], "messages": previous["messages"]}
            for previous in state["history"][:state["cursor"]]
            if previous["kind"] == "ai" and previous["done"] and previous["messages"]
            and not explicit.intersection((previous["config"]["agent_name"], agent_output_name(previous["config"]["agent_name"]), previous["config"]["ai_config_id"]))
        ]
        if prior:
            context += "\nPrevious AI conversations: " + json.dumps(prior, ensure_ascii=False)
    source = a["input_source_config"].get("question_id")
    if source:
        if source not in state["answers"]:
            fail("AI Input Source has no answer")
        context += "\nInput Source: " + json.dumps(
            state["answers"][source], ensure_ascii=False
        )
    messages = [
        {"role": "system", "content": a["system_prompt"] + "\nContext:\n" + context}
    ]
    if a["include_history"]:
        history = page["messages"]
        window = a["history_window"]
        messages.extend(
            history if window is None else history[-window:] if window else []
        )
    task = resolve(a["user_message_template"], state, execution_data(db, session))
    messages.append(
        {
            "role": "user",
            "content": (
                "Begin the conversation with an opening message.\n"
                if opening
                else "Participant Message:\n" + message + "\nTask:\n"
            )
            + task,
        }
    )
    start = time.perf_counter()
    error = None
    usage = {}
    result = ""
    model = a["model"] or settings.ai_model
    try:
        result, usage, model = await ai_request(a, messages)
    except Exception as exc:
        error = (
            str(exc)
            if isinstance(exc, RuntimeError)
            else "AI request failed. Please retry."
        )
    conv = db.get(AIConversation, page["conversation_id"])
    turn = 0 if opening else page["turn_count"] + 1
    log = a["logging_config"]
    run = AIRun(
        run_id=uid(),
        conversation_id=conv.conversation_id,
        ai_config_id=a["ai_config_id"],
        config_version=a["config_version"],
        flow_element_id=page["element_id"],
        turn_number=turn,
        model=model,
        status="failed" if error else "completed",
        error_message=error if log["save_error"] else None,
        latency_ms=(
            int((time.perf_counter() - start) * 1000) if log["save_latency"] else None
        ),
        input_tokens=usage.get("prompt_tokens") if log["save_token_usage"] else None,
        output_tokens=(
            usage.get("completion_tokens") if log["save_token_usage"] else None
        ),
        total_tokens=usage.get("total_tokens") if log["save_token_usage"] else None,
        input_json={"messages": messages} if log["save_prompt"] else None,
        output_json={"content": result} if log["save_response"] and not error else None,
    )
    db.add(run)
    db.flush()
    page["error"] = error
    if error:
        conv.status = "failed"
        behavior = a["failure_behavior"]
        if behavior != "show_error":
            page["done"] = True
            conv.end_reason = "api_failure"
            conv.ended_at = now()
            if behavior == "end_survey":
                state["failed"] = True
                state["queue"] = []
            elif behavior == "use_default_value":
                state["variables"]["ai_" + a["agent_name"]] = ""
    else:
        conv.status = "running"
        if not opening:
            page["messages"].append({"role": "user", "content": message})
        page["messages"].append({"role": "assistant", "content": result})
        if not opening:
            page["turn_count"] += 1
        conv.turn_count = page["turn_count"]
        page["done"] = page["turn_count"] >= a["max_turns"]
        if page["done"]:
            conv.status = "completed"
            conv.end_reason = "max_turns_reached"
            conv.ended_at = now()
            state["variables"]["ai_" + a["agent_name"]] = result
            state.setdefault("agent_outputs", {})[a["ai_config_id"]] = page["messages"]
            state["variables"][a["agent_name"]] = page["messages"]
            state["variables"][agent_output_name(a["agent_name"])] = page["messages"]
            state["variables"][a["ai_config_id"]] = page["messages"]
        content = deepcopy(conv.ai_conversation_json)
        content["turns"].append(
            {"turn": turn, "role": "assistant", "content": result}
            if opening
            else {"turn": turn, "participant": message, "assistant": result}
        )
        content["end_reason"] = conv.end_reason
        # Respect prompt/response logging flags in durable logs; runtime keeps necessary conversation history until session expiry.
        if log["save_response"]:
            if not log["save_prompt"]:
                for saved_turn in content["turns"]:
                    saved_turn.pop("participant", None)
            conv.ai_conversation_json = content
        existing = (
            db.scalar(
                select(func.count())
                .select_from(AIMessage)
                .where(AIMessage.conversation_id == conv.conversation_id)
            )
            or 0
        )
        entries = []
        if not opening and log["save_prompt"]:
            entries.append(("user", message))
        if log["save_response"]:
            entries.append(("assistant", result))
        for i, (role, content) in enumerate(entries):
            db.add(
                AIMessage(
                    message_id=uid(),
                    conversation_id=conv.conversation_id,
                    run_id=run.run_id,
                    role=role,
                    content=content,
                    turn_number=turn,
                    sequence_number=existing + i + 1,
                )
            )
    session.runtime_json = state
    db.commit()
    return view(db, session)


def quit_conversation(db, identifier):
    session = load_session(db, identifier)
    state = deepcopy(session.runtime_json)
    page = state["history"][state["cursor"]]
    if session.status != "active" or page["kind"] != "ai" or page["done"] or not page["config"]["input_source_config"].get("allow_participant_quit", True):
        fail("This Conversation cannot be ended here", 409)
    config = page["config"]
    conv = db.get(AIConversation, page["conversation_id"])
    conv.status = "completed"
    conv.end_reason = "participant_quit"
    conv.ended_at = now()
    conv.ai_conversation_json = {**conv.ai_conversation_json, "end_reason": conv.end_reason}
    page["done"] = True
    page["error"] = None
    state.setdefault("agent_outputs", {})[config["ai_config_id"]] = page["messages"]
    state["variables"][config["agent_name"]] = page["messages"]
    state["variables"][agent_output_name(config["agent_name"])] = page["messages"]
    state["variables"][config["ai_config_id"]] = page["messages"]
    session.runtime_json = state
    db.commit()
    return view(db, session)
