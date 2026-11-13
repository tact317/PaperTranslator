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


def _ev() -> m.TranslationEvaluation:
    return m.TranslationEvaluation(
        verdict="correct", score=100, feedback="", reference_translation="基準訳",
        issues=[], key_points=[m.KeyPoint(source="s", translation="t", status="correct")],
        semantic_units=[m.SemanticUnit(id="u1", source="s", translation="t", importance="core", status="correct", evidence_span="")],
        japanese_quality=m.JapaneseQuality(level="natural", note="自然な日本語表現。"),
    )


def test_v1714_revision_and_cache_generation():
    assert m.read_root()["quiz_revision"] in {"phase99-numeric-integrity-v1", "v1.7.14-japanese-surface-fluency", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-phase99-numeric-integrity-v1", "quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    assert m._quiz_rubric_cache_path().name == "quiz_rubric_cache_v10.json"


def test_continuative_passive_change_is_minor():
    answer = "磁石位置を調節することによって位相誤差は減少され、一方ピーク磁場は測定不確かさの中で変化なしに残りました。"
    hints = m._quiz_japanese_surface_fluency_hints(answer)
    assert any("〜され、" in h for h in hints)
    out = m._reconcile_japanese_quality_consistency(_ev(), user_answer=answer)
    assert out.japanese_quality.level == "minor"


def test_direct_object_intransitive_change_is_minor():
    answer = "入口温度が80 °Cを超過するとき、コントローラはバッテリーが安全でない運転領域へ入ることを防止するためコンプレッサ速度を減少します。"
    hints = m._quiz_japanese_surface_fluency_hints(answer)
    assert any("目的語『を』" in h for h in hints)
    out = m._reconcile_japanese_quality_consistency(_ev(), user_answer=answer)
    assert out.japanese_quality.level == "minor"


def test_causative_change_form_is_not_flagged_by_new_direct_object_rule():
    answer = "コントローラはコンプレッサ速度を低下させます。"
    hints = m._quiz_japanese_surface_fluency_hints(answer)
    assert not any("目的語『を』" in h for h in hints)


def test_plain_intransitive_change_is_not_flagged_by_new_direct_object_rule():
    answer = "温度が上昇し、反応速度も増加します。"
    hints = m._quiz_japanese_surface_fluency_hints(answer)
    assert not any("目的語『を』" in h for h in hints)


def test_v1714_benchmark_contract_remains_60_cases():
    data = json.loads((Path(__file__).resolve().parents[2] / "evaluation" / "quiz_eval_cases.json").read_text(encoding="utf-8"))
    assert data["grader_target"] in {"quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    assert len(data["cases"]) == 60
    assert sum(c.get("tier") == "quick" for c in data["cases"]) == 12
