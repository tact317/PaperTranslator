"""v1.7.23: blind2-exposed Japanese fluency and learner feedback regression.

No Qwen request or new forward/backtranslation is performed. These four cases
were already observed in blind2, hence they are regression data, NOT new blind.
"""
from __future__ import annotations
import sys
import types
import pytest

fake_ollama = types.ModuleType("ollama")
class _DummyClient:
    def __init__(self,*args,**kwargs): pass
    def list(self): return {"models": []}
fake_ollama.Client = _DummyClient
fake_ollama.chat = lambda *args,**kwargs: {"message":{"content":"{}"}}
sys.modules.setdefault("ollama", fake_ollama)
from backend import main as m

FAIL_INPUTS = [
    "これらのテープのJcが磁場とテープ表面との間の角度によって著しく影響されるということは、注意されることが重要である。",
    "この設計はReBCOバルクを磁化するための一様な双極子磁場を生成することを行うためにレーストラックコイルを統合している。",
    "冷たいソレノイド磁石の内部へ統合されているHTSインサートは、GM冷凍機とヒーターを使うことによって4 Kから100 Kを超えるまでの温度の制御を容易にすることを可能にする。",
    "文献[5,103]で議論されているように、これらの進展は、励磁遅れとアンジュレータ磁場と励磁電流の間のヒステリシスを最小化することが可能であるかもしれないという可能性を有する。",
]

NATURAL_INPUTS = [
    "これらのテープのJcは、磁場とテープ表面のなす角度によって大きく変化することに注意が必要である。",
    "この設計ではレーストラックコイルを使用し、ReBCOバルクの磁化に必要な一様な双極子磁場を生成する。",
    "GM冷凍機とヒーターにより、HTSインサートの温度を4 Kから100 K超まで調整できる。",
    "これらの改善によって、励磁遅れとアンジュレータ磁場・励磁電流間のヒステリシスを低減できる可能性がある。",
    "実験を行うことが必要である。",
    "可能性を有する条件を調査した。",
    "注意することが重要である。",
]


def _neutral_eval(*, note='') -> m.TranslationEvaluation:
    unit=m.SemanticUnit(id='u1',source='scientific meaning unit',translation='意味単位',importance='core',status='correct')
    return m.TranslationEvaluation(
        verdict='correct', score=100, feedback='採点理由を生成できませんでした。',
        reference_translation='意味単位が保持される。',
        key_points=[m.KeyPoint(source=unit.source,translation=unit.translation,status='correct')],
        semantic_units=[unit], japanese_quality=m.JapaneseQuality(level='natural',note=note),
    )


def test_version():
    assert m.QUIZ_GRADER_VERSION in {'quiz-grader-v1.7.26', 'quiz-grader-v1.7.27'}
    assert m.read_root()['quiz_revision'] in {'v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue','v1.7.27-source-anchored-science-and-japanese-fluency'}


@pytest.mark.parametrize('answer', FAIL_INPUTS)
def test_strong_redundant_japanese_constructions_downgrade_only_fluency(answer: str):
    ev=_neutral_eval()
    result=m._reconcile_evaluation_consistency(ev,user_answer=answer)
    assert result.japanese_quality.level=='awkward'
    assert result.score_breakdown.japanese==10
    assert result.score_breakdown.meaning==70
    assert result.score_breakdown.terminology==15
    assert result.verdict=='correct'
    assert '採点理由を生成できませんでした' not in result.feedback
    assert '日本語' in result.feedback
    assert '可能性を重複' in result.feedback or '二重' in result.feedback or '受動表現' in result.feedback


@pytest.mark.parametrize('answer', NATURAL_INPUTS)
def test_normal_scientific_expressions_are_not_matched_as_severe(answer: str):
    assert not m._quiz_japanese_surface_strong_fluency_hints(answer)


def test_japanese_fluency_and_semantic_severity_are_independent():
    bad=_neutral_eval()
    wrong=bad.semantic_units[0].model_copy(update={'status':'wrong','note':'正反対の物理的関係'})
    bad=bad.model_copy(update={
        'semantic_units':[wrong],
        'issues':[m.TranslationIssue(category='mistranslation',source_span=wrong.source,message='物理関係の反転',suggestion='意味単位')]
    })
    result=m._reconcile_evaluation_consistency(bad,user_answer=FAIL_INPUTS[2])
    assert result.semantic_units[0].status=='wrong'
    assert any(issue.category=='mistranslation' for issue in result.issues)
    assert result.score<=59
    assert result.score_breakdown.japanese==10


def test_meaning_correct_missing_model_feedback_gets_factual_fallback():
    ev=_neutral_eval()
    result=m._reconcile_evaluation_consistency(ev,user_answer='原文に対応する情報がすべて含まれる。')
    assert result.feedback=='原文の主要な意味単位は訳文に保持されています。'


def test_explicit_good_model_feedback_never_overwritten():
    ev=_neutral_eval().model_copy(update={'feedback':'主語と述語の対応は適切です。'})
    result=m._reconcile_evaluation_consistency(ev,user_answer=FAIL_INPUTS[0])
    assert result.feedback.startswith('主語と述語の対応は適切です。')
    assert '日本語品質' in result.feedback
    assert result.score_breakdown.japanese==10


def test_minor_surface_hint_is_idempotent_after_note_augmentation():
    text="450 °C・2時間の熱処理により、引張強さは18%向上したが、伸び率は12%から8%へ減少した。"
    once=m._reconcile_evaluation_consistency(_neutral_eval(), user_answer=text)
    twice=m._reconcile_evaluation_consistency(once, user_answer=text)
    assert once.score_breakdown.japanese==13
    assert twice.score_breakdown.japanese==13
    assert twice.japanese_quality.level=='minor'


def test_severe_surface_hint_is_idempotent_after_note_augmentation():
    once=m._reconcile_evaluation_consistency(_neutral_eval(), user_answer=FAIL_INPUTS[0])
    twice=m._reconcile_evaluation_consistency(once, user_answer=FAIL_INPUTS[0])
    assert once.score_breakdown.japanese==10
    assert twice.score_breakdown.japanese==10
    assert twice.score_breakdown.meaning==once.score_breakdown.meaning
