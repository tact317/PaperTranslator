from __future__ import annotations

import json
import sys
import types
from pathlib import Path

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


def _evaluation(
    units: list[m.SemanticUnit],
    *,
    issues: list[m.TranslationIssue] | None = None,
    level: str = "natural",
    note: str = "",
) -> m.TranslationEvaluation:
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
        japanese_quality=m.JapaneseQuality(level=level, note=note),
    )


def test_v1713_revision_and_cache_generation():
    assert m.read_root()["quiz_revision"] in {"v1.7.13-consensus-severity-equivalence", "v1.7.14-japanese-surface-fluency", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-v1.7.13", "quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    # Rubric definition is unchanged; source-only rubric cache stays reusable.
    assert m._quiz_rubric_cache_path().name == "quiz_rubric_cache_v10.json"


def test_all_correct_units_remove_orphan_material_issue():
    unit = m.SemanticUnit(
        id="u1",
        source="when the input distribution differed from the training data",
        translation="入力分布が訓練データと異なる場合",
        importance="support",
        status="correct",
        evidence_span="学習時とは異なる分布の入力に対して",
    )
    ev = _evaluation(
        [unit],
        issues=[m.TranslationIssue(
            category="mistranslation",
            source_span="入力分布が訓練データと異なる場合",
            message="表現が限定的",
            suggestion="入力分布が訓練データと異なる場合",
        )],
    )
    out = m._reconcile_material_issue_severity_from_units(ev)
    assert out.issues == []


def test_nonhard_partial_material_issue_is_downgraded_to_wording():
    source = "without a corresponding decrease in viability"
    unit = m.SemanticUnit(
        id="u1",
        source=source,
        translation="生存率は低下しなかった",
        importance="support",
        status="partial",
        note="対象が一部不明確",
        evidence_span="viabilityは維持されたまま",
    )
    ev = _evaluation(
        [unit],
        issues=[m.TranslationIssue(
            category="mistranslation",
            source_span=source,
            message="対象が一部不明確",
            suggestion="生存率は低下しなかった",
        )],
    )
    out = m._reconcile_material_issue_severity_from_units(ev)
    assert len(out.issues) == 1
    assert out.issues[0].category == "wording"


def test_hard_relation_partial_keeps_material_issue():
    source = "depends on the flow direction"
    unit = m.SemanticUnit(
        id="u1",
        source=source,
        translation="流れ方向に依存する",
        importance="core",
        status="partial",
        note=f"{m._QUIZ_RELATION_AUDIT_PREFIX} depend/rely on の依存対象が原文と一致していません。",
        evidence_span="流速に依存する",
    )
    ev = _evaluation(
        [unit],
        issues=[m.TranslationIssue(
            category="mistranslation",
            source_span=source,
            message="依存対象が異なる",
            suggestion="流れ方向に依存する",
        )],
    )
    out = m._reconcile_material_issue_severity_from_units(ev)
    assert out.issues[0].category == "mistranslation"


def test_backtranslation_can_rescue_model_mistranslation_label_on_partial():
    source = "when the input distribution differed from the training data"
    unit = m.SemanticUnit(
        id="u1",
        source=source,
        translation="入力分布が訓練データと異なる場合",
        importance="support",
        status="partial",
        note="表現が限定的",
        evidence_span="学習時とは異なる分布の入力に対して",
    )
    ev = _evaluation(
        [unit],
        issues=[m.TranslationIssue(
            category="mistranslation",
            source_span=source,
            message="完全に表現していない",
            suggestion="入力分布が訓練データと異なる場合",
        )],
    )
    out = m._audit_quiz_backtranslation_semantic_rescue(
        ev,
        backtranslation="the input distribution differed from the training data",
    )
    assert out.semantic_units[0].status == "correct"
    assert not any(i.category == "mistranslation" for i in out.issues)


def test_prevent_unsafe_accepts_keep_safe_complement():
    source = "to prevent the battery from entering an unsafe operating region"
    unit = m.SemanticUnit(
        id="u1",
        source=source,
        translation="バッテリーが危険な動作領域に入ることを防ぐ",
        importance="support",
        status="wrong",
        note="逆の関係を表現している",
        evidence_span="バッテリーを安全な運転範囲に保つため",
    )
    ev = _evaluation(
        [unit],
        issues=[m.TranslationIssue(
            category="mistranslation",
            source_span=source,
            message="逆の関係",
            suggestion=unit.translation,
        )],
    )
    out = m._audit_quiz_logical_complement_equivalence(ev)
    assert out.semantic_units[0].status == "correct"
    assert out.issues == []


def test_prevent_unsafe_accepts_literal_negative_form():
    source = "to prevent the battery from entering an unsafe operating region"
    assert m._quiz_japanese_matches_prevent_unsafe_relation(
        "安全でない運転領域へ入ることを防止するため"
    )
    assert m._quiz_japanese_matches_prevent_unsafe_relation(
        "バッテリーを安全な運転範囲に保つため"
    )
    assert not m._quiz_japanese_matches_prevent_unsafe_relation(
        "バッテリーを危険な運転範囲に保つため"
    )
    assert m._quiz_source_is_prevent_unsafe_relation(source)


def test_unsupported_awkward_label_is_limited_to_minor():
    unit = m.SemanticUnit(
        id="u1",
        source="the controller reduces the compressor speed",
        translation="コントローラーはコンプレッサーの速度を落とす",
        importance="core",
        status="correct",
        evidence_span="制御器はコンプレッサ速度を低下させる",
    )
    ev = _evaluation([unit], level="awkward", note="文の流れが自然でない。")
    out = m._reconcile_japanese_quality_consistency(ev, user_answer="制御器はコンプレッサ速度を低下させる。")
    assert out.japanese_quality.level == "minor"


def test_natural_label_with_explicit_improvement_note_becomes_minor():
    unit = m.SemanticUnit(
        id="u1",
        source="the controller reduces the compressor speed",
        translation="コントローラーはコンプレッサーの速度を落とす",
        importance="core",
        status="correct",
        evidence_span="コンプレッサ速度を減少します",
    )
    ev = _evaluation([unit], level="natural", note="意味は正確だが、自然さに若干の改善余地あり")
    out = m._reconcile_japanese_quality_consistency(ev, user_answer="コンプレッサ速度を減少します。")
    assert out.japanese_quality.level == "minor"


def test_v1713_benchmark_contract_remains_60_cases():
    data = json.loads((Path(__file__).resolve().parents[2] / "evaluation" / "quiz_eval_cases.json").read_text(encoding="utf-8"))
    assert data["grader_target"] in {"quiz-grader-v1.7.13", "quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    assert len(data["cases"]) == 60
    assert sum(c.get("tier") == "quick" for c in data["cases"]) == 12
