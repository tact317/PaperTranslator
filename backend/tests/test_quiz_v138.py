from __future__ import annotations

import json
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

SOURCE = (
    "Undulators, consisting of arrays of dipole magnets, are key devices in "
    "advanced light sources for generating high-brilliance photon beams."
)


def _unit(uid, source, translation, status="correct"):
    return m.SemanticUnit(
        id=uid, source=source, translation=translation,
        importance="support", status=status,
    )


def test_relation_expectations_cover_common_academic_relations() -> None:
    assert m._quiz_relation_expectation("consisting of arrays of dipole magnets")[0] == "composition"
    assert m._quiz_relation_expectation("in advanced light sources")[0] == "context"
    assert m._quiz_relation_expectation("for generating high-brilliance photon beams")[0] == "purpose"
    assert m._quiz_relation_expectation("are key devices") is None


def test_relation_audit_can_catch_false_positive_correct(monkeypatch) -> None:
    ev = m.TranslationEvaluation(
        verdict="correct", score=96, feedback="x", reference_translation="ref",
        key_points=[m.KeyPoint(
            source="in advanced light sources",
            translation="先進光源において", status="correct",
        )],
        semantic_units=[
            _unit("u1", "in advanced light sources", "先進光源において", "correct"),
        ],
    )
    monkeypatch.setattr(
        m.ollama, "chat",
        lambda **kwargs: {"message": {"content": json.dumps({
            "results": [{
                "id": "u1",
                "relation_status": "changed",
                "reason": "『先進的な挿入光源として』は場所・文脈ではなく役割を表す",
            }]
        }, ensure_ascii=False)}}
    )
    checked = m._audit_quiz_relation_units(
        ev,
        SOURCE,
        "ダイポール磁石配列でのアンジュレータは高輝度光子ビーム生成のための先進的な挿入光源として重要です。",
    )
    assert checked.semantic_units[0].status == "partial"
    assert checked.key_points[0].status == "warning"
    assert "関係監査" in checked.semantic_units[0].note


def test_relation_audit_does_not_make_existing_deduction_harsher(monkeypatch) -> None:
    ev = m.TranslationEvaluation(
        verdict="partial", score=82, feedback="x", reference_translation="ref",
        semantic_units=[
            _unit("u1", "consisting of arrays of dipole magnets", "ダイポール磁石の配列から構成される", "partial"),
        ],
    )
    calls = {"count": 0}
    def fake_chat(**kwargs):
        calls["count"] += 1
        return {"message": {"content": json.dumps({
            "results": [{"id": "u1", "relation_status": "changed", "reason": "x"}]
        })}}
    monkeypatch.setattr(m.ollama, "chat", fake_chat)
    checked = m._audit_quiz_relation_units(ev, SOURCE, "ダイポール磁石配列でのアンジュレータ")
    assert checked.semantic_units[0].status == "partial"
    assert calls["count"] == 0


def test_relation_audit_never_creates_major_error_cap(monkeypatch) -> None:
    ev = m.TranslationEvaluation(
        verdict="correct", score=100, feedback="x", reference_translation="ref",
        semantic_units=[
            _unit("u1", "in advanced light sources", "先進光源において", "correct"),
        ],
    )
    monkeypatch.setattr(
        m.ollama, "chat",
        lambda **kwargs: {"message": {"content": json.dumps({
            "results": [{"id": "u1", "relation_status": "changed", "reason": "relation changed"}]
        })}}
    )
    checked = m._audit_quiz_relation_units(ev, SOURCE, "先進光源として")
    assert checked.semantic_units[0].status == "partial"
    scored = m._apply_semantic_scoring(checked)
    assert scored.score >= 60
    assert scored.score_breakdown.cap_reason == ""
