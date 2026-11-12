"""Post-blind3 tests: observed five failures are REGRESSION, not fresh blind.

Learner answers and model evaluations are captured from the real 2026-10-09
v1.7.23 Windows result. Reconstructed English backtranslations below are
synthetic *test fixtures*, not claims about the actual Azure response.
"""
from __future__ import annotations
import json
import sys
import types
from pathlib import Path
import pytest

fake_ollama = types.ModuleType('ollama')
class _DummyClient:
    def __init__(self,*a,**k):pass
    def list(self):return {'models':[]}
fake_ollama.Client = _DummyClient
fake_ollama.chat = lambda *a,**k:{'message':{'content':'{}'}}
sys.modules.setdefault('ollama',fake_ollama)
from backend import main as m

FIXTURES=json.loads((Path(__file__).parent/'fixtures/v1724_blind3_failed_cases.json').read_text(encoding='utf-8'))['cases']
PARA=next(x for x in FIXTURES if x['id'].endswith('paraphrase_07'))
AWKWARD=[x for x in FIXTURES if x['id'].split('_')[-2]=='awkward']
SYNTHETIC_BACKTRANSLATION=(
    'To ensure full liquid nitrogen coverage in the bend region, a wavy surface was '
    'added where the conductor tape contacts the bending jig.'
)


def test_version_and_corpus():
    assert m.QUIZ_GRADER_VERSION in {'quiz-grader-v1.7.26', 'quiz-grader-v1.7.27'}
    assert m.read_root()['quiz_revision'] in {'v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue','v1.7.27-source-anchored-science-and-japanese-fluency'}
    root=Path(__file__).parents[2]/'evaluation'
    data=json.loads((root/'quiz_v1724_blind3_regression.json').read_text(encoding='utf-8'))
    assert len(data['cases'])==5
    assert {x['id'] for x in data['cases']}=={x['id'] for x in FIXTURES}
    assert all('POST-HOC' in x['regression_origin'] for x in data['cases'])


def test_real_failure_replay_apparatus_contact_with_independent_relation_checks():
    actual=m.TranslationEvaluation.model_validate(PARA['evaluation'])
    assert actual.semantic_units[-1].status=='wrong'
    assert any(i.category=='mistranslation' for i in actual.issues)
    rescued=m._audit_quiz_backtranslation_semantic_rescue(
        actual, backtranslation=SYNTHETIC_BACKTRANSLATION,
        user_answer=PARA['user_answer'],
    )
    assert rescued.semantic_units[-1].status=='correct'
    assert not any(i.category=='mistranslation' for i in rescued.issues)
    final=m._reconcile_evaluation_consistency(rescued,user_answer=PARA['user_answer'])
    assert final.score>=85
    assert final.verdict=='correct'
    assert final.score_breakdown.japanese==15
    assert '意味関係が原文と異な' not in final.feedback
    assert '保持されています' in final.feedback


@pytest.mark.parametrize('case',AWKWARD,ids=lambda c:c['id'])
def test_real_failure_replay_awkward_japanese_fluency_only(case):
    before=m.TranslationEvaluation.model_validate(case['evaluation'])
    result=m._reconcile_evaluation_consistency(before,user_answer=case['user_answer'])
    assert result.score_breakdown.japanese <= 12
    assert result.japanese_quality.level=='awkward'
    assert result.score_breakdown.meaning==before.score_breakdown.meaning
    assert result.score_breakdown.terminology==before.score_breakdown.terminology
    assert '日本語品質' in result.feedback
    again=m._reconcile_evaluation_consistency(result,user_answer=case['user_answer'])
    assert again.score_breakdown.japanese==result.score_breakdown.japanese
    assert again.feedback==result.feedback


@pytest.mark.parametrize('source,span,answer,context,back',[
    ('where the conductor tape touches the body','',PARA['user_answer'],'bend region','conductor tape contacts a bending jig'),
    ('where the conductor tape touches the body','テープと曲げ治具の接触面','テープと曲げ治具の接触面','normal room temperature storage','conductor tape contacts a bending jig'),
    ('where the conductor tape touches the body','テープと曲げ治具の接触面','テープと曲げ治具の接触面','bend region','conductor tape does not touch the bending jig'),
    ('where the conductor tape touches the body','テープが曲げ治具に接触しない部分','テープが曲げ治具に接触しない部分','bend region','conductor tape touches jig'),
    ('where the conductor tape touches the body','テープと人体の接触面','テープと人体の接触面','bend region','tape touches human body'),
    ('where the conductor tape touches the body','曲げ治具との接触面','曲げ治具との接触面','bend region','tape touches jig'),
    ('where the conductor tape touches the body','テープと曲げ治具の接触面','テープと曲げ治具の非接触面','bend region','tape touches jig'),
    ('where the sensor touches the body','テープと曲げ治具の接触面','テープと曲げ治具の接触面','bend region','sensor touches jig'),
    ('where the conductor tape touches the body','テープと曲げ治具の接触面','テープと曲げ治具の接触面','bend region','conductor tape contacts the outside of the body'),
])
def test_apparatus_guard_never_rescues_unverified_or_reversed_relations(source,span,answer,context,back):
    assert not m._quiz_bending_apparatus_contact_equivalent(source,span,answer,context,back)


@pytest.mark.parametrize('answer',[
    '曲げられることが行われた。','冷却されることが行われた。',
    'ひずみが誘起されることが起きた。','損傷の可能性があり得ることができる。',
    '負担を減らすことをするために、スリーブを含めることを行った。',
    'その実験を想定することをしている。',
])
def test_strong_japanese_only_surface_errors(answer):
    assert m._quiz_japanese_surface_strong_fluency_hints(answer)


@pytest.mark.parametrize('answer',[
    '室温で試料を曲げ、77 Kで測定した。',
    '曲げ治具とテープの接触面を波状に加工した。',
    '研究者は実験を行うことが重要だと考えた。',
    'できることをするという方針を掲げた。',
    '曲げひずみが発生し、通電特性を損なう可能性がある。',
    '試料の追加評価を想定している。',
])
def test_fluent_scientific_japanese_is_not_overpenalized(answer):
    assert not m._quiz_japanese_surface_strong_fluency_hints(answer)


def test_older_blind2_fluency_patterns_retained():
    old=json.loads((Path(__file__).parents[2]/'evaluation/quiz_v1724_fluency_regression.json').read_text(encoding='utf-8'))
    assert len(old['cases'])==4
    assert all(m._quiz_japanese_surface_strong_fluency_hints(x['user_answer']) for x in old['cases'])
