from __future__ import annotations

import inspect
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


def _eval(unit: m.SemanticUnit, *, level: str = "natural") -> m.TranslationEvaluation:
    return m.TranslationEvaluation(
        verdict="correct",
        score=100,
        feedback="",
        reference_translation="基準訳",
        key_points=[m.KeyPoint(source=unit.source, translation=unit.translation, status="correct")],
        semantic_units=[unit],
        japanese_quality=m.JapaneseQuality(level=level, note=""),
    )


def test_v1711_revision_and_cache_generation():
    assert m.read_root()["quiz_revision"] in {"v1.7.11-single-pass-evidence-consensus", "v1.7.12-magnitude-equivalence-rescue", "v1.7.13-consensus-severity-equivalence", "v1.7.14-japanese-surface-fluency", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-v1.7.11", "quiz-grader-v1.7.12", "quiz-grader-v1.7.13", "quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    # Rubric definition did not change; keep the expensive source-only rubric cache.
    assert m._quiz_rubric_cache_path().name == "quiz_rubric_cache_v10.json"


def test_live_quiz_path_no_longer_calls_second_qwen_deduction_verifier():
    source = inspect.getsource(m.check_translation)
    assert "_verify_quiz_deductions(" not in source
    assert 'num_predict": 900' in source
    assert "evidence_span" in source


def test_valid_evidence_still_blocks_backtranslation_false_omission():
    unit = m.SemanticUnit(
        id="u1",
        source="and allow experiments to be carried out",
        translation="実験を可能にする",
        importance="core",
        status="correct",
        evidence_span="実験が可能になる",
    )
    out = m._audit_quiz_semantic_presence_by_backtranslation(
        _eval(unit),
        backtranslation="research can be done with photons",
    )
    assert out.semantic_units[0].status == "correct"


def test_no_verified_evidence_plus_absent_concepts_can_still_mark_omission():
    unit = m.SemanticUnit(
        id="u1",
        source="than those treated later",
        translation="後で治療を受けた患者よりも",
        importance="support",
        status="correct",
        evidence_span="",
    )
    out = m._audit_quiz_semantic_presence_by_backtranslation(
        _eval(unit),
        backtranslation="Patients receiving the intervention within six hours had a lower risk of complications.",
    )
    assert out.semantic_units[0].status == "missing"


def test_compact_merge_synthesizes_severe_issue_when_model_omits_duplicate_issue():
    rubric = {
        "reference_translation": "実験を可能にする。",
        "semantic_units": [{
            "id": "u1",
            "source": "allow experiments to be carried out",
            "translation": "実験を可能にする",
            "importance": "core",
        }],
    }
    raw = {
        "unit_results": [{
            "id": "u1", "status": "missing", "evidence_span": "", "note": "実験可能化がない"
        }],
        "issues": [],
        "japanese_quality": {"level": "natural", "note": ""},
    }
    merged = m._merge_quiz_rubric_result(raw, rubric, "光子エネルギーは60 keVを超える。")
    assert merged["issues"][0]["category"] == "omission"
    assert merged["issues"][0]["source_span"] == "allow experiments to be carried out"


def test_order_of_magnitude_literalism_is_at_least_minor_japanese():
    unit = m.SemanticUnit(
        id="u1", source="by over one order of magnitude", translation="1桁以上",
        importance="detail", status="correct", evidence_span="1桁オーダーより多く",
    )
    ev = _eval(unit)
    out = m._reconcile_japanese_quality_consistency(
        ev,
        user_answer="輝度を1桁オーダーより多く増加させる。",
    )
    assert out.japanese_quality.level == "minor"


def test_v1711_benchmark_contract_remains_60_cases():
    data = json.loads((Path(__file__).resolve().parents[2] / "evaluation" / "quiz_eval_cases.json").read_text(encoding="utf-8"))
    assert data["grader_target"] in {"quiz-grader-v1.7.11", "quiz-grader-v1.7.12", "quiz-grader-v1.7.13", "quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    assert len(data["cases"]) == 60
    assert sum(c.get("tier") == "quick" for c in data["cases"]) == 12
