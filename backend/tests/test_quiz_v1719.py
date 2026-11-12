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


def _evaluation(unit: m.SemanticUnit) -> m.TranslationEvaluation:
    return m.TranslationEvaluation(
        verdict="partial",
        score=82,
        feedback="",
        reference_translation="基準訳",
        issues=[m.TranslationIssue(
            category="mistranslation",
            source_span=unit.source,
            message="関係が間違っている",
            suggestion=unit.translation,
        )],
        key_points=[m.KeyPoint(source=unit.source, translation=unit.translation, status="missing")],
        semantic_units=[unit],
        japanese_quality=m.JapaneseQuality(level="natural", note=""),
    )


def _wrong_relative_unit() -> m.SemanticUnit:
    return m.SemanticUnit(
        id="u3",
        source="which determine the beam trajectory along the undulator",
        translation="アンジュレータ内のビーム軌道を決定する",
        importance="support",
        status="wrong",
        note="関係が間違っている",
        evidence_span="",
    )


def test_v1719_revision_and_cache_generation() -> None:
    assert m.read_root()["quiz_revision"] in {"v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    assert m._quiz_rubric_cache_path().name == "quiz_rubric_cache_v10.json"


def test_relation_lemma_preserves_silent_e_predicate_inflections() -> None:
    assert m._quiz_relation_lemma("determine") == "determine"
    assert m._quiz_relation_lemma("determines") == "determine"
    assert m._quiz_relation_lemma("determined") == "determine"
    assert m._quiz_relation_lemma("determining") == "determine"
    assert m._quiz_relation_lemma("increases") == "increase"
    assert m._quiz_relation_lemma("decreases") == "decrease"
    assert m._quiz_relation_lemma("reduces") == "reduce"
    assert m._quiz_relation_lemma("measured") == "measure"


def test_v1719_real_failure_shape_accepts_singular_backtranslation_predicate() -> None:
    unit = _wrong_relative_unit()
    ev = _evaluation(unit)
    # Azure may choose singular agreement after reconstructing the Japanese
    # relative clause, yielding "determines" although the source has "determine".
    backtranslation = (
        "The main role of the correction current is to adjust the first and second integrals "
        "of the on-axis magnetic field, which determines the beam orbit in the undulator."
    )
    assert m._quiz_relation_content_sequence(unit.source) == [
        "determine", "beam", "trajectory", "along", "undulator"
    ]
    assert "determine" in m._quiz_relation_content_concepts(backtranslation)
    assert "trajectory" in m._quiz_relation_content_concepts(backtranslation)
    assert m._quiz_relative_clause_backtranslation_equivalent(unit.source, backtranslation)
    out = m._audit_quiz_backtranslation_semantic_rescue(ev, backtranslation=backtranslation)
    assert out.semantic_units[0].status == "correct"
    assert not any(i.category == "mistranslation" for i in out.issues)


def test_v1719_relation_rescue_still_rejects_negated_determines() -> None:
    unit = _wrong_relative_unit()
    backtranslation = (
        "The magnetic-field integrals do not determine the beam trajectory in the undulator."
    )
    assert not m._quiz_relative_clause_backtranslation_equivalent(unit.source, backtranslation)
    out = m._audit_quiz_backtranslation_semantic_rescue(
        _evaluation(unit), backtranslation=backtranslation
    )
    assert out.semantic_units[0].status == "wrong"


def test_v1719_relation_rescue_still_rejects_outside_reversal() -> None:
    unit = _wrong_relative_unit()
    backtranslation = (
        "The magnetic-field integrals determine the beam trajectory outside the undulator."
    )
    assert m._quiz_spatial_relation_conflicts(unit.source, backtranslation)
    assert not m._quiz_relative_clause_backtranslation_equivalent(unit.source, backtranslation)


def test_v1719_relation_rescue_still_rejects_changed_predicate() -> None:
    unit = _wrong_relative_unit()
    backtranslation = "The magnetic-field integrals distort the beam trajectory in the undulator."
    assert not m._quiz_relative_clause_backtranslation_equivalent(unit.source, backtranslation)
