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


def _evaluation(units, issues=None):
    return m.TranslationEvaluation(
        verdict="correct",
        score=100,
        feedback="",
        reference_translation="基準訳",
        issues=issues or [],
        key_points=[
            m.KeyPoint(
                source=u.source,
                translation=u.translation,
                status="correct" if u.status == "correct" else "warning" if u.status == "partial" else "missing",
            )
            for u in units
        ],
        semantic_units=units,
        japanese_quality=m.JapaneseQuality(level="natural", note=""),
    )


def test_v1715_revision_and_cache_generation() -> None:
    assert m.read_root()["quiz_revision"] in {"phase99-numeric-integrity-v1", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-phase99-numeric-integrity-v1", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}
    # Source-only rubric definition is unchanged; existing v10 rubric cache stays reusable.
    assert m._quiz_rubric_cache_path().name == "quiz_rubric_cache_v10.json"


def test_quantity_parser_does_not_read_turns_as_tesla() -> None:
    assert m._quiz_quantities("20 turns") == []
    anchors, witnessed = m._quiz_unit_identity_anchor_evidence(
        "and the second one consists of 20 turns",
        "第1補正コイルパックは59ターンで構成されている。",
        "The first correction coil pack consists of 59 turns.",
    )
    assert "number:20" in anchors
    assert "number:20t" not in anchors
    assert "ordinal:second" in anchors
    assert witnessed == []


def test_wrong_without_evidence_can_be_reclassified_as_whole_unit_omission() -> None:
    unit = m.SemanticUnit(
        id="u2",
        source="and the second one consists of 20 turns",
        translation="2つ目のパックは20巻からなる",
        importance="core",
        status="wrong",
        note="数量が異なる",
        evidence_span="",
    )
    ev = _evaluation([
        unit,
    ], issues=[m.TranslationIssue(
        category="mistranslation",
        source_span=unit.source,
        message="数量が異なる",
        suggestion=unit.translation,
    )])
    out = m._audit_quiz_whole_unit_omissions(
        ev,
        user_answer="第1補正コイルパックは59ターンで構成されている。",
        backtranslation="The first correction coil pack consists of 59 turns.",
    )
    assert out.semantic_units[0].status == "missing"
    assert [i.category for i in out.issues] == ["omission"]


def test_backtranslation_presence_reclassifies_unsupported_wrong_as_missing() -> None:
    unit = m.SemanticUnit(
        id="u2",
        source="guided by rails",
        translation="そのスレッジはレールで誘導されていた",
        importance="support",
        status="wrong",
        note="誘導対象が違う",
        evidence_span="",
    )
    ev = _evaluation([unit], issues=[m.TranslationIssue(
        category="mistranslation",
        source_span=unit.source,
        message="誘導対象が違う",
        suggestion=unit.translation,
    )])
    out = m._audit_quiz_semantic_presence_by_backtranslation(
        ev,
        backtranslation="The SCU assembly was equipped with a Hall probe sledge.",
    )
    assert out.semantic_units[0].status == "missing"
    assert [i.category for i in out.issues] == ["omission"]


def test_verified_reversal_evidence_is_not_reclassified_as_omission() -> None:
    unit = m.SemanticUnit(
        id="u1",
        source="are both stronger than the center field",
        translation="中心磁場より強い",
        importance="core",
        status="wrong",
        note="反対の比較",
        evidence_span="中心磁場より弱かった",
    )
    ev = _evaluation([unit])
    out = m._audit_quiz_semantic_presence_by_backtranslation(
        ev,
        backtranslation="Both off-center fields were weaker than the center field.",
    )
    assert out.semantic_units[0].status == "wrong"


def test_sibling_quantity_is_not_stolen_as_substitution_evidence() -> None:
    u1 = m.SemanticUnit(
        id="u1",
        source="the maximum operation current reaches 480 A",
        translation="最大動作電流は480Aに達する",
        importance="core",
        status="correct",
        evidence_span="最大運転電流は480 Aに達した",
    )
    u2 = m.SemanticUnit(
        id="u2",
        source="the peak magnetic field on-axis reaches 1 T at 450 A",
        translation="450Aで軸上ピーク磁場が1Tに達する",
        importance="core",
        status="partial",
        evidence_span="",
    )
    ev = _evaluation([u1, u2])
    out = m._audit_quiz_quantitative_values(
        ev,
        user_answer="最大運転電流は480 Aに達した。",
        backtranslation="The maximum operating current reached 480 A.",
    )
    assert out.semantic_units[1].status == "partial"
    assert not out.semantic_units[1].note.startswith(m._QUIZ_QUANT_AUDIT_PREFIX)


def test_respectively_reordered_values_are_material_numeric_error() -> None:
    values = m.SemanticUnit(
        id="u2",
        source="are 14.8 degrees, 6.1 degrees and 8.2 degrees",
        translation="14.8度、6.1度、8.2度です",
        importance="core",
        status="partial",
        note="順序が異なる",
        evidence_span="14.8度、8.2度、6.1度",
    )
    mapping = m.SemanticUnit(
        id="u3",
        source="for 0 A, 20 A and 30 A correction currents, respectively",
        translation="それぞれ0A、20A、30Aの補正電流に対して",
        importance="support",
        status="correct",
        evidence_span="それぞれ0 A、20 A、30 Aの場合",
    )
    ev = _evaluation([values, mapping])
    out = m._audit_quiz_quantitative_values(
        ev,
        user_answer="補正電流がそれぞれ0 A、20 A、30 Aの場合、位相RMS誤差は14.8度、8.2度、6.1度である。",
        backtranslation="For correction currents of 0 A, 20 A, and 30 A, respectively, the phase RMS errors are 14.8 degrees, 8.2 degrees, and 6.1 degrees.",
    )
    assert out.semantic_units[0].status == "wrong"
    assert out.semantic_units[0].note.startswith(m._QUIZ_QUANT_AUDIT_PREFIX)
    assert any(i.category == "mistranslation" for i in out.issues)


def test_ordered_backtranslation_rescues_false_wrong_paraphrase() -> None:
    source = "which determine the beam trajectory along the undulator"
    unit = m.SemanticUnit(
        id="u3",
        source=source,
        translation="アンジュレータ内のビーム軌道を決定する",
        importance="support",
        status="wrong",
        note="軌道決定の対象が誤っている",
        evidence_span="ビーム軌道を決める",
    )
    ev = _evaluation([unit], issues=[m.TranslationIssue(
        category="mistranslation",
        source_span=source,
        message="軌道決定の対象が誤っている",
        suggestion="アンジュレータ内の軌道を決定する",
    )])
    out = m._audit_quiz_backtranslation_semantic_rescue(
        ev,
        backtranslation="the first and second integrals of the on-axis magnetic field which determine the beam trajectory along the undulator",
    )
    assert out.semantic_units[0].status == "correct"
    assert not any(i.category == "mistranslation" for i in out.issues)


def test_ordered_backtranslation_does_not_rescue_reversal() -> None:
    source = "are both stronger than the center field"
    unit = m.SemanticUnit(
        id="u1",
        source=source,
        translation="中心磁場より強い",
        importance="core",
        status="wrong",
        note="反対の比較",
        evidence_span="中心磁場より弱かった",
    )
    ev = _evaluation([unit], issues=[m.TranslationIssue(
        category="mistranslation",
        source_span=source,
        message="反対の比較",
        suggestion="中心磁場より強い",
    )])
    out = m._audit_quiz_backtranslation_semantic_rescue(
        ev,
        backtranslation="Both off-center fields are weaker than the center field.",
    )
    assert out.semantic_units[0].status == "wrong"
    assert any(i.category == "mistranslation" for i in out.issues)


def test_ordered_backtranslation_does_not_rescue_negation_change() -> None:
    source = "the treatment increases the response"
    unit = m.SemanticUnit(
        id="u1",
        source=source,
        translation="処理は応答を増加させる",
        importance="core",
        status="wrong",
        note="否定が追加された",
        evidence_span="応答を増加させない",
    )
    ev = _evaluation([unit], issues=[m.TranslationIssue(
        category="mistranslation",
        source_span=source,
        message="否定が追加された",
        suggestion=unit.translation,
    )])
    out = m._audit_quiz_backtranslation_semantic_rescue(
        ev,
        backtranslation="the treatment does not increase the response",
    )
    assert out.semantic_units[0].status == "wrong"
