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

ALLOW_UNIT = "and allow experiments to be carried out"


def _evaluation(status: str = "partial") -> m.TranslationEvaluation:
    unit = m.SemanticUnit(
        id="u5",
        source=ALLOW_UNIT,
        translation="実験を実施できるようにする",
        importance="detail",
        status=status,
        note="",
    )
    return m.TranslationEvaluation(
        verdict="correct",
        score=100,
        feedback="",
        reference_translation="基準訳",
        semantic_units=[unit],
        key_points=[m.KeyPoint(source=ALLOW_UNIT, translation=unit.translation, status="warning")],
    )


def test_v175_revision_and_cache_version() -> None:
    assert m.read_root()["quiz_revision"] in {"v1.7.5-predicate-argument-guard", "v1.7.6-importance-japanese-quality", "v1.7.7-japanese-consistency-eval-harness", "v1.7.8-quantitative-integrity-fluency-guard", "v1.7.9-semantic-evidence-hardening", "v1.7.10-evidence-span-verified-omission", "v1.7.11-single-pass-evidence-consensus", "v1.7.12-magnitude-equivalence-rescue", "v1.7.13-consensus-severity-equivalence", "v1.7.14-japanese-surface-fluency", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-v1.7.5", "quiz-grader-v1.7.6", "quiz-grader-v1.7.7", "quiz-grader-v1.7.8", "quiz-grader-v1.7.9", "quiz-grader-v1.7.10", "quiz-grader-v1.7.11", "quiz-grader-v1.7.12", "quiz-grader-v1.7.13", "quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}


def test_allow_relation_missing_enabled_object_is_missing() -> None:
    # This mirrors the field failure: the learner mentions that >60 keV photons
    # can be used, but says nothing about experiments being made possible.
    back = (
        "Compared with other state-of-the-art undulator technologies, the BHTSU source "
        "will increase beamline brilliance by more than one order of magnitude, and "
        "photon energies above 60 keV can be obtained and used."
    )
    out = m._audit_quiz_predicate_argument_relations(_evaluation(), back)
    assert out.semantic_units[0].status == "missing"
    assert out.key_points[0].status == "missing"


def test_allow_relation_valid_free_paraphrase_survives() -> None:
    back = "The source makes it possible to conduct experiments at photon energies above 60 keV."
    out = m._audit_quiz_predicate_argument_relations(_evaluation("correct"), back)
    assert out.semantic_units[0].status == "correct"


def test_allow_relation_test_synonym_survives() -> None:
    back = "This enables tests to be performed above 60 keV."
    out = m._audit_quiz_predicate_argument_relations(_evaluation("correct"), back)
    assert out.semantic_units[0].status == "correct"


def test_object_without_enabling_relation_is_not_forced_missing() -> None:
    # The object survives.  Whether the relation is sufficiently explicit is a
    # semantic-grader decision; this deterministic guard must not overreach.
    back = "Experiments at photon energies above 60 keV are discussed."
    out = m._audit_quiz_predicate_argument_relations(_evaluation("partial"), back)
    assert out.semantic_units[0].status == "partial"


def test_no_backtranslation_does_not_change_grading() -> None:
    out = m._audit_quiz_predicate_argument_relations(_evaluation("partial"), "")
    assert out.semantic_units[0].status == "partial"


def test_unrelated_partial_unit_is_untouched() -> None:
    unit = m.SemanticUnit(
        id="u3",
        source="by over one order of magnitude",
        translation="1桁以上",
        importance="detail",
        status="partial",
        note="",
    )
    evaluation = m.TranslationEvaluation(
        verdict="partial", score=90, feedback="", reference_translation="基準訳",
        semantic_units=[unit],
        key_points=[m.KeyPoint(source=unit.source, translation=unit.translation, status="warning")],
    )
    out = m._audit_quiz_predicate_argument_relations(evaluation, "by more than one order of magnitude")
    assert out.semantic_units[0].status == "partial"


def test_field_86_point_case_drops_to_78_when_experiment_event_is_missing() -> None:
    sources = [
        ("The very hard x-ray source generated by the BHTSU", "core"),
        ("will increase the brilliance at the beamline", "core"),
        ("by over one order of magnitude", "support"),
        ("in comparison to other state-of-the-art undulator technologies", "support"),
        (ALLOW_UNIT, "support"),
        ("with photon energies in excess of 60 keV", "support"),
    ]
    units = [
        m.SemanticUnit(
            id=f"u{i+1}", source=source, translation=f"訳{i+1}",
            importance=importance, status="partial", note="",
        )
        for i, (source, importance) in enumerate(sources)
    ]
    evaluation = m.TranslationEvaluation(
        verdict="correct", score=86, feedback="", reference_translation="基準訳",
        semantic_units=units,
        key_points=[m.KeyPoint(source=u.source, translation=u.translation, status="warning") for u in units],
    )
    before = m._apply_semantic_scoring(evaluation)
    assert before.score == 86
    back = (
        "Compared with other state-of-the-art undulator technologies, the very hard X-ray source generated by BHTSU "
        "will increase beamline brilliance by more than one order of magnitude, and photon energies above 60 keV can be used."
    )
    guarded = m._audit_quiz_predicate_argument_relations(evaluation, back)
    after = m._apply_semantic_scoring(guarded)
    assert next(u for u in after.semantic_units if u.source == ALLOW_UNIT).status == "missing"
    assert after.score == 78
    assert after.verdict == "partial"
