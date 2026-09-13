from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json
import sqlite3
import zipfile

import pytest

from latka_jazn.tools.memory_rebuild_app.memory_studio import MemoryStudio, StudioConfig
from latka_jazn.tools.memory_rebuild_app.studio_audit import scan_sources, classify
from latka_jazn.tools.memory_rebuild_app.studio_links import link_entry, parse_source_time


def conversation(cid='c', text='Pamiętam spokojny wieczór', role='user'):
    return {'id': cid, 'title': 'Łatka', 'create_time': 1750000000.0,
            'current_node': 'n', 'mapping': {'n': {'id': 'n', 'parent': None, 'children': [],
            'message': {'id': cid + '-m', 'author': {'role': role}, 'create_time': 1750000000.0,
                        'content': {'content_type': 'text', 'parts': [text]}}}}}


def setup(tmp_path):
    source = tmp_path / 'sources'
    source.mkdir()
    (source / 'conversations.json').write_text(json.dumps([conversation()], ensure_ascii=False), encoding='utf-8')
    w = tmp_path / 'work'
    cfg = StudioConfig(str(source), str(w/'tests'), str(w/'db.sqlite3'), str(w/'backups'),
                       str(w/'exports'), str(w/'reports'), str(w/'catalog.sqlite3'), base_commit='b'*40)
    return source, cfg, MemoryStudio(cfg)


def test_inventory_duplicates_titles_and_cache(tmp_path):
    source, cfg, app = setup(tmp_path)
    (source / 'shared_conversations.json').write_text('[{"id":"shared","title":"Łatka"}]')
    (source / 'conversations-001.json').write_text(json.dumps([conversation('d')]), encoding='utf-8')
    (source / 'copy-conversations.json').write_bytes((source/'conversations.json').read_bytes())
    (source / 'chat.html').write_text('<script>var jsonData = ' + json.dumps([conversation()]) + ';</script>')
    first = app.scan()
    assert first['ok'], first
    assert first['conversation_count'] == 2
    assert first['message_versions_by_role'] == {'user': 2}
    assert first['same_title_distinct_chats'] == [{'title': 'Łatka', 'chats': 2}]
    assert len(first['selected_sources']) == 2
    second = app.scan()
    assert second['fingerprint'] == first['fingerprint']
    assert second['message_versions_by_role'] == first['message_versions_by_role']
    assert classify(Path('prefix-shared_conversations.json')) == 'relational_metadata'


def test_conflicts_preserved_and_missing_sources_removed(tmp_path):
    source, cfg, app = setup(tmp_path)
    other = source/'conversations-001.json'
    other.write_text(json.dumps([conversation(text='Inny tekst')]))
    assert app.scan()['conflicting_message_ids'] == 1
    other.unlink()
    assert app.scan()['conflicting_message_ids'] == 0


def test_time_links_require_unambiguous_time_and_identity(tmp_path):
    source, cfg, app = setup(tmp_path)
    app.scan()
    con = sqlite3.connect(cfg.catalog)
    con.row_factory = sqlite3.Row
    try:
        linked = link_entry(con, {'message_id': 'c-m', 'timestamp': 1750000000})
        assert linked['status'] == 'time_correlated'
        uncertain = link_entry(con, {'message_id': 'c-m', 'date': '01/07/2025'})
        assert uncertain['status'] == 'review_required'
        assert uncertain['timestamp_status'] == 'ambiguous_date_order'
        mismatch = link_entry(con, {'message_id': 'c-m', 'timestamp': 1760000000})
        assert mismatch['status'] == 'review_required'
    finally:
        con.close()
    assert parse_source_time('2025-07-01T10:00:00')[1] == 'timezone_missing'
    assert parse_source_time('2025-07-01T10:00:00+02:00')[1] == 'explicit_timezone'


def test_create_update_backup_and_failed_source_preserves_target(tmp_path):
    source, cfg, app = setup(tmp_path)
    app.scan()
    result = app.build()
    assert result['ok'], result
    target = Path(cfg.database)
    with sqlite3.connect(target) as con:
        assert con.execute('select count(*) from memory_l0_records').fetchone()[0] == 1
    con.close()
    updated = app.build(update=True)
    assert Path(updated['backup']).is_file()
    with sqlite3.connect(target) as con:
        assert con.execute('select count(*) from memory_l0_records').fetchone()[0] == 1
        assert con.execute('pragma integrity_check').fetchone()[0] == 'ok'
        assert con.execute('pragma foreign_key_check').fetchall() == []
    con.close()
    before = target.read_bytes()
    (source/'conversations.json').write_text('[]')
    with pytest.raises(ValueError, match='zmieniło'):
        app.build(update=True)
    assert target.read_bytes() == before


def test_stage_resume_does_not_repeat_previous_test(tmp_path):
    source, cfg, app = setup(tmp_path)
    app.scan()
    zero = app.stage('test00', 'run')
    assert zero['ok'], zero
    one = app.stage('test01', 'run')
    assert one['ok'], one
    cached = app.stage('test01', 'run')
    assert cached['reused_completed_stage'] is True
    two = app.stage('test02', 'run')
    assert two['ok'], two
    three = app.stage('test03', 'run')
    assert three['ok'], three
    with pytest.raises(ValueError, match='benchmark'):
        app.stage('test04', 'run')


def test_paths_and_lossy_html_fail_closed(tmp_path):
    source, cfg, app = setup(tmp_path)
    bad = StudioConfig(**{**asdict(cfg), 'database': str(source/'bad.sqlite3')})
    with pytest.raises(ValueError):
        bad.validate()
    (source/'chat.html').write_text('<p>Only rendered content</p>')
    report = app.scan()
    assert not report['ok']
    with pytest.raises(ValueError):
        app.build()
    with pytest.raises(ValueError):
        app.stage('test00', '../escape')


def test_embedded_json_repair_preserves_original_and_music_entries(tmp_path):
    from latka_jazn.tools.memory_rebuild_app.adapters.music_analysis import _analysis_rows
    source, cfg, app = setup(tmp_path)
    broken = b'{"entries":[{"numer":1,"analiza":"one"} {"numer":2,"analiza":"two"}]}'
    archive = source/'memory.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('resources/analizy_utworow.json', broken)
    assert not app.scan()['ok']
    cfg = StudioConfig(**{**asdict(cfg), 'repair_missing_commas': True})
    app = MemoryStudio(cfg)
    assert app.scan()['ok']
    materialized = app.sources()
    music = next(p for p in materialized if p.name == 'analizy_utworow.json')
    assert len(list(_analysis_rows(music))) == 2
    assert (music.parent/'original.bin').read_bytes() == broken
    with zipfile.ZipFile(archive) as z:
        assert z.read('resources/analizy_utworow.json') == broken


def test_repair_does_not_change_strings_or_guess_other_syntax():
    from latka_jazn.tools.memory_rebuild_app.studio_repair import repair_missing_object_comma
    with pytest.raises(ValueError):
        repair_missing_object_comma(b'{"entries":[{"text":"unfinished}]}')


def test_complete_studio_pipeline_exports_verified_database(tmp_path):
    source, cfg, app = setup(tmp_path)
    benchmark = tmp_path/'benchmark.json'
    categories = ['direct', 'paraphrase', 'referential_followup', 'temporal',
                  'update', 'conflict', 'provenance', 'sensitive_boundary']
    cases = []
    for category in categories:
        case = {'id': category, 'category': category, 'query': 'spokojny',
                'expected_any': ['spokojny'], 'limit': 20}
        if category == 'referential_followup':
            case['context_turns'] = ['spokojny wieczór']
        if category == 'temporal':
            case['temporal_start'] = '2025-01-01T00:00:00Z'
            case['temporal_end'] = '2026-01-01T00:00:00Z'
        if category == 'provenance':
            case['expected_source_kinds'] = ['chatgpt_conversation']
        if category == 'sensitive_boundary':
            case['forbidden_any'] = ['secret-that-must-never-appear']
        cases.append(case)
    cases.append({'id': 'negative', 'category': 'negative', 'query': 'xyznothere987',
                  'expected_abstain': True, 'minimum_hits': 0})
    benchmark.write_text(json.dumps({'schema_version': 'jazn_memory_recall_benchmark/v2',
        'suite_id': 'studio-integration', 'cases': cases,
        'minimums': {'recall_at_20': 1.0, 'mrr': 1.0, 'ndcg': 1.0,
                     'abstention_accuracy': 1.0, 'provenance_accuracy': 1.0,
                     'temporal_accuracy': 1.0, 'max_sensitive_leakage_rate': 0.0,
                     'max_false_memory_rate': 0.0}}))
    app = MemoryStudio(StudioConfig(**{**asdict(cfg), 'benchmark': str(benchmark)}))
    app.scan()
    for name in ('test00', 'test01', 'test02', 'test03', 'test04', 'final'):
        result = app.stage(name, 'complete')
        assert result['ok'], (name, result)
    exported = Path(cfg.export_root)/'complete'/'memory_jazn.sqlite3'
    assert exported.is_file()
    con = sqlite3.connect(exported)
    try:
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not con.execute('PRAGMA foreign_key_check').fetchall()
        assert con.execute('SELECT count(*) FROM memory_l0_records').fetchone()[0] == 1
    finally:
        con.close()


def test_raw_html_matching_json_does_not_decode_author_entities_twice(tmp_path):
    source, cfg, app = setup(tmp_path)
    data = json.dumps([conversation(text='Code example: &amp; and &lt;')])
    (source/'conversations.json').write_text(data)
    (source/'chat.html').write_text('<script>var jsonData = '+data+';</script>')
    report = app.scan()
    assert report['ok']
    assert report['conflicting_message_ids'] == 0
    assert report['selected_sources'] == [str(source/'conversations.json')]
