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
        verdict="partial" if any(u.status != "correct" for u in units) else "correct",
        score=82 if any(u.status != "correct" for u in units) else 100,
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


def test_v1717_revision_and_cache_generation() -> None:
    assert m.read_root()["quiz_revision"] in {"phase99-numeric-integrity-v1", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-phase99-numeric-integrity-v1", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    assert m._quiz_rubric_cache_path().name == "quiz_rubric_cache_v10.json"


def test_verified_over_ten_times_is_not_collapsed_to_bare_ten() -> None:
    unit = m.SemanticUnit(
        id="u3",
        source="by over one order of magnitude",
        translation="1桁以上",
        importance="detail",
        status="wrong",
        note="model said magnitude mismatch",
        evidence_span="10倍を超えて",
    )
    ev = _evaluation([unit], issues=[m.TranslationIssue(
        category="mistranslation",
        source_span=unit.source,
        message="桁倍率が異なる",
        suggestion="1桁以上",
    )])
    out = m._audit_quiz_order_of_magnitude_conflicts(
        ev,
        user_answer="輝度は10倍を超えて高まる。",
        backtranslation="the brilliance increases by more than 10 times",
    )
    assert out.semantic_units[0].note == "model said magnitude mismatch"
    assert not out.semantic_units[0].note.startswith(m._QUIZ_QUANT_AUDIT_PREFIX)


def test_bare_ten_times_still_conflicts_with_over_one_order() -> None:
    unit = m.SemanticUnit(
        id="u3",
        source="by over one order of magnitude",
        translation="1桁以上",
        importance="detail",
        status="correct",
        note="",
        evidence_span="10倍",
    )
    out = m._audit_quiz_order_of_magnitude_conflicts(
        _evaluation([unit]),
        user_answer="輝度は10倍になる。",
        backtranslation="the brilliance increases by 10 times",
    )
    assert out.semantic_units[0].status == "wrong"
    assert out.semantic_units[0].note.startswith(m._QUIZ_QUANT_AUDIT_PREFIX)


def test_full_clause_backtranslation_can_rescue_missing_attachment_span() -> None:
    source = "which determine the beam trajectory along the undulator"
    unit = m.SemanticUnit(
        id="u3",
        source=source,
        translation="アンジュレータに沿ったビーム軌道を決定する",
        importance="support",
        status="wrong",
        note="関係が間違っている",
        evidence_span="",
    )
    ev = _evaluation([unit], issues=[m.TranslationIssue(
        category="mistranslation",
        source_span=source,
        message="関係が間違っている",
        suggestion=unit.translation,
    )])
    out = m._audit_quiz_backtranslation_semantic_rescue(
        ev,
        backtranslation=(
            "The main function is to adjust the first and second integrals of the magnetic field, "
            "which determine the beam trajectory along the undulator."
        ),
    )
    assert out.semantic_units[0].status == "correct"
    assert not any(i.category == "mistranslation" for i in out.issues)


def test_trend_subject_conflict_detects_rate_reversal_amid_temperature_rise() -> None:
    source = "The reaction rate increased with temperature"
    evidence = "As temperature increases, the reaction rate decreases."
    assert m._quiz_trend_subject_conflicts(source, evidence)
    assert m._quiz_relation_polarity_conflicts(source, evidence)


def test_wrong_rescue_never_clears_subject_trend_reversal() -> None:
    source = "The reaction rate increased with temperature"
    unit = m.SemanticUnit(
        id="u1",
        source=source,
        translation="反応速度は温度とともに上昇した",
        importance="core",
        status="wrong",
        note="反対の関係",
        evidence_span="温度が上がるほど反応速度は低下し",
    )
    out = m._audit_quiz_backtranslation_semantic_rescue(
        _evaluation([unit]),
        backtranslation="As temperature increases, the reaction rate decreases.",
    )
    assert out.semantic_units[0].status == "wrong"


def test_particle_he_proportionality_is_surface_fluency_hint() -> None:
    hints = m._quiz_japanese_surface_fluency_hints(
        "変位は適用された荷重へ比例していました。"
    )
    assert hints


def test_passive_potential_construction_is_surface_fluency_hint() -> None:
    hints = m._quiz_japanese_surface_fluency_hints(
        "校正は反対方向の測定へ直接適用されることができません。"
    )
    assert hints


def test_surface_hint_downgrades_japanese_quality_to_minor() -> None:
    unit = m.SemanticUnit(
        id="u1",
        source="was proportional to the applied load",
        translation="荷重に比例した",
        importance="core",
        status="correct",
        note="",
        evidence_span="適用された荷重へ比例していました",
    )
    out = m._reconcile_japanese_quality_consistency(
        _evaluation([unit]),
        user_answer="変位は適用された荷重へ比例していました。",
    )
    assert out.japanese_quality.level == "minor"
