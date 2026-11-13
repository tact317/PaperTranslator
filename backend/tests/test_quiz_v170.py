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


def test_cross_domain_academic_vocabulary_is_extracted_without_models() -> None:
    source = (
        "The proposed method was evaluated experimentally and compared with existing approaches "
        "to determine the effect of temperature on system performance."
    )
    cards = m._quiz_vocabulary_candidates(source)
    by_source = {item["source"]: item for item in cards}

    for key in ("propose", "method", "evaluate", "compare", "determine", "effect", "temperature", "system", "performance"):
        assert key in by_source, key
    assert by_source["compare"]["surface"].casefold() == "compared"
    assert "compared with/to" in by_source


def test_cross_domain_data_model_sentence_is_extracted() -> None:
    source = "We analyze the data, validate the model, and compare the measured results with the simulation."
    cards = m._quiz_vocabulary_candidates(source)
    by_source = {item["source"] for item in cards}
    assert {"analyze", "data", "validate", "model", "compare", "result", "simulation"}.issubset(by_source)


def test_duplicate_metadata_flags_alias_and_translation_conflict(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(m, "QUIZ_VOCABULARY_PATH", tmp_path / "vocabulary.json")
    m._add_quiz_vocabulary_cards([
        m.QuizVocabularyCardInput(source="key device", translation="重要な装置", kind="phrase", origin="phrase_rule", context="a", document_id="a", question_id=1),
        m.QuizVocabularyCardInput(source="Key-device", translation="主要装置", kind="phrase", origin="phrase_rule", context="b", document_id="b", question_id=2),
        m.QuizVocabularyCardInput(source="models", translation="モデル", kind="word", origin="academic_lexicon", context="c", document_id="a", question_id=3),
        m.QuizVocabularyCardInput(source="model", translation="モデル", kind="word", origin="academic_lexicon", context="d", document_id="a", question_id=4),
    ])
    payload = m._quiz_vocabulary_payload()
    cards = {item["source"]: item for item in payload["cards"]}
    assert cards["key device"]["duplicate_status"] == "conflict"
    assert cards["Key-device"]["duplicate_status"] == "conflict"
    assert cards["models"]["duplicate_status"] == "alias"
    assert cards["model"]["duplicate_status"] == "alias"
    assert payload["duplicate_count"] == 4
    assert len(payload["duplicate_groups"]) == 2


def test_seen_count_is_unique_per_question(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(m, "QUIZ_VOCABULARY_PATH", tmp_path / "vocabulary.json")
    card = m.QuizVocabularyCardInput(source="method", translation="方法", kind="word", origin="academic_lexicon", context="A method is used.", document_id="doc", question_id=1)
    first = m._add_quiz_vocabulary_cards([card])
    second = m._add_quiz_vocabulary_cards([card])
    method = next(item for item in second["cards"] if item["source"] == "method")
    assert method["seen_count"] == 1
    assert len(method["document_ids"]) == 1

    third = m._add_quiz_vocabulary_cards([
        m.QuizVocabularyCardInput(source="method", translation="方法", kind="word", origin="academic_lexicon", context="Another method is used.", document_id="doc", question_id=2)
    ])
    method3 = next(item for item in third["cards"] if item["source"] == "method")
    assert method3["seen_count"] == 2


def test_frontend_has_vocabulary_index_search_and_duplicate_filter() -> None:
    page = (Path(__file__).resolve().parents[2] / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert 'setViewMode("list")' in page
    assert "英語・日本語・本文形・Contextを検索" in page
    assert "重複候補だけ" in page
    assert "表記重複" in page and "訳違い" in page
    assert "出現" in page and "論文" in page


def test_quiz_revision_v170() -> None:
    assert m.read_root()["quiz_revision"] in {"phase99-numeric-integrity-v1", "v1.7.0-vocabulary-index", "v1.7.1-glossary-policy", "v1.7.2-fast-audited-grading", "v1.7.3-paraphrase-safe-cache", "v1.7.4-anchor-omission-guard", "v1.7.5-predicate-argument-guard", "v1.7.6-importance-japanese-quality", "v1.7.7-japanese-consistency-eval-harness", "v1.7.8-quantitative-integrity-fluency-guard", "v1.7.9-semantic-evidence-hardening", "v1.7.10-evidence-span-verified-omission", "v1.7.11-single-pass-evidence-consensus", "v1.7.12-magnitude-equivalence-rescue", "v1.7.13-consensus-severity-equivalence", "v1.7.14-japanese-surface-fluency", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
