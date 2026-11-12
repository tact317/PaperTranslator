from __future__ import annotations

import sys
import types

fake_ollama = types.ModuleType("ollama")


class _DummyClient:
    def __init__(self, *args, **kwargs):
        pass

    def list(self):
        return {"models": []}


fake_ollama.Client = _DummyClient
fake_ollama.chat = lambda *args, **kwargs: {"message": {"content": "{}"}}
sys.modules.setdefault("ollama", fake_ollama)

from backend import main as m


def _unit() -> m.SemanticUnit:
    return m.SemanticUnit(
        id="u3",
        source="which determine the beam trajectory along the undulator",
        translation="アンジュレータ内のビーム軌道を決定する",
        importance="support",
        status="wrong",
        note="関係が間違っている",
        evidence_span="",
    )


def _evaluation() -> m.TranslationEvaluation:
    u1 = m.SemanticUnit(
        id="u1", source="The main function of the correction current",
        translation="補正電流の主な機能", importance="core", status="correct"
    )
    u2 = m.SemanticUnit(
        id="u2", source="is to adjust the first and second integrals of the magnetic field on-axis",
        translation="軸上磁場の第1・第2積分を調整する", importance="core", status="correct"
    )
    u3 = _unit()
    return m.TranslationEvaluation(
        verdict="partial", score=82, feedback="", reference_translation="基準訳",
        issues=[m.TranslationIssue(category="mistranslation", source_span=u3.source, message="関係が間違っている", suggestion=u3.translation)],
        key_points=[m.KeyPoint(source=u3.source, translation=u3.translation, status="missing")],
        semantic_units=[u1, u2, u3],
        japanese_quality=m.JapaneseQuality(level="natural", note=""),
    )


def test_v1720_revision_and_cache_generation() -> None:
    assert m.read_root()["quiz_revision"] == "v1.7.20-relative-clause-role-preserving-rescue"
    assert m.QUIZ_GRADER_VERSION == "quiz-grader-v1.7.20"
    assert m._quiz_rubric_cache_path().name == "quiz_rubric_cache_v10.json"


def test_relative_clause_accepts_noun_of_noun_reordering_with_antecedent_anchor() -> None:
    source = _unit().source
    antecedent = "is to adjust the first and second integrals of the magnetic field on-axis"
    back = (
        "The main role of the correction current is to adjust the first and second integrals "
        "of the on-axis magnetic field, which determine the trajectory of the beam in the undulator."
    )
    assert m._quiz_relative_clause_backtranslation_equivalent(source, back, antecedent_source=antecedent)
    out = m._audit_quiz_backtranslation_semantic_rescue(_evaluation(), backtranslation=back)
    assert out.semantic_units[2].status == "correct"
    assert not any(i.category == "mistranslation" for i in out.issues)


def test_relative_clause_rejects_antecedent_reattachment_to_correction_current() -> None:
    source = _unit().source
    antecedent = "is to adjust the first and second integrals of the magnetic field on-axis"
    back = "The correction current determines the trajectory of the beam in the undulator."
    assert not m._quiz_relative_clause_backtranslation_equivalent(source, back, antecedent_source=antecedent)


def test_relative_clause_rejects_subject_object_role_reversal() -> None:
    source = _unit().source
    antecedent = "is to adjust the first and second integrals of the magnetic field on-axis"
    back = "The beam trajectory in the undulator determines the on-axis magnetic-field integrals."
    assert not m._quiz_relative_clause_backtranslation_equivalent(source, back, antecedent_source=antecedent)


def test_relative_clause_still_rejects_negation_and_outside_reversal() -> None:
    source = _unit().source
    antecedent = "is to adjust the first and second integrals of the magnetic field on-axis"
    neg = "The on-axis magnetic-field integrals do not determine the trajectory of the beam in the undulator."
    outside = "The on-axis magnetic-field integrals determine the trajectory of the beam outside the undulator."
    assert not m._quiz_relative_clause_backtranslation_equivalent(source, neg, antecedent_source=antecedent)
    assert not m._quiz_relative_clause_backtranslation_equivalent(source, outside, antecedent_source=antecedent)
