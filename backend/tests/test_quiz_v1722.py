from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

fake_ollama = types.ModuleType("ollama")
class _DummyClient:
    def __init__(self, *args, **kwargs): pass
    def list(self): return {"models": []}
fake_ollama.Client = _DummyClient
fake_ollama.chat = lambda *args, **kwargs: {"message": {"content": "{}"}}
sys.modules.setdefault("ollama", fake_ollama)

from backend import main as m

# Exact strings captured in the uploaded v1.7.21 fresh smoke report and previous
# read-only v1.7.20 forensic capture; no mock translation is substituted here.
BACKTRANSLATION = (
    "The main role of the correcting current is to adjust the first and second "
    "integrals of the axial magnetic field that determine the beam path inside the endurator."
)
LEARNER_ANSWER = "アンジュレータ内のビーム軌道を決める軸上磁場の第1・第2積分を調整することが、補正電流の主な役割である。"
RELATIVE_CLAUSE = "which determine the beam trajectory along the undulator"
ANTECEDENT = "is to adjust the first and second integrals of the magnetic field on-axis"


def _live_evaluation(evidence_span: str = "ビーム軌道を決める") -> m.TranslationEvaluation:
    # Snapshot of the semantic verdict, source spans and learner evidence from
    # v1.7.21 Windows output. The rubric/reference text is left unchanged.
    u1 = m.SemanticUnit(id="u1", source="The main function of the correction current", translation="補正電流の主な機能", importance="core", status="correct")
    u2 = m.SemanticUnit(id="u2", source=ANTECEDENT, translation="磁場の第1および第2の積分を調整する", importance="core", status="correct")
    u3 = m.SemanticUnit(id="u3", source=RELATIVE_CLAUSE, translation="その積分値がビームの軌道を決定するアンジュレータ内の軌道を決める", importance="support", status="wrong", note="軌道決定の対象がアンジュレータ内と異なる", evidence_span=evidence_span)
    return m.TranslationEvaluation(
        verdict="partial", score=82,
        feedback="「which determine the beam trajectory along the undulator」の意味関係が原文と異なります。",
        reference_translation="補正電流の主な機能は、磁場の第1および第2の積分を調整し、その積分値がビームの軌道を決定するアンジュレータ内の軌道を決める。",
        semantic_units=[u1,u2,u3],
        issues=[m.TranslationIssue(category="mistranslation", source_span=RELATIVE_CLAUSE, message="軌道決定の対象が異なる", suggestion="アンジュレータ内の軌道を決定する")],
        key_points=[m.KeyPoint(source=RELATIVE_CLAUSE,translation=u3.translation,status="missing")],
        japanese_quality=m.JapaneseQuality(level="natural",note="自然な日本語表現。"),
    )


def test_v1722_version_matches_package():
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    assert m.read_root()["quiz_revision"] in {"v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}


@pytest.mark.parametrize("span", ["ビーム軌道を決める", ""])
def test_live_windows_smoke_evidence_span_does_not_change_semantic_rescue(span: str):
    evaluation = _live_evaluation(evidence_span=span)
    result = m._audit_quiz_backtranslation_semantic_rescue(evaluation, backtranslation=BACKTRANSLATION, user_answer=LEARNER_ANSWER)
    assert result.semantic_units[2].status == "correct"
    assert not any(i.category == "mistranslation" for i in result.issues)
    finalized = m._reconcile_evaluation_consistency(result, user_answer=LEARNER_ANSWER)
    assert finalized.verdict == "correct"
    assert finalized.score == 100
    assert finalized.reference_translation == evaluation.reference_translation


@pytest.mark.parametrize("backtranslation", [
    BACKTRANSLATION.replace("that determine", "that do not determine"),
    BACKTRANSLATION.replace("inside the endurator", "outside the endurator"),
    BACKTRANSLATION.replace("that determine", "that reduce"),
    "The beam path inside the endurator determines the axial magnetic field integrals.",
    BACKTRANSLATION.replace("the endurator", "the insulator"),
    BACKTRANSLATION.replace("the endurator", "the modulator"),
])
def test_live_evidence_span_does_not_override_hard_semantic_guards(backtranslation: str):
    result = m._audit_quiz_backtranslation_semantic_rescue(_live_evaluation(), backtranslation=backtranslation, user_answer=LEARNER_ANSWER)
    assert result.semantic_units[2].status == "wrong"
    assert any(i.category == "mistranslation" for i in result.issues)


def test_live_evidence_span_missing_glossary_corroboration_is_not_rescued():
    result = m._audit_quiz_backtranslation_semantic_rescue(
        _live_evaluation(),
        backtranslation=BACKTRANSLATION,
        user_answer="装置内のビーム軌道を決める軸上磁場の第1・第2積分を調整することが主な役割である。",
    )
    assert result.semantic_units[2].status == "wrong"


def test_real_smoke_and_targeted_cases_unchanged():
    root = Path(__file__).resolve().parents[2] / "evaluation"
    smoke = json.loads((root / "quiz_v1724_smoke.json").read_text(encoding="utf-8"))
    targeted = json.loads((root / "quiz_v1724_regression.json").read_text(encoding="utf-8"))
    assert len(smoke["cases"]) == 1 and len(targeted["cases"]) == 13
    assert smoke["cases"][0] == next(x for x in targeted["cases"] if x["id"] == "blind_ihep_paraphrase_01")
    assert smoke["cases"][0]["user_answer"] == LEARNER_ANSWER
