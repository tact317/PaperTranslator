"""v1.7.25 post-hoc blind4 regression (NOT new independent blind)."""
from __future__ import annotations
import sys,types,json
from pathlib import Path
import pytest

fake_ollama=types.ModuleType('ollama')
class DummyClient:
 def __init__(self,*a,**k):pass
 def list(self):return {'models':[]}
fake_ollama.Client=DummyClient
fake_ollama.chat=lambda *a,**k:{'message':{'content':'{}'}}
sys.modules.setdefault('ollama',fake_ollama)
from backend import main as m

ROOT=Path(__file__).parents[2]
FIX=json.loads((Path(__file__).parent/'fixtures/v1725_blind4_failed_cases.json').read_text('utf-8'))['cases']
BYID={x['id']:x for x in FIX}
ID03=BYID['blind4_otten2016_natural_03']
ID04=BYID['blind4_otten2016_natural_04']
ID11=BYID['blind4_otten2016_awkward_11']
ID13=BYID['blind4_otten2016_omission_13']
ID24=BYID['blind4_otten2016_reversal_24']


def replay(case, answer=None, source=None, backtranslation=''):
    evaluation=m.TranslationEvaluation.model_validate(case['evaluation'])
    return m._reconcile_evaluation_consistency(
        m._audit_quiz_v1725_blind4_general_guards(
            evaluation,
            user_answer=answer if answer is not None else case['user_answer'],
            backtranslation=backtranslation,
            source_text=source if source is not None else case['source_text'],
        ),
        user_answer=answer if answer is not None else case['user_answer'],
    )


def test_version_and_unchanged_corpi():
    assert m.QUIZ_GRADER_VERSION in {'quiz-grader-v1.7.26', 'quiz-grader-v1.7.27'}
    assert m.read_root()['quiz_revision'] in {'v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue','v1.7.27-source-anchored-science-and-japanese-fluency'}
    src=json.loads((ROOT/'evaluation/quiz_v1725_blind4_regression.json').read_text('utf-8'))
    assert len(src['cases'])==7
    assert all('POST-HOC' in x['regression_origin'] for x in src['cases'])
    assert len(json.loads((ROOT/'evaluation/quiz_eval_cases.json').read_text('utf-8'))['cases'])==60
    assert len(json.loads((ROOT/'evaluation/quiz_v1724_regression.json').read_text('utf-8'))['cases'])==13


@pytest.mark.parametrize('case',FIX,ids=lambda c:c['id'])
def test_actual_seven_failing_cases_post_hoc_replay(case):
    before=m.TranslationEvaluation.model_validate(case['evaluation'])
    final=replay(case)
    exp=case['expect']
    assert exp['min_score'] <= final.score <= exp['max_score']
    if exp.get('forbid_material_issue'):
        assert not any(i.category in {'omission','mistranslation'} for i in final.issues)
    if 'japanese_max' in exp:
        assert final.score_breakdown.japanese <= exp['japanese_max']
    if 'japanese_min' in exp:
        assert final.score_breakdown.japanese >= exp['japanese_min']
    if exp.get('must_have_material_issue'):
        assert any(i.category in {'omission','mistranslation'} for i in final.issues)
    if exp.get('must_have_missing'):
        assert any(u.status=='missing' for u in final.semantic_units)
    if exp.get('must_have_noncorrect'):
        assert any(u.status!='correct' for u in final.semantic_units)
    if case['id'].endswith(('natural_03','natural_04','awkward_11')):
        assert '意味関係が原文と異な' not in final.feedback
        assert all(u.status=='correct' for u in final.semantic_units)
    if case['id'].endswith(('awkward_10','awkward_11','awkward_12')):
        assert final.score_breakdown.meaning==before.score_breakdown.meaning or case['id'].endswith('awkward_11')
        assert '日本語品質' in final.feedback
    again=replay({**case,'evaluation':final.model_dump()})
    assert again.score==final.score
    assert again.score_breakdown.japanese==final.score_breakdown.japanese


@pytest.mark.parametrize('case,answer',[
    (ID03,'最小曲げ半径は不可逆的な劣化が5%以上となる範囲で最も小さい曲げ半径と定義する。'),
    (ID03,'最小曲げ半径は不可逆的な劣化が5%未満となる範囲で最も大きい曲げ半径と定義する。'),
    (ID03,'最小曲げ半径は不可逆的な劣化が7%未満となる範囲で最も小さい曲げ半径と定義する。'),
    (ID04,'含浸は素線同士の相対的なすべりを妨げ、ケーブルの柔軟性を失わせない。'),
    (ID04,'素線同士の相対的なすべりが含浸を妨げ、ケーブルの柔軟性を失わせる。'),
    (ID11,'両ケーブルは転位長が227 mmであるということになっており、15本の素線から構成されているということになっている。'),
])
def test_equivalence_rejects_negation_wrong_quantity_subject_and_definition(case,answer):
    before=m.TranslationEvaluation.model_validate(case['evaluation'])
    after=m._audit_quiz_v1725_blind4_general_guards(before,answer,source_text=case['source_text'])
    if case is ID11:
        assert after.semantic_units[1].status=='wrong'
    else:
        assert any(u.status=='wrong' for u in after.semantic_units)


@pytest.mark.parametrize('answer,expected',[
    ('ケーブルをコイル形状に曲げた後に含浸する。',False),
    ('ケーブルをコイル形状に曲げる前に含浸する。',True),
    ('試料を測定する前に曲げた後、含浸を行う。',False),
])
def test_before_after_requires_same_event(answer,expected):
    assert m._quiz_v1725_reversed_procedure('after the cable is bent into the coil shape',answer)==expected


@pytest.mark.parametrize('unit,answer,back,expected_missing',[
    ('compressive bending to a radius of 6 mm','圧縮曲げに耐えた','',True),
    ('compressive bending to a radius of 6 mm','半径0.6 cmまで曲げた','',False),
    ('with less than 5% irreversible degradation','不可逆劣化5パーセント未満であった','',False),
    ('with less than 5% irreversible degradation','不可逆劣化5%未満であった','',False),
    ('with less than 5% irreversible degradation','不可逆劣化は小さい','under 5 percent irreversible degradation',False),
    ('with less than 5% irreversible degradation','不可逆劣化は小さい','',True),
])
def test_missing_scientific_quantity_is_conservative(unit,answer,back,expected_missing):
    assert bool(m._quiz_v1725_absent_quantities(unit,answer,back))==expected_missing


@pytest.mark.parametrize('answer',[
    '曲げひずみが負になることが起こるということになる。',
    '両ケーブルは転位長が226 mmであるということになっており、15本の素線から構成されているということになっている。',
    'この影響を考慮することが必要となることが求められる。',
])
def test_strong_redundancies_have_concrete_explanation(answer):
    assert m._quiz_japanese_surface_strong_fluency_hints(answer)


@pytest.mark.parametrize('answer',[
    '曲げひずみは負になる。',
    '転位長は226 mmで、ケーブルは15本の素線から構成される。',
    'T = 77 Kで事前試験する場合は、この影響を考慮する必要がある。',
    '原文によると、以前は治具を交換することになっている。',
])
def test_natural_sentences_are_not_over_penalized(answer):
    assert not m._quiz_japanese_surface_strong_fluency_hints(answer)


def test_quantitative_guards_do_not_create_missing_for_lone_implicit_temperature():
    data=m.TranslationEvaluation.model_validate(ID13['evaluation'])
    before=[u.status for u in data.semantic_units]
    # Only one quantitative condition in this substituted unit-source sentence;
    # translating 77 K as liquid-nitrogen temperature should defer to the model.
    source='The sample was cooled down to T = 77 K.'
    fake=data.model_copy(update={'semantic_units':[data.semantic_units[0].model_copy(update={'source':source,'status':'correct'})]})
    out=m._audit_quiz_v1725_blind4_general_guards(fake,'試料は液体窒素温度に冷却された。',source_text=source)
    assert out.semantic_units[0].status=='correct'
