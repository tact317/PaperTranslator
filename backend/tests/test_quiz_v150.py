from __future__ import annotations

import json
import sys
import types
from pathlib import Path

fake_ollama = types.ModuleType("ollama")
class _DummyClient:
    def __init__(self, *args, **kwargs): pass
    def list(self): return {"models": []}
fake_ollama.Client = _DummyClient
fake_ollama.chat = lambda *args, **kwargs: {"message": {"content": "{}"}}
sys.modules.setdefault("ollama", fake_ollama)

from backend import main as m


def _evaluation_dump() -> dict:
    return m.TranslationEvaluation(
        verdict="correct",
        score=95,
        feedback="ok",
        reference_translation="アンジュレータは重要な装置である。",
        semantic_units=[m.SemanticUnit(
            id="u1",
            source="Undulators",
            translation="アンジュレータ",
            importance="core",
            status="correct",
        )],
    ).model_dump()


def test_evaluation_cache_round_trip_and_answer_separation(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(m, "QUIZ_EVALUATION_CACHE_PATH", tmp_path / "eval.json")
    monkeypatch.setattr(m, "_quiz_reference_key", lambda source: "rubric-key")
    monkeypatch.setattr(m, "_quiz_audit_month_key", lambda: "2099-01")

    source = "Undulators are key devices."
    answer = "アンジュレータは重要な装置です。"
    evaluation = _evaluation_dump()
    m._store_quiz_evaluation(source, answer, evaluation)

    cached = m._get_cached_quiz_evaluation(source, answer)
    assert cached is not None
    assert cached["evaluation"]["score"] == 95
    assert m._get_cached_quiz_evaluation(source, answer + "追加") is None


def test_check_translation_returns_cached_result_without_model(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(m, "QUIZ_EVALUATION_CACHE_PATH", tmp_path / "eval.json")
    monkeypatch.setattr(m, "_quiz_reference_key", lambda source: "rubric-key")
    monkeypatch.setattr(m, "_quiz_audit_month_key", lambda: "2099-01")
    monkeypatch.setattr(m, "_quiz_vocabulary_candidates", lambda source: [{"source": "undulator", "translation": "アンジュレータ", "origin": "glossary"}])

    source = "Undulators are key devices."
    answer = "アンジュレータは重要な装置です。"
    m._store_quiz_evaluation(source, answer, _evaluation_dump())
    monkeypatch.setattr(m, "_canonical_quiz_rubric", lambda source: (_ for _ in ()).throw(AssertionError("rubric must not run")))

    result = m.check_translation(m.TranslationRequest(source_text=source, user_answer=answer))
    assert result["cache_hit"] is True
    assert result["evaluation"]["score"] == 95
    assert result["vocabulary_candidates"][0]["translation"] == "アンジュレータ"


def test_vocabulary_deduplicates_and_tracks_both_directions(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(m, "QUIZ_VOCABULARY_PATH", tmp_path / "vocab.json")
    card = m.QuizVocabularyCardInput(
        source="undulator",
        translation="アンジュレータ",
        document_id="a" * 64,
        question_id=1,
    )
    first = m._add_quiz_vocabulary_cards([card])
    second = m._add_quiz_vocabulary_cards([card])
    assert first["count"] == 1
    assert second["count"] == 1
    card_id = second["cards"][0]["card_id"]

    m._review_quiz_vocabulary_card(m.QuizVocabularyReviewRequest(card_id=card_id, direction="en-ja", known=False))
    m._review_quiz_vocabulary_card(m.QuizVocabularyReviewRequest(card_id=card_id, direction="ja-en", known=True))
    payload = m._quiz_vocabulary_payload()
    item = payload["cards"][0]
    assert item["wrong_en_ja"] == 1
    assert item["correct_ja_en"] == 1


def test_vocabulary_candidates_are_glossary_grounded() -> None:
    cards = m._quiz_vocabulary_candidates("An HTS undulator uses dipole magnets in advanced light sources.")
    pairs = {(item["source"].casefold(), item["translation"]) for item in cards}
    assert any("undulator" in source and target == "アンジュレータ" for source, target in pairs)
    assert any("dipole magnet" in source and target == "ダイポール磁石" for source, target in pairs)


def test_frontend_contains_cache_wait_ui_and_vocabulary_panel() -> None:
    page = (Path(__file__).resolve().parents[2] / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert "同じ回答の保存済み採点を再利用しました" in page
    assert "同じ英文・同じ回答なら次回は保存済み採点を即時再利用します" in page
    assert "VocabularyPanel" in page
    assert "英 → 日" in page and "日 → 英" in page
    assert "苦手だけ" in page
    assert 'version: 6' in page
