"""Sixth paper blind -> explicitly POST-HOC v1.7.27 regression, not another blind."""
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
fake_ollama.chat = lambda *args, **kwargs: {'message': {'content': '{}'}}
sys.modules.setdefault('ollama', fake_ollama)

from backend import main as m
ROOT = Path(__file__).parents[2]
FIX = json.loads((Path(__file__).parent / 'fixtures/v1727_blind6_failed_cases.json').read_text('utf8'))['cases']
BYID = {x['id']: x for x in FIX}


def replay(case, answer=None):
    answer = case['user_answer'] if answer is None else answer
    before = m.TranslationEvaluation.model_validate(case['evaluation'])
    updated = m._audit_quiz_v1727_blind6_general_guards(before, answer, case['source_text'])
    updated = m._reconcile_material_issue_severity_from_units(updated)
    return m._reconcile_evaluation_consistency(updated, user_answer=answer)


def test_versions_and_archived_immutable_data():
    assert m.QUIZ_GRADER_VERSION in {'quiz-grader-v1.7.27', "quiz-grader-phase99-numeric-integrity-v1"}
    assert m.read_root()['quiz_revision'] in {'v1.7.27-source-anchored-science-and-japanese-fluency', 'phase99-numeric-integrity-v1'}
    reg = json.loads((ROOT/'evaluation/quiz_v1727_blind6_regression.json').read_text('utf8'))
    assert len(reg['cases']) == len(FIX) == 7
    assert all('POST-HOC' in x.get('regression_origin', '') for x in reg['cases'])
    for case in reg['cases']:
        original = BYID[case['id']]
        assert case['source_text'] == original['source_text']
        assert case['user_answer'] == original['user_answer']
        assert case['expect'] == original['expect']


@pytest.mark.parametrize('case', FIX, ids=lambda x: x['id'])
def test_blind6_exposed_seven_repaired_and_idempotent(case):
    before = m.TranslationEvaluation.model_validate(case['evaluation'])
    after = replay(case)
    exp = case['expect']
    assert exp.get('min_score', 0) <= after.score <= exp.get('max_score', 100)
    assert not (exp.get('forbid_material_issue') and any(x.category in {'omission', 'mistranslation'} for x in after.issues))
    if 'japanese_max' in exp: assert after.score_breakdown.japanese <= exp['japanese_max']
    if 'japanese_min' in exp: assert after.score_breakdown.japanese >= exp['japanese_min']
    if exp.get('must_have_missing'): assert any(u.status=='missing' for u in after.semantic_units)
    if exp.get('must_have_noncorrect'): assert any(u.status!='correct' for u in after.semantic_units)
    if exp.get('must_have_material_issue'): assert any(i.category in {'omission','mistranslation'} for i in after.issues)
    if case['variant'] == 'awkward':
        assert before.score_breakdown.meaning == after.score_breakdown.meaning
        assert before.score_breakdown.terminology == after.score_breakdown.terminology
        assert after.score_breakdown.japanese == 10
        assert '日本語品質:' in after.feedback
    if case['id'].endswith('omission_14'):
        assert any(u.note.startswith(m._QUIZ_V1727_RESISTIVITY_OMISSION_PREFIX) for u in after.semantic_units)
    if case['id'].endswith(('natural_03', 'paraphrase_07')):
        assert all(u.status=='correct' for u in after.semantic_units)
        assert '意味関係が原文と異な' not in after.feedback
        assert '抜けています' not in after.feedback
    # A second post-processing pass cannot stack deductions or change statuses.
    second = m._audit_quiz_v1727_blind6_general_guards(after,case['user_answer'],case['source_text'])
    second = m._reconcile_evaluation_consistency(second,user_answer=case['user_answer'])
    assert second.score == after.score
    assert second.score_breakdown.japanese == after.score_breakdown.japanese
    assert [(u.status,u.note) for u in second.semantic_units] == [(u.status,u.note) for u in after.semantic_units]


@pytest.mark.parametrize('answer,expected', [
    ('すべてのモデルを、一次形状関数を用いた2次元軸対称形状で実装した。', True),
    ('モデルを一次形状関数を用いた2次元軸対称幾何学で実装した。', True),
    ('モデルを一次形状関数を用いた3次元軸対称形状で実装した。', False),
    ('モデルを一次形状関数を用いた1次元軸対称形状で実装した。', False),
    ('モデルを一次形状関数を用いた非軸対称形状で実装した。', False),
    ('モデルを二次形状関数を用いた2次元軸対称形状で実装した。', False),
    ('モデルを一次形状関数を用いた2次元軸対称形状ではない場所で実装した。', False),
])
def test_axisymmetric_geometry_witness_never_relaxes_wrong_dimensions(answer, expected):
    case=BYID['blind6_arsenault2023_natural_03']
    unit=m.TranslationEvaluation.model_validate(case['evaluation']).semantic_units[3]
    assert m._quiz_v1727_scientific_equivalence(unit,case['source_text'],answer) is expected


@pytest.mark.parametrize('answer,expected', [
    ('完全H定式化と比較すると、H–φ/D定式化では自由度を約半分、計算時間を約4分の1にしながら、最も精度の高い解を得られる。', True),
    ('完全H定式化と比較すると、H–φ/D定式化では自由度を半分、計算時間を4分の1にしながら、最も精度の高い解を得られる。', True),
    ('完全H定式化と比較すると、H–φ/D定式化では自由度を2倍、計算時間を約4分の1にしながら、最も精度の高い解を得られる。', False),
    ('完全H定式化と比較すると、H–φ/D定式化では自由度を約半分、計算時間を約4倍にしながら、最も精度の高い解を得られる。', False),
    ('完全H定式化と比較すると、H–φ/D定式化では自由度を約半分、計算時間を約4分の1にしながら、精度の低い解を得る。', False),
    ('完全H定式化と比較すると、H–φ/QS定式化では自由度を約半分、計算時間を約4分の1にしながら、最も精度の高い解を得られる。', False),
    ('完全H定式化と比較すると、H–φ/D定式化では自由度を約半分、計算時間を約4分の1にしても、解を得られない。', False),
])
def test_half_dofs_quarter_time_needs_complete_correct_context(answer, expected):
    case=BYID['blind6_arsenault2023_paraphrase_07']
    unit=m.TranslationEvaluation.model_validate(case['evaluation']).semantic_units[2]
    assert m._quiz_v1727_scientific_equivalence(unit,case['source_text'],answer) is expected


@pytest.mark.parametrize('answer,missing', [
    ('空気領域に抵抗率を設定するのが一般的である。', True),
    ('空気領域に1 Ω·mの抵抗率を設定するのが一般的である。', False),
    ('空気領域に1 Ω mの抵抗率を設定するのが一般的である。', False),
    ('空気領域に1 Ω・mの抵抗率を設定するのが一般的である。', False),
    ('空気領域に1オームメートルの抵抗率を設定するのが一般的である。', False),
    ('空気領域に2 Ω·mの抵抗率を設定するのが一般的である。', False),
    ('空気領域の電気伝導率が低い。', False),
])
def test_ohm_m_absence_based_on_actual_japanese_not_backtranslation(answer, missing):
    case=BYID['blind6_arsenault2023_omission_14']
    unit=m.TranslationEvaluation.model_validate(case['evaluation']).semantic_units[1]
    assert m._quiz_v1727_missing_explicit_resistivity(unit,case['source_text'],answer) is missing


def test_new_ohm_metres_are_quantities_but_bare_number_is_not():
    assert m._quiz_quantities('1 Ω·m') == [('1','ohm_m')]
    assert m._quiz_quantities('1 Ωm') == [('1','ohm_m')]
    assert m._quiz_quantities('1 Ω・m') == [('1','ohm_m')]
    assert m._quiz_quantities('2 ohm m') == [('2','ohm_m')]
    assert m._quiz_quantities('resistivity 1') == []


@pytest.mark.parametrize('answer,awkward', [
    ('必要となることが必要であった。', True),
    ('見いだすことが行われた。', True),
    ('見いだされることになったということである。', True),
    ('示されているということが示されることになる。', True),
    ('高次の形状関数が必要であった。',False),
    ('すべてのシミュレーションで定性的な一致が確認された。',False),
    ('両定式化が同じ値へ収束することがわかった。',False),
    ('図5(c)の相対誤差が小さいことから示されている。',False),
])
def test_strong_fluency_only_on_structural_redundancy(answer,awkward):
    assert bool(m._quiz_japanese_surface_strong_fluency_hints(answer)) is awkward
