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


SOURCE = (
    "Undulators, consisting of arrays of dipole magnets, are key devices in "
    "advanced light sources for generating high-brilliance photon beams."
)


def test_real_sentence_has_required_domain_glossary() -> None:
    rows = dict(m._quiz_relevant_glossary(SOURCE))
    assert rows["undulator"] == "アンジュレータ"
    assert rows["dipole magnet"] == "ダイポール磁石"
    assert rows["advanced light source"] == "先進光源"
    assert rows["high-brilliance photon beam"] == "高輝度光子ビーム"


def test_source_aware_reference_normalizes_bad_qwen_terms() -> None:
    bad = "アンジュレータは、電磁石の配列から構成され、高輝度の光子ビームを生成するために、高度な光源において重要な装置である。"
    fixed = m._quiz_apply_source_glossary_aliases(SOURCE, bad)
    assert "ダイポール磁石" in fixed
    assert "電磁石" not in fixed
    assert "先進光源" in fixed
    assert "高度な光源" not in fixed
    assert "高輝度光子ビーム" in fixed
    assert m._quiz_reference_glossary_violations(SOURCE, fixed) == []


def test_reference_generation_repairs_terms_without_extra_llm_retry(monkeypatch) -> None:
    bad = "アンジュレータは、電磁石の配列から構成され、高輝度の光子ビームを生成するために、高度な光源において重要な装置である。"
    monkeypatch.setattr(m, "_translate_batch_to_japanese", lambda batch: [{**batch[0], "translation": bad}])
    monkeypatch.setattr(m, "_repair_known_translation_terms", lambda text: text)
    def no_retry(*args, **kwargs):
        raise AssertionError("source-aware deterministic aliases should resolve this sentence")
    monkeypatch.setattr(m.ollama, "chat", no_retry)
    fixed = m._generate_quiz_reference_translation(SOURCE)
    assert "ダイポール磁石" in fixed
    assert "先進光源" in fixed
    assert "高輝度光子ビーム" in fixed


def test_semantic_unit_translation_is_source_aware() -> None:
    raw = {
        "reference_translation": "アンジュレータはダイポール磁石の配列から構成される。",
        "semantic_units": [
            {
                "source": "consisting of arrays of dipole magnets",
                "translation": "電磁石の配列から構成される",
                "importance": "support",
            }
        ],
    }
    rubric = m._normalize_quiz_rubric(raw, SOURCE)
    assert rubric["semantic_units"][0]["translation"] == "ダイポール磁石の配列から構成される"


def test_dipole_magnet_common_japanese_variants_are_accepted() -> None:
    rubric = {
        "reference_translation": "ダイポール磁石で構成される。",
        "semantic_units": [
            {"id": "u1", "source": "dipole magnets", "translation": "ダイポール磁石", "importance": "support"},
        ],
    }
    for answer in ("ダイポール磁石で構成される。", "双極磁石で構成される。", "二極磁石で構成される。"):
        merged = m._merge_quiz_rubric_result(
            {"unit_results": [{"id": "u1", "status": "wrong", "note": "grader hallucinated"}]},
            rubric,
            answer,
        )
        assert merged["semantic_units"][0]["status"] == "correct"


def test_primary_feedback_prioritizes_missing_over_partial() -> None:
    ev = m.TranslationEvaluation(
        verdict="partial",
        score=82,
        feedback="model picked the wrong priority",
        reference_translation="ref",
        semantic_units=[
            m.SemanticUnit(
                id="u1", source="consisting of arrays of dipole magnets",
                translation="ダイポール磁石の配列から構成される", importance="support", status="partial",
            ),
            m.SemanticUnit(
                id="u2", source="in advanced light sources",
                translation="先進光源において", importance="support", status="missing",
            ),
        ],
    )
    feedback = m._quiz_primary_feedback_from_units(ev)
    assert "in advanced light sources" in feedback
    assert "先進光源において" in feedback


def test_rubric_cache_key_changes_with_relevant_glossary(monkeypatch) -> None:
    monkeypatch.setattr(m, "_quiz_relevant_glossary", lambda _text: [("undulator", "アンジュレータ")])
    first = m._quiz_reference_key(SOURCE)
    monkeypatch.setattr(m, "_quiz_relevant_glossary", lambda _text: [("undulator", "別訳")])
    second = m._quiz_reference_key(SOURCE)
    assert first != second
