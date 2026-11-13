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


def test_v1721_revision_and_cache_generation() -> None:
    assert m.read_root()["quiz_revision"] in {"phase99-numeric-integrity-v1", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-phase99-numeric-integrity-v1", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
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


# This fixture is copied from the user's v1.7.20 read-only forensic capture:
# the ORIGINAL learner response contains the exact strict Japanese glossary term,
# while Azure mistranscribes undulator as "endurator". No synthetic backtranslation
# variant is substituted for the real evidence.
_DIAGNOSTIC_SOURCE = (
    "The main function of the correction current is to adjust the first and second "
    "integrals of the magnetic field on-axis which determine the beam trajectory along the undulator."
)
_DIAGNOSTIC_ANSWER = (
    "アンジュレータ内のビーム軌道を決める軸上磁場の第1・第2積分を調整することが、補正電流の主な役割である。"
)
_DIAGNOSTIC_REVERSE = (
    "The main role of the correcting current is to adjust the first and second "
    "integrals of the axial magnetic field that determine the beam path inside the endurator."
)


def test_v1721_actual_v1720_forensic_reverse_is_rescued_safely() -> None:
    import json
    from pathlib import Path

    case = json.loads((Path(__file__).parents[2] / "evaluation/quiz_v1724_regression.json").read_text(encoding="utf-8"))
    case = next(c for c in case["cases"] if c["id"] == "blind_ihep_paraphrase_01")
    assert case["source_text"] == _DIAGNOSTIC_SOURCE
    assert case["user_answer"] == _DIAGNOSTIC_ANSWER
    assert "endurator" in _DIAGNOSTIC_REVERSE and "undulator" not in _DIAGNOSTIC_REVERSE

    original = _evaluation()
    original = original.model_copy(update={"reference_translation": (
        "補正電流の主な機能は、磁場の第1および第2の積分を調整し、"
        "その積分値がビームの軌道を決定するアンジュレータ内の軌道を決める。"
    )})
    output = m._audit_quiz_backtranslation_semantic_rescue(
        original, backtranslation=_DIAGNOSTIC_REVERSE, user_answer=_DIAGNOSTIC_ANSWER,
    )
    assert output.semantic_units[2].status == "correct"
    assert not any(issue.category == "mistranslation" for issue in output.issues)
    assert output.reference_translation == original.reference_translation  # source-only cache not rewritten
    # No global changes to the Azure string or the existing cached rubric.
    assert "endurator" in _DIAGNOSTIC_REVERSE


def test_v1721_without_exact_japanese_glossary_target_does_not_rescue() -> None:
    out = m._audit_quiz_backtranslation_semantic_rescue(
        _evaluation(), backtranslation=_DIAGNOSTIC_REVERSE,
        user_answer="装置内のビーム軌道を決める軸上磁場の第1・第2積分を調整する。",
    )
    assert out.semantic_units[2].status == "wrong"


def test_v1721_reverse_lookalike_real_technical_words_are_not_autocorrected() -> None:
    source = _unit().source
    antecedent = "is to adjust the first and second integrals of the magnetic field on-axis"
    for real_term in ("insulator", "modulator"):
        back = _DIAGNOSTIC_REVERSE.replace("endurator", real_term)
        assert m._quiz_backtranslation_glossary_typo_evidence(source, back, _DIAGNOSTIC_ANSWER) == back
        assert not m._quiz_relative_clause_backtranslation_equivalent(
            source, back, antecedent, user_answer=_DIAGNOSTIC_ANSWER,
        )


def test_v1721_no_rescue_for_negation_or_spatial_reversal_despite_azure_typo() -> None:
    antecedent = "is to adjust the first and second integrals of the magnetic field on-axis"
    for back in (
        _DIAGNOSTIC_REVERSE.replace("that determine", "that do not determine"),
        _DIAGNOSTIC_REVERSE.replace("inside the endurator", "outside the endurator"),
        "The beam path inside the endurator determines the on-axis magnetic field integrals.",
        _DIAGNOSTIC_REVERSE.replace("that determine", "that decrease"),
    ):
        assert not m._quiz_relative_clause_backtranslation_equivalent(
            _unit().source, back, antecedent_source=antecedent, user_answer=_DIAGNOSTIC_ANSWER,
        )


def test_v1721_multi_candidate_or_no_role_anchor_prevents_domain_repair() -> None:
    source = _unit().source
    with_two = _DIAGNOSTIC_REVERSE.replace("the endurator", "the endurator and endulator")
    assert m._quiz_backtranslation_glossary_typo_evidence(source, with_two, _DIAGNOSTIC_ANSWER) == with_two
    no_predicate = _DIAGNOSTIC_REVERSE.replace("determine", "conceal")
    assert m._quiz_backtranslation_glossary_typo_evidence(source, no_predicate, _DIAGNOSTIC_ANSWER) == no_predicate


def test_v1721_only_learner_verified_term_can_change_reverse_evidence() -> None:
    source = _unit().source
    adjusted = m._quiz_backtranslation_glossary_typo_evidence(source, _DIAGNOSTIC_REVERSE, _DIAGNOSTIC_ANSWER)
    assert adjusted.endswith("the undulator.")
    assert _DIAGNOSTIC_REVERSE.endswith("the endurator.")
    assert m._quiz_backtranslation_glossary_typo_evidence(source, _DIAGNOSTIC_REVERSE, "") == _DIAGNOSTIC_REVERSE


def test_v1721_real_reverse_reaches_correct_final_score_after_consistency() -> None:
    audited = m._audit_quiz_backtranslation_semantic_rescue(
        _evaluation(), backtranslation=_DIAGNOSTIC_REVERSE, user_answer=_DIAGNOSTIC_ANSWER,
    )
    result = m._reconcile_evaluation_consistency(audited, user_answer=_DIAGNOSTIC_ANSWER)
    assert result.verdict == "correct"
    assert result.score == 100
    assert all(point.status == "correct" for point in result.key_points)
    assert not [issue for issue in result.issues if issue.category in {"omission", "mistranslation"}]
