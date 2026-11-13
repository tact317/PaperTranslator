from __future__ import annotations

import sys
import types
from pathlib import Path

fake_ollama = types.ModuleType("ollama")
class _DummyClient:
    def __init__(self, *args, **kwargs): pass
    def list(self): return {"models": []}
fake_ollama.Client = _DummyClient
fake_ollama.chat = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("model must not run"))
sys.modules.setdefault("ollama", fake_ollama)

from backend import main as m


def test_cache_hit_vocabulary_sync_adds_glossary_terms_without_models(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(m, "QUIZ_VOCABULARY_PATH", tmp_path / "vocabulary.json")
    source = "Undulators, consisting of arrays of dipole magnets, are key devices in advanced light sources for generating high-brilliance photon beams."

    payload = m._sync_quiz_vocabulary_from_source(source, document_id="doc-1", question_id=1)

    assert payload["model_calls"] == 0
    assert payload["external_audit_calls"] == 0
    assert payload["synced_candidates"] >= 4
    pairs = {(item["source"].casefold(), item["translation"]) for item in payload["cards"]}
    assert any("undulator" in source_key and target == "アンジュレータ" for source_key, target in pairs)
    assert any("dipole magnet" in source_key and target == "ダイポール磁石" for source_key, target in pairs)
    assert any("advanced light source" in source_key and target == "先進光源" for source_key, target in pairs)


def test_vocabulary_sync_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(m, "QUIZ_VOCABULARY_PATH", tmp_path / "vocabulary.json")
    source = "An undulator uses dipole magnets."
    first = m._sync_quiz_vocabulary_from_source(source, document_id="doc-1", question_id=1)
    second = m._sync_quiz_vocabulary_from_source(source, document_id="doc-1", question_id=1)
    assert second["count"] == first["count"]


def test_frontend_local_cache_hit_still_syncs_vocabulary() -> None:
    page = (Path(__file__).resolve().parents[2] / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    assert "/api/quiz/vocabulary/sync" in page
    assert "await syncVocabularyFromSource(current.sourceText, current.id)" in page
    assert "LLM/Azureは呼び出さず、単語カードだけ同期しました" in page
    assert "LLM/APIは呼び出していません" not in page


def test_quiz_revision_is_not_older_than_v151() -> None:
    assert m.read_root()["quiz_revision"] in {"phase99-numeric-integrity-v1", "v1.5.1-cache-vocabulary-sync", "v1.6.0-layered-vocabulary", "v1.7.0-vocabulary-index", "v1.7.1-glossary-policy", "v1.7.2-fast-audited-grading", "v1.7.3-paraphrase-safe-cache", "v1.7.4-anchor-omission-guard", "v1.7.5-predicate-argument-guard", "v1.7.6-importance-japanese-quality", "v1.7.7-japanese-consistency-eval-harness", "v1.7.8-quantitative-integrity-fluency-guard", "v1.7.9-semantic-evidence-hardening", "v1.7.10-evidence-span-verified-omission", "v1.7.11-single-pass-evidence-consensus", "v1.7.12-magnitude-equivalence-rescue", "v1.7.13-consensus-severity-equivalence", "v1.7.14-japanese-surface-fluency", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
