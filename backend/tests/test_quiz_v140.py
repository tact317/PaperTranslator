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


def test_audit_config_defaults_to_local_only(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(m, "QUIZ_AUDIT_CONFIG_PATH", tmp_path / "cfg.json")
    monkeypatch.setattr(m, "QUIZ_AUDIT_USAGE_PATH", tmp_path / "usage.json")
    monkeypatch.delenv("PEPER_AZURE_TRANSLATOR_KEY", raising=False)
    cfg = m._quiz_audit_config()
    assert cfg["enabled"] is False
    result = m._azure_quiz_translate("Undulators are important devices.")
    assert result["status"] == "local_only"


def test_azure_translation_is_cached_and_counts_only_once(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(m, "QUIZ_AUDIT_CONFIG_PATH", tmp_path / "cfg.json")
    monkeypatch.setattr(m, "QUIZ_AUDIT_USAGE_PATH", tmp_path / "usage.json")
    monkeypatch.setattr(m, "QUIZ_AUDIT_CACHE_PATH", tmp_path / "cache.json")
    m._write_json_dict(m.QUIZ_AUDIT_CONFIG_PATH, {
        "enabled": True,
        "azure_key": "secret",
        "azure_region": "",
        "monthly_soft_limit": 1800000,
    })

    calls = {"count": 0}
    class _Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self):
            return json.dumps([{"translations": [{"text": "アンジュレータは重要な装置です。"}]}], ensure_ascii=False).encode()
    def fake_urlopen(request, timeout=0):
        calls["count"] += 1
        return _Response()
    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)

    source = "Undulators are important devices."
    first = m._azure_quiz_translate(source)
    second = m._azure_quiz_translate(source)
    assert first["status"] == "available"
    assert second["cached"] is True
    assert calls["count"] == 1
    assert m._quiz_audit_usage()["characters"] == len(source)


def test_soft_limit_falls_back_without_network(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(m, "QUIZ_AUDIT_CONFIG_PATH", tmp_path / "cfg.json")
    monkeypatch.setattr(m, "QUIZ_AUDIT_USAGE_PATH", tmp_path / "usage.json")
    monkeypatch.setattr(m, "QUIZ_AUDIT_CACHE_PATH", tmp_path / "cache.json")
    m._write_json_dict(m.QUIZ_AUDIT_CONFIG_PATH, {
        "enabled": True,
        "azure_key": "secret",
        "monthly_soft_limit": 10000,
    })
    m._write_json_dict(m.QUIZ_AUDIT_USAGE_PATH, {
        "month": m._quiz_audit_month_key(),
        "characters": 9999,
    })
    calls = {"count": 0}
    monkeypatch.setattr(m.urllib.request, "urlopen", lambda *a, **k: calls.__setitem__("count", calls["count"] + 1))
    result = m._azure_quiz_translate("This is longer than one character.")
    assert result["status"] == "quota_exhausted"
    assert calls["count"] == 0


def test_external_audit_can_only_relax_deductions(monkeypatch) -> None:
    evaluation = m.TranslationEvaluation(
        verdict="partial", score=80, feedback="x", reference_translation="ref",
        key_points=[m.KeyPoint(source="in advanced light sources", translation="先進光源において", status="warning")],
        semantic_units=[m.SemanticUnit(
            id="u1", source="in advanced light sources", translation="先進光源において",
            importance="support", status="partial",
        )],
    )
    monkeypatch.setattr(m.ollama, "chat", lambda **kwargs: {"message": {"content": json.dumps({
        "results": [{"id": "u1", "status": "correct", "reason": "独立訳と意味が一致"}]
    }, ensure_ascii=False)}})
    checked = m._audit_quiz_deductions_with_external_reference(
        evaluation,
        "Undulators are key devices in advanced light sources.",
        "アンジュレータは先進光源において重要な装置です。",
        {"status": "verified", "translation": "アンジュレータは先進光源における重要な装置です。"},
    )
    assert checked.semantic_units[0].status == "correct"


def test_external_disagreement_never_changes_grade(monkeypatch) -> None:
    evaluation = m.TranslationEvaluation(
        verdict="partial", score=80, feedback="x", reference_translation="ref",
        semantic_units=[m.SemanticUnit(
            id="u1", source="in advanced light sources", translation="先進光源において",
            importance="support", status="partial",
        )],
    )
    calls = {"count": 0}
    monkeypatch.setattr(m.ollama, "chat", lambda **kwargs: calls.__setitem__("count", calls["count"] + 1))
    checked = m._audit_quiz_deductions_with_external_reference(
        evaluation, "source", "answer",
        {"status": "disagreement", "translation": "別の訳"},
    )
    assert checked.semantic_units[0].status == "partial"
    assert calls["count"] == 0
