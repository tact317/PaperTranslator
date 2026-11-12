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
    "A bulk high-temperature superconductor undulator was developed at the "
    "Paul Scherrer Institute for the Swiss Light Source."
)


def test_bundled_long_terms_and_facility_names_are_preferences_not_exact_locks() -> None:
    strict = dict(m._quiz_strict_glossary(SOURCE))
    preferred = dict(m._quiz_preferred_glossary(SOURCE))

    assert strict["undulator"] == "アンジュレータ"
    assert "bulk high-temperature superconductor undulator" not in strict
    assert "Paul Scherrer Institute" not in strict
    assert "Swiss Light Source" not in strict

    assert preferred["bulk high-temperature superconductor undulator"] == "バルク高温超伝導アンジュレータ（BHTSU）"
    assert preferred["Paul Scherrer Institute"] == "パウル・シェラー研究所（PSI）"
    assert preferred["Swiss Light Source"] == "スイス光源（SLS）"


def test_exact_semantic_unit_lock_is_reserved_for_explicit_fixed_term() -> None:
    assert m._quiz_exact_glossary_target("Undulators") == "アンジュレータ"
    assert m._quiz_exact_glossary_target("Paul Scherrer Institute") is None
    assert m._quiz_exact_glossary_target("Swiss Light Source") is None
    assert m._quiz_exact_glossary_target("bulk high-temperature superconductor undulator") is None


def test_reference_generation_does_not_fail_on_preferred_glossary_variants(monkeypatch) -> None:
    # This reproduces the v1.7.0 failure class: the reference preserves canonical
    # undulator terminology but uses natural/original proper names and omits bundled
    # parenthesized abbreviations. Those differences must not abort grading.
    translation = (
        "このバルク高温超伝導アンジュレータは、Paul Scherrer Instituteで"
        "Swiss Light Source向けに開発された。"
    )
    monkeypatch.setattr(
        m,
        "_translate_batch_to_japanese",
        lambda batch: [{**batch[0], "translation": translation}],
    )
    monkeypatch.setattr(m, "_repair_known_translation_terms", lambda text: text)

    def no_glossary_retry(*args, **kwargs):
        raise AssertionError("preferred glossary differences must not trigger an Ollama repair")

    monkeypatch.setattr(m.ollama, "chat", no_glossary_retry)
    assert m._generate_quiz_reference_translation(SOURCE) == translation


def test_fixed_undulator_still_blocks_a_reference_that_loses_the_term() -> None:
    violations = m._quiz_reference_glossary_violations(
        SOURCE,
        "この装置はPaul Scherrer InstituteでSwiss Light Source向けに開発された。",
    )
    assert violations == [("undulator", "アンジュレータ")]


def test_parenthesized_acronym_is_not_required_for_term_satisfaction() -> None:
    assert m._quiz_text_has_target("パウル・シェラー研究所（PSI）", "パウル・シェラー研究所で開発された")
    assert m._quiz_text_has_target("スイス光源（SLS）", "SLS向けに設計された")
