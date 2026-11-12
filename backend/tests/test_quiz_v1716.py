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


def _evaluation(units, issues=None):
    return m.TranslationEvaluation(
        verdict="correct",
        score=100,
        feedback="",
        reference_translation="基準訳",
        issues=issues or [],
        key_points=[
            m.KeyPoint(
                source=u.source,
                translation=u.translation,
                status="correct" if u.status == "correct" else "warning" if u.status == "partial" else "missing",
            )
            for u in units
        ],
        semantic_units=units,
        japanese_quality=m.JapaneseQuality(level="natural", note=""),
    )


def test_v1716_revision_and_cache_generation() -> None:
    assert m.read_root()["quiz_revision"] in {"v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    assert m._quiz_rubric_cache_path().name == "quiz_rubric_cache_v10.json"


def test_explicit_proportionality_signatures_are_bilingual() -> None:
    assert m._quiz_proportionality_signature("was proportional to the applied load") == "direct"
    assert m._quiz_proportionality_signature("was inversely proportional to the applied load") == "inverse"
    assert m._quiz_proportionality_signature("荷重に比例した") == "direct"
    assert m._quiz_proportionality_signature("荷重に反比例した") == "inverse"


def test_direct_to_inverse_proportionality_is_hard_relation_error() -> None:
    unit = m.SemanticUnit(
        id="u2",
        source="was proportional to the applied load",
        translation="加えられた荷重に比例した",
        importance="core",
        status="correct",
        note="",
        evidence_span="加えた荷重に反比例した",
    )
    out = m._audit_quiz_proportionality_relations(
        _evaluation([unit]),
        user_answer="変位は加えた荷重に反比例した。",
        backtranslation="The displacement was inversely proportional to the applied load.",
    )
    assert out.semantic_units[0].status == "wrong"
    assert out.semantic_units[0].note.startswith(m._QUIZ_RELATION_AUDIT_PREFIX)
    assert any(i.category == "mistranslation" for i in out.issues)


def test_wrong_rescue_never_clears_inverse_proportionality() -> None:
    unit = m.SemanticUnit(
        id="u2",
        source="was proportional to the applied load",
        translation="加えられた荷重に比例した",
        importance="core",
        status="wrong",
        note="関係が異なる",
        evidence_span="加えた荷重に反比例した",
    )
    out = m._audit_quiz_backtranslation_semantic_rescue(
        _evaluation([unit]),
        backtranslation="was inversely proportional to the applied load",
    )
    assert out.semantic_units[0].status == "wrong"


def test_order_of_magnitude_to_two_times_is_quantitative_error() -> None:
    unit = m.SemanticUnit(
        id="u3",
        source="by over one order of magnitude",
        translation="1桁以上",
        importance="detail",
        status="missing",
        note="",
        evidence_span="",
    )
    out = m._audit_quiz_order_of_magnitude_conflicts(
        _evaluation([unit]),
        user_answer="輝度を約2倍に向上させる。",
        backtranslation="increase the brilliance by about 2 times",
    )
    assert out.semantic_units[0].status == "wrong"
    assert out.semantic_units[0].note.startswith(m._QUIZ_QUANT_AUDIT_PREFIX)


def test_order_of_magnitude_valid_factor_is_not_flagged() -> None:
    unit = m.SemanticUnit(
        id="u3",
        source="by over one order of magnitude",
        translation="1桁以上",
        importance="detail",
        status="correct",
        note="",
        evidence_span="12倍超",
    )
    ev = _evaluation([unit])
    out = m._audit_quiz_order_of_magnitude_conflicts(
        ev,
        user_answer="輝度を12倍超に向上させる。",
        backtranslation="increase the brilliance by more than 12 times",
    )
    assert out.semantic_units[0].status == "correct"


def test_set_coverage_rescues_correct_relative_clause_paraphrase() -> None:
    source = "which determine the beam trajectory along the undulator"
    unit = m.SemanticUnit(
        id="u3",
        source=source,
        translation="アンジュレータ内のビーム軌道を決定する",
        importance="support",
        status="wrong",
        note="軌道決定の対象が異なる",
        evidence_span="ビーム軌道を決める",
    )
    ev = _evaluation([unit], issues=[m.TranslationIssue(
        category="mistranslation",
        source_span=source,
        message="軌道決定の対象が異なる",
        suggestion=unit.translation,
    )])
    out = m._audit_quiz_backtranslation_semantic_rescue(
        ev,
        backtranslation=(
            "Adjusting the first and second integrals of the on-axis magnetic field "
            "that determine the beam trajectory within the undulator is the main role of the correction current."
        ),
    )
    assert out.semantic_units[0].status == "correct"
    assert not any(i.category == "mistranslation" for i in out.issues)
