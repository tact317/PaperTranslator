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


def _eval(units, issues=None, jp="natural", jp_note=""):
    return m.TranslationEvaluation(
        verdict="correct",
        score=100,
        feedback="",
        reference_translation="基準訳",
        issues=issues or [],
        key_points=[
            m.KeyPoint(source=u.source, translation=u.translation, status="correct")
            for u in units
        ],
        semantic_units=units,
        japanese_quality=m.JapaneseQuality(level=jp, note=jp_note),
    )


def test_v179_revision_and_cache_generation():
    assert m.read_root()["quiz_revision"] in {"v1.7.9-semantic-evidence-hardening", "v1.7.10-evidence-span-verified-omission", "v1.7.11-single-pass-evidence-consensus", "v1.7.12-magnitude-equivalence-rescue", "v1.7.13-consensus-severity-equivalence", "v1.7.14-japanese-surface-fluency", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-v1.7.9", "quiz-grader-v1.7.10", "quiz-grader-v1.7.11", "quiz-grader-v1.7.12", "quiz-grader-v1.7.13", "quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    assert m._quiz_rubric_cache_path().name == "quiz_rubric_cache_v10.json"


def test_numeric_substitution_marks_core_wrong_but_uses_84_quantitative_cap():
    unit = m.SemanticUnit(
        id="u1",
        source="Although the model achieved 96% accuracy on the validation set",
        translation="モデルは検証セットで96%の精度を達成した",
        importance="core",
        status="partial",
        note="数値が違う",
    )
    audited = m._audit_quiz_quantitative_values(
        _eval([unit]),
        user_answer="モデルは検証データで69%の精度を達成した。",
        backtranslation="The model achieved 69% accuracy on the validation data.",
    )
    assert audited.semantic_units[0].status == "wrong"
    assert audited.semantic_units[0].note.startswith(m._QUIZ_QUANT_AUDIT_PREFIX)
    scored = m._apply_semantic_scoring(audited)
    assert scored.score <= 84
    assert scored.verdict in {"partial", "incorrect"}
    assert "数量" in scored.score_breakdown.cap_reason


def test_numeric_exact_value_does_not_trigger_guard_with_japanese_unit_alias():
    unit = m.SemanticUnit(
        id="u1",
        source="Cells were exposed for 24 h",
        translation="細胞を24時間曝露した",
        importance="core",
        status="correct",
    )
    audited = m._audit_quiz_quantitative_values(
        _eval([unit]),
        user_answer="細胞を24時間曝露した。",
        backtranslation="Cells were exposed for 24 hours.",
    )
    assert audited.semantic_units[0].status == "correct"


def test_backtranslation_presence_guard_catches_omitted_comparison_unit():
    unit = m.SemanticUnit(
        id="u3",
        source="than those treated later",
        translation="後で治療を受けた患者よりも",
        importance="support",
        status="correct",
    )
    audited = m._audit_quiz_semantic_presence_by_backtranslation(
        _eval([unit]),
        backtranslation="Patients receiving the intervention within six hours had a lower risk of complications.",
    )
    assert audited.semantic_units[0].status == "missing"
    assert any(i.category == "omission" for i in audited.issues)


def test_backtranslation_presence_guard_preserves_present_paraphrase():
    unit = m.SemanticUnit(
        id="u3",
        source="than those treated later",
        translation="後で治療を受けた患者よりも",
        importance="support",
        status="partial",
    )
    audited = m._audit_quiz_semantic_presence_by_backtranslation(
        _eval([unit]),
        backtranslation="compared with patients who received delayed treatment",
    )
    assert audited.semantic_units[0].status == "partial"


def test_dependency_argument_change_gets_relation_cap():
    unit = m.SemanticUnit(
        id="u1",
        source="Because the sensor response depends on flow direction",
        translation="センサー応答は流れの方向に依存するため",
        importance="core",
        status="partial",
    )
    audited = m._audit_quiz_dependency_argument_relations(
        _eval([unit]),
        backtranslation="Because the sensor response depends only on flow speed",
    )
    assert audited.semantic_units[0].status == "partial"
    assert audited.semantic_units[0].note.startswith(m._QUIZ_RELATION_AUDIT_PREFIX)
    scored = m._apply_semantic_scoring(audited)
    assert scored.score == 84
    assert "依存対象" in scored.score_breakdown.cap_reason


def test_dependency_orientation_synonym_is_not_mismatch():
    unit = m.SemanticUnit(
        id="u1",
        source="the response depends on flow direction",
        translation="応答は流れの方向に依存する",
        importance="core",
        status="correct",
    )
    audited = m._audit_quiz_dependency_argument_relations(
        _eval([unit]),
        backtranslation="the response depends on the orientation of the flow",
    )
    assert audited.semantic_units[0].status == "correct"


def test_wording_only_partial_gets_light_partial_credit():
    unit = m.SemanticUnit(
        id="u1", source="because the apparent activation energy was reduced",
        translation="見かけの活性化エネルギーが低下したため",
        importance="support", status="partial",
    )
    issue = m.TranslationIssue(
        category="wording", source_span=unit.source,
        message="模範訳と表現が異なる", suggestion=unit.translation,
    )
    out = m._apply_semantic_scoring(_eval([unit], [issue]))
    # Single support unit receives all 70 meaning points; light partial = 90%.
    assert out.score_breakdown.meaning == 63


def test_backtranslation_rescue_removes_reference_wording_preference():
    unit = m.SemanticUnit(
        id="u1",
        source="Although the model achieved 96% accuracy on the validation set",
        translation="モデルは検証セットで96%の精度を達成したが",
        importance="core",
        status="partial",
        note="検証データではなく検証セットが望ましい",
    )
    issue = m.TranslationIssue(
        category="wording", source_span="validation set",
        message="検証データではなく検証セット", suggestion="検証セット",
    )
    audited = m._audit_quiz_backtranslation_semantic_rescue(
        _eval([unit], [issue]),
        backtranslation="Although the model achieved 96% accuracy on the validation data",
    )
    assert audited.semantic_units[0].status == "correct"
    assert not audited.issues


def test_backtranslation_rescue_never_overrides_quantitative_marker():
    unit = m.SemanticUnit(
        id="u1", source="accuracy was 96%", translation="精度は96%だった",
        importance="core", status="partial",
        note=f"{m._QUIZ_QUANT_AUDIT_PREFIX} mismatch",
    )
    audited = m._audit_quiz_backtranslation_semantic_rescue(
        _eval([unit]),
        backtranslation="accuracy was 69%",
    )
    assert audited.semantic_units[0].status == "partial"


def test_ml_substantially_calque_forces_minor_japanese():
    ev = _eval([
        m.SemanticUnit(id="u1", source="performance dropped substantially", translation="性能が大幅に低下した", importance="core", status="partial")
    ])
    out = m._reconcile_japanese_quality_consistency(
        ev,
        user_answer="性能は実質的に低下しました。",
    )
    assert out.japanese_quality.level == "minor"


def test_because_comma_and_passive_change_patterns_make_awkward():
    ev = _eval([
        m.SemanticUnit(id="u1", source="because activation energy was reduced", translation="活性化エネルギーが低下したため", importance="core", status="partial")
    ])
    out = m._reconcile_japanese_quality_consistency(
        ev,
        user_answer="反応速度は増加しました、なぜなら活性化エネルギーが減少されたからです。",
    )
    assert out.japanese_quality.level == "awkward"


def test_weakly_awkward_model_label_is_relaxed_to_minor():
    ev = _eval([
        m.SemanticUnit(id="u1", source="calibration performed in one orientation", translation="ある方向での校正", importance="core", status="partial")
    ], jp="awkward", jp_note="『一方向』の表現と文末の『そのまま』が若干ぎこちない。")
    out = m._reconcile_japanese_quality_consistency(
        ev,
        user_answer="一方向で行った校正を反対方向での測定にそのまま適用することはできない。",
    )
    assert out.japanese_quality.level == "minor"
