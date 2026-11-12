from __future__ import annotations

import sys
import types
from pathlib import Path

fake_ollama = types.ModuleType("ollama")
class _DummyClient:
    def __init__(self, *args, **kwargs): pass
    def list(self): return {"models": []}
fake_ollama.Client = _DummyClient
fake_ollama.chat = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Vocabulary extraction must not call a model"))
sys.modules.setdefault("ollama", fake_ollama)

from backend import main as m


SOURCE = (
    "Undulators, consisting of arrays of dipole magnets, are key devices in advanced light sources "
    "for generating high-brilliance photon beams."
)


def test_layered_vocabulary_extracts_term_word_phrase_and_pattern_without_models() -> None:
    cards = m._quiz_vocabulary_candidates(SOURCE)
    by_key = {(item["kind"], item["source"]): item for item in cards}

    assert ("term", "undulator") in by_key
    assert by_key[("term", "undulator")]["translation"] == "アンジュレータ"
    assert by_key[("term", "undulator")]["surface"].casefold() == "undulators"

    assert ("word", "consist") in by_key
    assert by_key[("word", "consist")]["surface"].casefold() == "consisting"
    assert ("word", "generate") in by_key
    assert by_key[("word", "generate")]["surface"].casefold() == "generating"

    assert ("phrase", "key device") in by_key
    assert by_key[("phrase", "key device")]["translation"] == "重要な装置"
    assert ("phrase", "consisting of arrays of dipole magnet") in by_key
    assert by_key[("phrase", "consisting of arrays of dipole magnet")]["translation"] == "ダイポール磁石の配列から構成される"
    assert ("phrase", "in advanced light source") in by_key
    assert by_key[("phrase", "in advanced light source")]["translation"] == "先進光源において"
    assert ("phrase", "for generating high-brilliance photon beam") in by_key

    assert ("pattern", "consist of") in by_key
    assert ("pattern", "for + V-ing") in by_key
    assert all(item["context"] == SOURCE for item in cards)


def test_vocabulary_sync_persists_richer_metadata_and_keeps_progress(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(m, "QUIZ_VOCABULARY_PATH", tmp_path / "vocabulary.json")
    first = m._sync_quiz_vocabulary_from_source(SOURCE, document_id="doc-a", question_id=1)
    assert first["model_calls"] == 0
    assert first["external_audit_calls"] == 0
    assert first["kind_counts"]["term"] >= 4
    assert first["kind_counts"]["word"] >= 3
    assert first["kind_counts"]["phrase"] >= 1
    assert first["kind_counts"]["pattern"] >= 2

    consist = next(card for card in first["cards"] if card["source"] == "consist")
    assert consist["kind"] == "word"
    assert "consisting" in [item.casefold() for item in consist["surface_forms"]]
    assert SOURCE in consist["contexts"]

    m._review_quiz_vocabulary_card(
        m.QuizVocabularyReviewRequest(card_id=consist["card_id"], direction="en-ja", known=False)
    )
    second = m._sync_quiz_vocabulary_from_source(SOURCE, document_id="doc-a", question_id=1)
    consist2 = next(card for card in second["cards"] if card["source"] == "consist")
    assert consist2["wrong_en_ja"] == 1
    assert second["count"] == first["count"]


def test_old_v15_card_is_migrated_in_payload(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(m, "QUIZ_VOCABULARY_PATH", tmp_path / "vocabulary.json")
    card_id = m._quiz_vocabulary_card_id("undulator", "アンジュレータ")
    m._write_json_dict(m.QUIZ_VOCABULARY_PATH, {
        card_id: {
            "card_id": card_id,
            "source": "undulator",
            "translation": "アンジュレータ",
            "origin": "glossary",
            "correct_en_ja": 3,
            "wrong_en_ja": 1,
            "correct_ja_en": 2,
            "wrong_ja_en": 0,
        }
    })
    payload = m._quiz_vocabulary_payload()
    card = payload["cards"][0]
    assert card["kind"] == "term"
    assert card["surface_forms"] == []
    assert card["contexts"] == []
    assert card["correct_en_ja"] == 3


def test_frontend_has_layer_filters_context_and_en_ja_reverse() -> None:
    page = (Path(__file__).resolve().parents[2] / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert 'type VocabularyKind = "term" | "word" | "phrase" | "pattern"' in page
    assert "専門用語" in page and "一般単語" in page and "フレーズ" in page and "構文" in page
    assert "本文形:" in page and "Context" in page
    assert "英 → 日" in page and "日 → 英" in page
    assert "語彙 {vocabularyCount}" in page


def test_quiz_revision_v160() -> None:
    assert m.read_root()["quiz_revision"] in {"v1.6.0-layered-vocabulary", "v1.7.0-vocabulary-index", "v1.7.1-glossary-policy", "v1.7.2-fast-audited-grading", "v1.7.3-paraphrase-safe-cache", "v1.7.4-anchor-omission-guard", "v1.7.5-predicate-argument-guard", "v1.7.6-importance-japanese-quality", "v1.7.7-japanese-consistency-eval-harness", "v1.7.8-quantitative-integrity-fluency-guard", "v1.7.9-semantic-evidence-hardening", "v1.7.10-evidence-span-verified-omission", "v1.7.11-single-pass-evidence-consensus", "v1.7.12-magnitude-equivalence-rescue", "v1.7.13-consensus-severity-equivalence", "v1.7.14-japanese-surface-fluency", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
