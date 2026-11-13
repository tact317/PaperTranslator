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


def _eval(unit: m.SemanticUnit) -> m.TranslationEvaluation:
    return m.TranslationEvaluation(
        verdict="correct",
        score=100,
        feedback="",
        reference_translation="基準訳",
        key_points=[m.KeyPoint(source=unit.source, translation=unit.translation, status="correct")],
        semantic_units=[unit],
        japanese_quality=m.JapaneseQuality(level="natural", note=""),
    )


def test_v1710_revision_and_cache_generation():
    assert m.read_root()["quiz_revision"] in {"phase99-numeric-integrity-v1", "v1.7.11-single-pass-evidence-consensus", "v1.7.12-magnitude-equivalence-rescue", "v1.7.13-consensus-severity-equivalence", "v1.7.14-japanese-surface-fluency", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-phase99-numeric-integrity-v1", "quiz-grader-v1.7.11", "quiz-grader-v1.7.12", "quiz-grader-v1.7.13", "quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    assert m._quiz_rubric_cache_path().name == "quiz_rubric_cache_v10.json"


def test_merge_accepts_only_verbatim_learner_evidence_span():
    rubric = {
        "reference_translation": "実験を可能にする。",
        "semantic_units": [{
            "id": "u1",
            "source": "allow experiments to be carried out",
            "translation": "実験を可能にする",
            "importance": "core",
        }],
    }
    raw = {"unit_results": [{
        "id": "u1",
        "status": "correct",
        "evidence_span": "実験が可能になる",
        "note": "意味保持",
    }]}
    merged = m._merge_quiz_rubric_result(raw, rubric, "60 keV超の光子を用いた実験が可能になる。")
    assert merged["semantic_units"][0]["evidence_span"] == "実験が可能になる"

    raw["unit_results"][0]["evidence_span"] = "実験を可能にする"  # reference-only hallucination
    merged = m._merge_quiz_rubric_result(raw, rubric, "60 keV超の光子を用いた実験が可能になる。")
    assert merged["semantic_units"][0]["evidence_span"] == ""


def test_verified_learner_evidence_blocks_lexical_backtranslation_false_omission():
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
        # Deliberately lexicalized differently from source; v1.7.9 could falsely
        # call the unit missing based on brittle content-token overlap.
        backtranslation="research can be done with these photons",
    )
    assert out.semantic_units[0].status == "correct"
    assert not any(issue.category == "omission" for issue in out.issues)


def test_no_evidence_span_still_allows_generic_omission_proposal():
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


def test_awkward_benchmark_ceiling_matches_minor_japanese_score_model():
    import json
    from pathlib import Path
    data = json.loads((Path(__file__).resolve().parents[2] / "evaluation" / "quiz_eval_cases.json").read_text(encoding="utf-8"))
    awkward = [c for c in data["cases"] if c.get("variant") == "awkward"]
    assert len(awkward) == 10
    assert all(c["expect"].get("japanese_max") == 13 for c in awkward)
    assert all(c["expect"].get("max_score") == 98 for c in awkward)
