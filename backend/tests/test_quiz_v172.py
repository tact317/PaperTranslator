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


def test_v172_revision_and_compact_context() -> None:
    assert m.read_root()["quiz_revision"].startswith("v1.7.")
    assert m.QUIZ_GRADER_VERSION.startswith("quiz-grader-v1.7.")


def test_rubric_generation_uses_one_normal_ollama_call(monkeypatch) -> None:
    source = "Undulators are key devices in advanced light sources."
    m._QUIZ_RUBRIC_CACHE_MEMORY.clear()
    monkeypatch.setattr(m, "_load_quiz_rubric_cache", lambda: {})
    monkeypatch.setattr(m, "_save_quiz_rubric_cache", lambda cache: None)
    monkeypatch.setattr(m, "_quiz_reference_key", lambda text: "v172-test")
    monkeypatch.setattr(m, "_quiz_glossary_prompt", lambda text: "fixed: undulator -> アンジュレータ")
    monkeypatch.setattr(m, "_repair_known_translation_terms", lambda text: text)
    monkeypatch.setattr(m, "_repair_quiz_reference_glossary", lambda src, text: text)
    monkeypatch.setattr(m, "_azure_quiz_translate", lambda text: {
        "provider": "azure", "status": "available", "translation": "アンジュレータは先進光源で重要な装置である。",
        "message": "ok", "month_usage": 10, "monthly_soft_limit": 1800000, "cached": False,
    })
    calls = []
    def chat(*args, **kwargs):
        calls.append(kwargs)
        return {"message": {"content": '{"reference_translation":"アンジュレータは先進光源で重要な装置である。","semantic_units":[{"source":"Undulators","translation":"アンジュレータ","importance":"core"},{"source":"are key devices","translation":"重要な装置である","importance":"core"},{"source":"in advanced light sources","translation":"先進光源において","importance":"support"}],"external_audit":{"status":"verified","message":"実質同義"}}'}}
    monkeypatch.setattr(m.ollama, "chat", chat)
    rubric = m._canonical_quiz_rubric(source)
    assert len(calls) == 1
    assert calls[0]["options"]["num_ctx"] == 4096
    assert rubric["external_audit"]["status"] == "verified"
    assert rubric["reference_translation"].startswith("アンジュレータ")


def test_partial_only_deductions_do_not_trigger_second_llm(monkeypatch) -> None:
    evaluation = m.TranslationEvaluation(
        verdict="correct",
        score=90,
        feedback="",
        reference_translation="基準訳",
        semantic_units=[m.SemanticUnit(
            id="u1", source="consisting of magnets", translation="磁石から構成される",
            importance="support", status="partial", note="関係が弱い",
        )],
    )
    monkeypatch.setattr(m.ollama, "chat", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("partial must not trigger verifier")))
    out = m._verify_quiz_deductions(evaluation, "source", "answer")
    assert out.semantic_units[0].status == "partial"


def test_primary_route_no_longer_calls_redundant_auditors() -> None:
    import inspect
    src = inspect.getsource(m.check_translation)
    assert "_audit_quiz_deductions_with_external_reference(" not in src
    assert "_audit_quiz_relation_units(" not in src
    assert "_verify_quiz_deductions(" not in src
    assert '"num_ctx": 4096' in src
