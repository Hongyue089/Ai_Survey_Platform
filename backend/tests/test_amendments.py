from copy import deepcopy
from datetime import datetime, timezone, timedelta
import pytest
from test_workflow import client, question, element, save, payload
from app.preview import block_pages


def mc(qid="q1", rt=False):
    q = question(qid)
    q.update(question_type="multiple_choice", config={"choices": [
        {"choice_id": qid + "c1", "value": 1, "label": "大学毕业"},
        {"choice_id": qid + "c2", "value": 2, "label": "高校毕业"}],
        "response_time": {"enabled": rt, "end_timing": "first_interaction"}})
    return q


def start(c, s):
    r = c.post(f"/api/surveys/{s['survey_id']}/preview-sessions")
    assert r.status_code == 201, r.text
    return r.json()


def test_option_reference_edit_guard_and_label_change(client):
    s = client.post('/api/projects').json()
    s['blocks'][0]['questions'] = [mc()]
    s['flow']['elements'] = [element('show', 'block', block_id=s['blocks'][0]['block_id']), element('branch', 'branch', config={'condition_groups': [{
        'group_id': 'g', 'conditions': [{'source_id': 'q1', 'value': 2}], 'children': []}]})]
    s = save(client, s)
    changed = deepcopy(s)
    changed['blocks'][0]['questions'][0]['config']['choices'].pop()
    r = client.put(f"/api/surveys/{s['survey_id']}/working", json=payload(changed))
    assert r.status_code == 409 and 'branch' in r.text
    assert len(client.get(f"/api/surveys/{s['survey_id']}/working").json()['blocks'][0]['questions'][0]['config']['choices']) == 2
    s['blocks'][0]['questions'][0]['config']['choices'][1]['label'] = '高校卒業'
    s = save(client, s)
    assert s['flow']['elements'][1]['config']['condition_groups'][0]['conditions'][0]['value'] == 2
    changed = deepcopy(s)
    changed['blocks'][0]['questions'][0]['config']['choices'][1]['value'] = 99
    assert client.put(f"/api/surveys/{s['survey_id']}/working", json=payload(changed)).status_code == 409


def test_end_information_and_path_termination(client):
    s = client.post('/api/projects').json()
    s['flow']['elements'] = [element('end', 'end_survey', config={'end_information': '以上です。\nご協力ありがとうございます。'}), element('never', 'block', block_id=s['blocks'][0]['block_id'])]
    s = save(client, s)
    v = start(client, s)
    assert v['page'] == {'kind': 'end', 'end_information': '以上です。\nご協力ありがとうございます。'}
    s['flow']['elements'][0]['config']['end_information'] = ''
    s = save(client, s)
    assert start(client, s)['page']['end_information'] == ''


def test_permanent_delete_disabled_and_restore(client):
    s = client.post('/api/projects').json()
    s['blocks'][0]['questions'] = [question()]
    s = save(client, s)
    s['blocks'][0]['questions'][0]['is_deleted'] = True
    s = save(client, s)
    r = client.delete(f"/api/surveys/{s['survey_id']}/trash/question/q1?expected_version={s['working_version']}")
    assert r.status_code == 409
    s['blocks'][0]['questions'][0]['is_deleted'] = False
    assert save(client, s)['blocks'][0]['questions'][0]['is_deleted'] is False


def test_rt_split_events_back_and_isolation(client):
    s = client.post('/api/projects').json()
    qs = [question('before'), mc('rt', True), question('after'), question('after2')]
    for i, q in enumerate(qs): q['sort_order'] = i
    s['blocks'][0]['questions'] = qs
    s['flow']['elements'] = [element('show', 'block', block_id=s['blocks'][0]['block_id'])]
    s = save(client, s)
    v = start(client, s); pid = v['preview_session_id']
    assert [q['question_id'] for q in v['page']['block']['questions']] == ['before']
    v = client.post(f'/api/preview-sessions/{pid}/next', json={'answers': {'before': 'ok'}}).json()
    assert [q['question_id'] for q in v['page']['block']['questions']] == ['rt']
    base = datetime.now(timezone.utc)
    events = [{'question_id': 'rt', 'event': event, 'at': (base + timedelta(milliseconds=ms)).isoformat(), 'elapsed_ms': ms} for event, ms in [('question_displayed', 0), ('option_selected', 240), ('option_selected', 390), ('page_submitted', 700)]]
    r = client.post(f'/api/preview-sessions/{pid}/next', json={'answers': {'rt': 2}, 'timings': [{'question_id': 'rt', 'events': events}]})
    assert r.status_code == 200, r.text
    v = r.json()
    assert [q['question_id'] for q in v['page']['block']['questions']] == ['after', 'after2']
    record = v['timing_debug'][0]
    assert record['first_interaction_rt_ms'] == 240 and record['final_response_rt_ms'] == 700
    assert record['preview_only'] and record['selected_rt_metric'] == 'first_interaction'
    restored = client.post(f'/api/preview-sessions/{pid}/back').json()
    assert restored['page']['block']['questions'][0]['question_id'] == 'rt'
    assert client.get('/api/projects').json()['items'][0]['response_count'] == 0


def test_group_random_selection_stable_across_reload_and_back(client):
    s = client.post('/api/projects').json()
    s['blocks'][0]['questions'] = [question('q' + str(i)) for i in range(4)]
    s['blocks'][0]['question_groups'] = [{'group_id': 'g', 'name': 'A', 'question_ids': ['q0', 'q1', 'q2', 'q3'], 'question_order': 'random', 'display_mode': 'random_n', 'display_count': 2}]
    s['flow']['elements'] = [element('show', 'block', block_id=s['blocks'][0]['block_id'])]
    s = save(client, s); v = start(client, s); pid = v['preview_session_id']
    ids = [q['question_id'] for q in v['page']['block']['questions']]
    assert len(set(ids)) == 2
    assert client.get(f'/api/preview-sessions/{pid}').json()['page'] == v['page']
    client.post(f'/api/preview-sessions/{pid}/next', json={'answers': {qid: 'yes' for qid in ids}})
    assert client.post(f'/api/preview-sessions/{pid}/back').json()['page'] == v['page']


def test_consecutive_rt_questions_each_isolated(client):
    s = client.post('/api/projects').json()
    s['blocks'][0]['questions'] = [mc('a', True), mc('b', True), question('c')]
    for i, q in enumerate(s['blocks'][0]['questions']): q['sort_order'] = i
    s = save(client, s)
    pages = block_pages(s['blocks'][0], {'allocations': {}})
    assert [[q['question_id'] for q in b['questions']] for b in pages] == [['a'], ['b'], ['c']]


def test_invalid_group_count_rejected(client):
    s = client.post('/api/projects').json()
    s['blocks'][0]['questions'] = [question()]
    s['blocks'][0]['question_groups'] = [{'group_id': 'g', 'question_ids': ['q1'], 'display_mode': 'random_n', 'display_count': 2}]
    assert client.put(f"/api/surveys/{s['survey_id']}/working", json=payload(s)).status_code == 422


def test_incomplete_ai_is_saved_as_draft_but_blocks_preview(client):
    s = client.post('/api/projects').json()
    s['ai_configs'] = [{'ai_config_id': 'a'}]
    s['flow']['elements'] = [element('show', 'block', block_id=s['blocks'][0]['block_id']), element('call', 'call_ai', ai_config_id='a')]
    s = save(client, s)
    response = client.post(f"/api/surveys/{s['survey_id']}/preview-sessions")
    assert response.status_code == 422 and "AI configuration is incomplete" in response.text


def test_legacy_mc_config_gets_runtime_defaults(client):
    from app.db import get_db
    from app.main import app
    from app.models import Survey, SurveyRevision
    s = client.post('/api/projects').json()
    s['blocks'][0]['questions'] = [mc()]
    s['flow']['elements'] = [element('show', 'block', block_id=s['blocks'][0]['block_id'])]
    s = save(client, s)
    dependency = app.dependency_overrides[get_db]
    gen = dependency()
    db = next(gen)
    survey = db.get(Survey, s["survey_id"])
    revision = db.get(SurveyRevision, survey.working_revision_id)
    legacy = deepcopy(revision.survey_json)
    legacy["blocks"][0]["questions"][0]["config"].pop("response_time")
    revision.survey_json = legacy
    db.commit()
    gen.close()
    v = start(client, s)
    assert v['page']['block']['questions'][0]['config']['response_time']['enabled'] is False


def test_missing_or_invalid_rt_events_rejected(client):
    s = client.post('/api/projects').json()
    s['blocks'][0]['questions'] = [mc('rt', True)]
    s['flow']['elements'] = [element('show', 'block', block_id=s['blocks'][0]['block_id'])]
    s = save(client, s)
    v = start(client, s); pid = v['preview_session_id']
    assert client.post(f'/api/preview-sessions/{pid}/next', json={'answers': {'rt': 1}}).status_code == 422
    base = datetime.now(timezone.utc)
    events = [{'question_id': 'rt', 'event': event, 'at': (base + timedelta(milliseconds=ms)).isoformat(), 'elapsed_ms': elapsed} for event, ms, elapsed in [('question_displayed', 0, 0), ('option_selected', 20, 20), ('page_submitted', 40, 10)]]
    assert client.post(f'/api/preview-sessions/{pid}/next', json={'answers': {'rt': 1}, 'timings': [{'question_id': 'rt', 'events': events}]}).status_code == 422


def test_group_duplicate_members_rejected(client):
    s = client.post('/api/projects').json()
    s['blocks'][0]['questions'] = [question()]
    s['blocks'][0]['question_groups'] = [{'group_id': 'g1', 'question_ids': ['q1']}, {'group_id': 'g2', 'question_ids': ['q1']}]
    assert client.put(f"/api/surveys/{s['survey_id']}/working", json=payload(s)).status_code == 422
