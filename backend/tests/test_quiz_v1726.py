"""Blind5 post-hoc regression: v1.7.26 never represents these cases as blind."""
from __future__ import annotations
import json
import sys
import types
from pathlib import Path
import pytest

fake_ollama = types.ModuleType('ollama')
class DummyClient:
    def __init__(self, *args, **kwargs): pass
    def list(self): return {'models': []}
fake_ollama.Client = DummyClient
fake_ollama.chat = lambda *a, **k: {'message': {'content': '{}'}}
sys.modules.setdefault('ollama', fake_ollama)

from backend import main as m
ROOT = Path(__file__).parents[2]
FIX = json.loads((Path(__file__).parent/'fixtures/v1726_blind5_failed_cases.json').read_text('utf-8'))['cases']
BYID = {case['id']: case for case in FIX}


def replay(case, *, answer=None, source=None, backtranslation=''):
    answer = case['user_answer'] if answer is None else answer
    source = case['source_text'] if source is None else source
    before = m.TranslationEvaluation.model_validate(case['evaluation'])
    updated = m._audit_quiz_v1726_blind5_general_guards(
        before, user_answer=answer, backtranslation=backtranslation, source_text=source)
    updated = m._reconcile_material_issue_severity_from_units(updated)
    return m._reconcile_evaluation_consistency(updated, user_answer=answer)


def test_version_and_post_hoc_dataset():
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-phase99-numeric-integrity-v1", 'quiz-grader-v1.7.26', 'quiz-grader-v1.7.27'}
    assert m.read_root()['quiz_revision'] in {'phase99-numeric-integrity-v1','v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue','v1.7.27-source-anchored-science-and-japanese-fluency'}
    reg=json.loads((ROOT/'evaluation/quiz_v1726_blind5_regression.json').read_text('utf-8'))
    assert len(reg['cases']) == 8
    assert all('POST-HOC' in c['regression_origin'] for c in reg['cases'])
    assert len(json.loads((ROOT/'evaluation/quiz_eval_cases.json').read_text('utf-8'))['cases']) == 60
    assert len(json.loads((ROOT/'evaluation/quiz_v1724_regression.json').read_text('utf-8'))['cases']) == 13


@pytest.mark.parametrize('case', FIX, ids=lambda c: c['id'])
def test_real_exposed_blind5_cases_are_repaired_without_rewriting_fixture(case):
    after = replay(case)
    exp = case['expect']
    assert exp['min_score'] <= after.score <= exp['max_score']
    if exp.get('forbid_material_issue'):
        assert not any(i.category in {'omission', 'mistranslation'} for i in after.issues)
    if 'japanese_max' in exp:
        assert after.score_breakdown.japanese <= exp['japanese_max']
    if 'japanese_min' in exp:
        assert after.score_breakdown.japanese >= exp['japanese_min']
    if exp.get('must_have_missing'):
        assert any(u.status == 'missing' for u in after.semantic_units)
    if exp.get('must_have_material_issue'):
        assert any(i.category in {'omission', 'mistranslation'} for i in after.issues)
    if exp.get('must_have_noncorrect'):
        assert any(u.status != 'correct' for u in after.semantic_units)
    if 'awkward' in case['id']:
        assert after.score_breakdown.meaning == 70
        assert '日本語品質:' in after.feedback
    if case['id'].endswith('reversal_24'):
        assert after.score <= 59
        assert any(u.note.startswith(m._QUIZ_V1726_PAIRING_REVERSAL_PREFIX) for u in after.semantic_units)
    if case['id'].endswith('omission_13'):
        assert any('100 k' in u.note for u in after.semantic_units)
    # Idempotence: replaying a preserved evaluation cannot stack deductions.
    again = m._audit_quiz_v1726_blind5_general_guards(after, case['user_answer'], source_text=case['source_text'])
    again = m._reconcile_evaluation_consistency(again, user_answer=case['user_answer'])
    assert again.score == after.score
    assert again.score_breakdown.japanese == after.score_breakdown.japanese
    assert [(u.status,u.note) for u in again.semantic_units] == [(u.status,u.note) for u in after.semantic_units]


@pytest.mark.parametrize('answer,expected', [
    ('NbTi製SCUは永久磁石式より耐放射線性にも優れ、長年の加速器運用で実証された。', True),
    ('NbTi製SCUは永久磁石式より耐放射線性に優れ、長年の加速器運用で実証された。', False),
    ('NbTi製SCUは永久磁石式より耐放射線性が低い。', False),
    ('NbTi製SCUは永久磁石式と比べ別の利点があるが、放射線耐性はない。', False),
])
def test_additional_advantage_needs_additive_semantic_cue(answer, expected):
    case=BYID['blind5_casalbuoni2023_paraphrase_05']
    u=m.TranslationEvaluation.model_validate(case['evaluation']).semantic_units[0]
    assert m._quiz_v1726_japanese_factual_equivalent(u,case['source_text'],answer) is expected


@pytest.mark.parametrize('answer,expected', [
    ('線材にはポリビニルホルマール絶縁が施されている。',True),
    ('線材にはポリビニル塩化ビニル絶縁が施されている。',False),
    ('線材にポリビニルホルマール絶縁は施されていない。',False),
    ('線材にはポリビニルホルマール被覆がない。',False),
])
def test_formvar_narrow_polyvinyl_formal_equivalence(answer,expected):
    case=BYID['blind5_casalbuoni2023_awkward_11']
    u=m.TranslationEvaluation.model_validate(case['evaluation']).semantic_units[1]
    assert m._quiz_v1726_japanese_factual_equivalent(u,case['source_text'],answer) is expected


@pytest.mark.parametrize('answer,expected', [
    ('クエンチ検出は平衡電圧の原理に基づく。',True),
    ('クエンチ検出はバランス電圧方式を用いる。',True),
    ('クエンチ検出は平衡電圧の原理に基づかない。',False),
    ('クエンチ検出は差動電圧の原理に基づく。',False),
    ('クエンチ検出は平衡電圧の原理とは無関係である。',False),
])
def test_balanced_voltage_equivalence_keeps_relation(answer,expected):
    case=BYID['blind5_casalbuoni2023_awkward_12']
    u=m.TranslationEvaluation.model_validate(case['evaluation']).semantic_units[2]
    assert m._quiz_v1726_japanese_factual_equivalent(u,case['source_text'],answer) is expected


@pytest.mark.parametrize('answer,expected', [
    ('各SCUモジュールは遠隔操作できる4基のカムムーバに設置される。',True),
    ('各SCUモジュールは遠隔操作できない4基のカムムーバに設置される。',False),
    ('各SCUモジュールは遠隔操作が不可能な4基のカムムーバに設置される。',False),
    ('各SCUモジュールは遠隔操作可能な2基のカムムーバに設置される。',False),
])
def test_remote_control_anchor_negative_and_four_movers(answer,expected):
    case=BYID['blind5_casalbuoni2023_awkward_10']
    u=m.TranslationEvaluation.model_validate(case['evaluation']).semantic_units[2]
    assert m._quiz_v1726_japanese_factual_equivalent(u,case['source_text'],answer) is expected


@pytest.mark.parametrize('answer,expected', [
    ('磁石を冷却すると残留磁化が増加し、磁気軸上のピーク磁場も増大する。',True),
    ('磁石を約100 Kまで冷却すると残留磁化が増加する。',False),
    ('磁石を約-173 ℃まで冷却すると残留磁化が増加する。',False),
    ('磁石を約100ケルビンまで冷却すると残留磁化が増加する。',False),
])
def test_single_explicit_quantity_omission_vs_conversion(answer,expected):
    case=BYID['blind5_casalbuoni2023_omission_13']
    before=m.TranslationEvaluation.model_validate(case['evaluation'])
    changed=m._audit_quiz_v1726_blind5_general_guards(before,answer,source_text=case['source_text'])
    assert any(u.status=='missing' for u in changed.semantic_units) is expected


def test_implicit_liquid_nitrogen_equivalence_for_77k_is_retained():
    unit=m.SemanticUnit(id='u',source='sample cooled to 77 K',translation='77 K',importance='core',status='correct')
    assert not m._quiz_v1726_lost_single_quantity(unit,'sample cooled to 77 K','試料を液体窒素温度に冷却した。','')


@pytest.mark.parametrize('answer,expected', [
    ('SUNDAE1は液体ヘリウム2 K、超流動ヘリウム4 Kで試験する。',True),
    ('SUNDAE1は2 Kの液体ヘリウムと4 Kの超流動ヘリウムで試験する。',True),
    ('SUNDAE1は液体ヘリウム4 K、超流動ヘリウム2 Kで試験する。',False),
    ('SUNDAE1は液体ヘリウムと超流動ヘリウムを、それぞれ4 Kと2 Kで試験する。',False),
    ('SUNDAE1は液体ヘリウム4 Kと超流動ヘリウム4 Kで試験する。',False),
])
def test_respectively_pairing_requires_both_wrong_pairs(answer,expected):
    case=BYID['blind5_casalbuoni2023_reversal_24']
    assert m._quiz_v1726_respectively_reversed(case['source_text'],answer) is expected


@pytest.mark.parametrize('answer,expected', [
    ('選ぶことが可能となることができる。',True),
    ('遠隔操作することが可能であることができる。',True),
    ('平衡電圧の原理に基づいて行われることが実施される。',True),
    ('電子エネルギーが固定された後に決定できる。',False),
    ('各SCUモジュールは遠隔操作できる。',False),
    ('クエンチ検出は平衡電圧原理に基づいて行われる。',False),
])
def test_new_fluency_patterns_do_not_penalize_normal_japanese(answer,expected):
    assert bool(m._quiz_japanese_surface_strong_fluency_hints(answer)) is expected


def test_missing_soft_xray_line_gets_missing_not_wrong_only():
    case=BYID['blind5_casalbuoni2023_omission_14']
    after=m._audit_quiz_v1726_blind5_general_guards(m.TranslationEvaluation.model_validate(case['evaluation']),case['user_answer'],source_text=case['source_text'])
    assert after.semantic_units[1].status=='missing'
    assert after.semantic_units[2].status=='wrong'


def test_blind5_fixtures_remain_unmodified_and_exposed_only_as_regression():
    regression=json.loads((ROOT/'evaluation/quiz_v1726_blind5_regression.json').read_text('utf-8'))
    fixture_by_id={case['id']:case for case in FIX}
    assert len(regression['cases']) == len(fixture_by_id) == 8
    for case in regression['cases']:
        original=fixture_by_id[case['id']]
        assert case['source_text'] == original['source_text']
        assert case['user_answer'] == original['user_answer']
        assert case['expect'] == original['expect']
        assert 'POST-HOC' in case['regression_origin']
