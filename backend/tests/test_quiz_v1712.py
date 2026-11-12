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


def _eval(source: str, evidence: str, status: str = "partial") -> m.TranslationEvaluation:
    unit = m.SemanticUnit(
        id="u1",
        source=source,
        translation="1桁以上",
        importance="detail",
        status=status,
        evidence_span=evidence,
        note="数量表現が不十分",
    )
    return m.TranslationEvaluation(
        verdict="correct",
        score=99,
        feedback=f"「{source}」の意味は一部保持されています。",
        reference_translation="基準訳",
        issues=[m.TranslationIssue(
            category="mistranslation",
            source_span=source,
            message="数量表現が不十分",
            suggestion="10倍以上",
        )],
        key_points=[m.KeyPoint(source=source, translation="1桁以上", status="warning")],
        semantic_units=[unit],
        japanese_quality=m.JapaneseQuality(level="natural", note=""),
    )


def test_v1712_revision_and_cache_generation():
    assert m.read_root()["quiz_revision"] in {"v1.7.12-magnitude-equivalence-rescue", "v1.7.13-consensus-severity-equivalence", "v1.7.14-japanese-surface-fluency", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-v1.7.12", "quiz-grader-v1.7.13", "quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    assert m._quiz_rubric_cache_path().name == "quiz_rubric_cache_v10.json"


def test_over_one_order_accepts_more_than_ten_times():
    ev = _eval("by over one order of magnitude", "10倍を超えて")
    out = m._audit_quiz_order_of_magnitude_equivalence(ev)
    assert out.semantic_units[0].status == "correct"
    assert not any(issue.category == "mistranslation" for issue in out.issues)
    assert out.key_points[0].status == "correct"


def test_over_one_order_accepts_one_digit_or_ten_times_forms():
    source = "by over one order of magnitude"
    assert m._quiz_japanese_matches_order_of_magnitude(source, "1桁以上向上")
    assert m._quiz_japanese_matches_order_of_magnitude(source, "10倍超に増加")
    assert m._quiz_japanese_matches_order_of_magnitude(source, "10倍を超える")


def test_two_orders_accepts_hundred_times_but_not_two_times():
    source = "by over two orders of magnitude"
    assert m._quiz_japanese_matches_order_of_magnitude(source, "100倍を超えて増加")
    assert m._quiz_japanese_matches_order_of_magnitude(source, "2桁以上増加")
    assert not m._quiz_japanese_matches_order_of_magnitude(source, "2倍を超えて増加")


def test_wrong_multiplier_is_not_rescued():
    ev = _eval("by over one order of magnitude", "約2倍")
    out = m._audit_quiz_order_of_magnitude_equivalence(ev)
    assert out.semantic_units[0].status == "partial"
    assert any(issue.category == "mistranslation" for issue in out.issues)


def test_v1712_benchmark_contract_remains_60_cases():
    data = json.loads((Path(__file__).resolve().parents[2] / "evaluation" / "quiz_eval_cases.json").read_text(encoding="utf-8"))
    assert data["grader_target"] in {"quiz-grader-v1.7.12", "quiz-grader-v1.7.13", "quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    assert len(data["cases"]) == 60
    assert sum(c.get("tier") == "quick" for c in data["cases"]) == 12
