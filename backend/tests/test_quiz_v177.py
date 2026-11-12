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


def _base_eval(*, issues=None, level="natural", note="") -> m.TranslationEvaluation:
    return m.TranslationEvaluation(
        verdict="correct",
        score=100,
        feedback="",
        reference_translation="結果は安定している。",
        issues=issues or [],
        semantic_units=[m.SemanticUnit(
            id="u1", source="The result is stable.", translation="結果は安定している。",
            importance="core", status="correct", note="",
        )],
        japanese_quality=m.JapaneseQuality(level=level, note=note),
    )


def test_v177_revision_cache_and_harness_target() -> None:
    assert m.read_root()["quiz_revision"] in {"v1.7.7-japanese-consistency-eval-harness", "v1.7.8-quantitative-integrity-fluency-guard", "v1.7.9-semantic-evidence-hardening", "v1.7.10-evidence-span-verified-omission", "v1.7.11-single-pass-evidence-consensus", "v1.7.12-magnitude-equivalence-rescue", "v1.7.13-consensus-severity-equivalence", "v1.7.14-japanese-surface-fluency", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-v1.7.7", "quiz-grader-v1.7.8", "quiz-grader-v1.7.9", "quiz-grader-v1.7.10", "quiz-grader-v1.7.11", "quiz-grader-v1.7.12", "quiz-grader-v1.7.13", "quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    assert m._quiz_rubric_cache_path().name == "quiz_rubric_cache_v10.json"


def test_explicit_fluency_wording_forces_minor_instead_of_15() -> None:
    ev = _base_eval(issues=[m.TranslationIssue(
        category="wording",
        source_span="designing a 1 m long BHTSU",
        message="『設計のための』という表現が不自然です。",
        suggestion="『設計する際の』とした方が自然です。",
    )])
    out = m._reconcile_japanese_quality_consistency(ev)
    assert out.japanese_quality.level == "minor"
    scored = m._apply_semantic_scoring(out)
    assert scored.score_breakdown.japanese == 13
    assert scored.score == 98


def test_multiple_fluency_wording_issues_force_awkward() -> None:
    ev = _base_eval(issues=[
        m.TranslationIssue(category="wording", message="語順が不自然です。", suggestion="語順を直してください。"),
        m.TranslationIssue(category="wording", message="助詞が不自然です。", suggestion="助詞を修正してください。"),
    ])
    out = m._reconcile_japanese_quality_consistency(ev)
    assert out.japanese_quality.level == "awkward"
    scored = m._apply_semantic_scoring(out)
    assert scored.score_breakdown.japanese == 10
    assert scored.score == 95


def test_explicit_direct_translation_note_cannot_remain_natural() -> None:
    ev = _base_eval(level="natural", note="意味は読めますが、全体に直訳調です。")
    out = m._reconcile_japanese_quality_consistency(ev)
    assert out.japanese_quality.level == "awkward"


def test_generic_semantic_wording_warning_does_not_lower_japanese_axis() -> None:
    ev = _base_eval(issues=[m.TranslationIssue(
        category="wording",
        message="この意味単位は概ね保持されていますが、表現または対応関係に改善余地があります。",
        suggestion="基準訳を確認してください。",
    )])
    out = m._reconcile_japanese_quality_consistency(ev)
    assert out.japanese_quality.level == "natural"
    assert m._apply_semantic_scoring(out).score_breakdown.japanese == 15


def test_negated_fluency_note_does_not_trigger_false_penalty() -> None:
    ev = _base_eval(level="natural", note="主述・助詞・修飾関係に目立つ不自然さがない。")
    out = m._reconcile_japanese_quality_consistency(ev)
    assert out.japanese_quality.level == "natural"
