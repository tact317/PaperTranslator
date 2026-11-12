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


def _evaluation(*, unit_status: str = "wrong", importance: str = "support") -> m.TranslationEvaluation:
    return m.TranslationEvaluation(
        verdict="incorrect",
        score=10,
        feedback="test",
        reference_translation="アンジュレータは重要な装置である。",
        issues=[m.TranslationIssue(category="mistranslation", source_span="Undulators", message="wrong", suggestion="アンジュレータ")],
        key_points=[m.KeyPoint(source="Undulators", translation="アンジュレータ", status="missing")],
        semantic_units=[m.SemanticUnit(id="u1", source="Undulators", translation="アンジュレータ", importance=importance, status=unit_status)],
    )


def test_rubric_forces_exact_undulator_glossary() -> None:
    raw = {
        "reference_translation": "アンジュレータは重要な装置である。",
        "semantic_units": [
            {"source": "Undulators", "translation": "安定した磁気粒子", "importance": "core"},
        ],
    }
    rubric = m._normalize_quiz_rubric(raw, "Undulators are key devices.")
    assert rubric["semantic_units"][0]["translation"] == "アンジュレータ"


def test_user_exact_glossary_term_overrides_wrong_unit() -> None:
    rubric = {
        "reference_translation": "アンジュレータは重要な装置である。",
        "semantic_units": [{"id": "u1", "source": "Undulators", "translation": "アンジュレータ", "importance": "core"}],
    }
    merged = m._merge_quiz_rubric_result(
        {"unit_results": [{"id": "u1", "status": "wrong", "note": "bad"}]},
        rubric,
        "アンジュレータは重要な装置である。",
    )
    assert merged["semantic_units"][0]["status"] == "correct"
    assert "用語" in merged["semantic_units"][0]["note"]


def test_support_wrong_is_not_forced_to_59_cap() -> None:
    ev = _evaluation(unit_status="wrong", importance="support")
    scored = m._apply_semantic_scoring(ev)
    assert scored.score == 30
    assert scored.score_breakdown.cap_reason == ""


def test_core_wrong_is_59_cap() -> None:
    ev = _evaluation(unit_status="wrong", importance="core")
    scored = m._apply_semantic_scoring(ev)
    assert scored.score <= 59


def test_unconfirmed_wrong_is_demoted(monkeypatch) -> None:
    ev = _evaluation(unit_status="wrong", importance="core")
    monkeypatch.setattr(
        m.ollama,
        "chat",
        lambda **kwargs: {"message": {"content": json.dumps({"results": [{"id": "u1", "status": "partial", "reason": "equivalent"}]}, ensure_ascii=False)}},
    )
    checked = m._verify_quiz_deductions(ev, "Undulators are key devices.", "アンジュレータは重要な装置である。")
    assert checked.semantic_units[0].status == "partial"
    assert not any(issue.category == "mistranslation" for issue in checked.issues)


def test_reference_uses_production_translation_path(monkeypatch) -> None:
    monkeypatch.setattr(m, "_translate_batch_to_japanese", lambda batch: [{**batch[0], "translation": "アンジュレータは重要な装置である。"}])
    monkeypatch.setattr(m, "_repair_known_translation_terms", lambda text: text)
    assert m._generate_quiz_reference_translation("Undulators are key devices.") == "アンジュレータは重要な装置である。"



def test_real_undulator_sentence_cannot_mark_fixed_term_wrong() -> None:
    rubric = {
        "reference_translation": "ダイポール磁石の配列からなるアンジュレータは、高輝度光子ビームを生成する先進光源の重要な装置である。",
        "semantic_units": [
            {"id": "u1", "source": "Undulators", "translation": "アンジュレータ", "importance": "core"},
            {"id": "u2", "source": "consisting of arrays of dipole magnets", "translation": "ダイポール磁石の配列からなる", "importance": "core"},
            {"id": "u3", "source": "are key devices", "translation": "重要な装置である", "importance": "core"},
            {"id": "u4", "source": "in advanced light sources", "translation": "先進光源において", "importance": "support"},
            {"id": "u5", "source": "for generating high-brilliance photon beams", "translation": "高輝度光子ビームを生成するための", "importance": "support"},
        ],
    }
    raw = {
        "unit_results": [
            {"id": "u1", "status": "wrong", "note": "grader hallucinated"},
            {"id": "u2", "status": "correct", "note": ""},
            {"id": "u3", "status": "correct", "note": ""},
            {"id": "u4", "status": "correct", "note": ""},
            {"id": "u5", "status": "correct", "note": ""},
        ]
    }
    merged = m._merge_quiz_rubric_result(
        raw, rubric,
        "ダイポール磁石の配列からなるアンジュレータは、高輝度光子ビームを生成する先進光源の重要な装置である。",
    )
    assert merged["semantic_units"][0]["status"] == "correct"

def test_grading_report_writes_llm_ready_bundle(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    request = m.QuizGradingReportRequest(
        document_id="abc",
        paper_title="Paper",
        filename="paper.pdf",
        question_id=1,
        page_ref=2,
        source_text="Undulators are key devices.",
        user_answer="アンジュレータは重要な装置である。",
        evaluation={"score": 59, "referenceTranslation": "アンジュレータは重要な装置である。"},
        note="判定がおかしい",
    )
    count, folder = m._append_quiz_grading_report(request)
    assert count == 1
    assert (folder / "quiz_grading_anomalies.jsonl").exists()
    assert (folder / "quiz_grading_review.md").exists()
    bundle = (folder / "quiz_improvement_bundle.md").read_text(encoding="utf-8")
    assert "個別例への対症療法" in bundle
    assert "Undulators are key devices." in bundle
