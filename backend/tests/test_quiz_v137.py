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


def _unit(uid, source, translation, importance, status):
    return m.SemanticUnit(
        id=uid, source=source, translation=translation,
        importance=importance, status=status,
    )


def test_modifier_units_are_not_all_core() -> None:
    raw = {
        "reference_translation": "アンジュレータはダイポール磁石の配列から構成され、先進光源で重要な装置である。",
        "semantic_units": [
            {"source": "Undulators", "translation": "アンジュレータ", "importance": "core"},
            {"source": "consisting of arrays of dipole magnets", "translation": "ダイポール磁石の配列から構成される", "importance": "core"},
            {"source": "are key devices", "translation": "重要な装置である", "importance": "core"},
            {"source": "in advanced light sources", "translation": "先進光源において", "importance": "core"},
            {"source": "for generating high-brilliance photon beams", "translation": "高輝度光子ビームを生成するため", "importance": "core"},
        ],
    }
    rubric = m._normalize_quiz_rubric(raw, SOURCE)
    assert [u["importance"] for u in rubric["semantic_units"]] == [
        "core", "support", "core", "support", "support"
    ]


def test_partial_credit_is_not_half_credit() -> None:
    ev = m.TranslationEvaluation(
        verdict="partial", score=0, feedback="x", reference_translation="ref",
        semantic_units=[
            _unit("u1", "Undulators", "アンジュレータ", "core", "correct"),
            _unit("u2", "consisting of arrays of dipole magnets", "ダイポール磁石の配列から構成", "support", "partial"),
            _unit("u3", "are key devices", "重要な装置", "core", "correct"),
        ],
    )
    scored = m._apply_semantic_scoring(ev)
    partial = next(u for u in scored.semantic_units if u.id == "u2")
    assert partial.earned_points >= round(partial.max_points * 0.75)
    assert partial.earned_points > partial.max_points / 2


def test_wording_issue_on_same_partial_unit_is_not_double_charged() -> None:
    ev = m.TranslationEvaluation(
        verdict="partial", score=0, feedback="x", reference_translation="ref",
        issues=[m.TranslationIssue(
            category="wording", source_span="are key devices",
            message="表現改善", suggestion="重要な装置である",
        )],
        semantic_units=[
            _unit("u1", "are key devices", "重要な装置である", "core", "partial"),
        ],
    )
    scored = m._apply_semantic_scoring(ev)
    assert scored.score_breakdown.japanese == 15


def test_independent_verifier_can_relax_missing_to_partial(monkeypatch) -> None:
    ev = m.TranslationEvaluation(
        verdict="partial", score=0, feedback="x", reference_translation="ref",
        issues=[m.TranslationIssue(
            category="omission", source_span="consisting of arrays of dipole magnets",
            message="欠落", suggestion="ダイポール磁石の配列から構成",
        )],
        key_points=[m.KeyPoint(
            source="consisting of arrays of dipole magnets",
            translation="ダイポール磁石の配列から構成", status="missing",
        )],
        semantic_units=[
            _unit("u1", "consisting of arrays of dipole magnets", "ダイポール磁石の配列から構成", "support", "missing"),
        ],
    )
    monkeypatch.setattr(
        m.ollama, "chat",
        lambda **kwargs: {"message": {"content": json.dumps({
            "results": [{"id": "u1", "status": "partial", "reason": "概念はあるが構成関係が弱い"}]
        }, ensure_ascii=False)}}
    )
    checked = m._verify_quiz_deductions(
        ev, SOURCE, "ダイポール磁石配列でのアンジュレータは重要な装置です。"
    )
    assert checked.semantic_units[0].status == "partial"
    assert not any(issue.category == "omission" for issue in checked.issues)


def test_verifier_never_makes_first_judgement_harsher(monkeypatch) -> None:
    ev = m.TranslationEvaluation(
        verdict="partial", score=0, feedback="x", reference_translation="ref",
        semantic_units=[
            _unit("u1", "in advanced light sources", "先進光源において", "support", "partial"),
        ],
    )
    monkeypatch.setattr(
        m.ollama, "chat",
        lambda **kwargs: {"message": {"content": json.dumps({
            "results": [{"id": "u1", "status": "wrong", "reason": "too harsh"}]
        }, ensure_ascii=False)}}
    )
    checked = m._verify_quiz_deductions(ev, SOURCE, "先進的な挿入光源として")
    assert checked.semantic_units[0].status == "partial"
