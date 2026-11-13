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

SOURCE_UNIT = (
    "equipped with a 1 m long short-period bulk high-temperature "
    "superconductor undulator (BHTSU)"
)


def _evaluation(status: str = "correct") -> m.TranslationEvaluation:
    unit = m.SemanticUnit(
        id="u2",
        source=SOURCE_UNIT,
        translation="1メートルの短周期バルク高温超伝導アンジュレータ（BHTSU）を搭載した",
        importance="support",
        status=status,
        note="",
    )
    return m.TranslationEvaluation(
        verdict="correct",
        score=100,
        feedback="",
        reference_translation="基準訳",
        semantic_units=[unit],
        key_points=[m.KeyPoint(source=SOURCE_UNIT, translation=unit.translation, status="correct")],
    )


def test_v174_revision_and_grader_version() -> None:
    assert m.read_root()["quiz_revision"] in {"phase99-numeric-integrity-v1", "v1.7.4-anchor-omission-guard", "v1.7.5-predicate-argument-guard", "v1.7.6-importance-japanese-quality", "v1.7.7-japanese-consistency-eval-harness", "v1.7.8-quantitative-integrity-fluency-guard", "v1.7.9-semantic-evidence-hardening", "v1.7.10-evidence-span-verified-omission", "v1.7.11-single-pass-evidence-consensus", "v1.7.12-magnitude-equivalence-rescue", "v1.7.13-consensus-severity-equivalence", "v1.7.14-japanese-surface-fluency", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-phase99-numeric-integrity-v1", "quiz-grader-v1.7.4", "quiz-grader-v1.7.5", "quiz-grader-v1.7.6", "quiz-grader-v1.7.7", "quiz-grader-v1.7.8", "quiz-grader-v1.7.9", "quiz-grader-v1.7.10", "quiz-grader-v1.7.11", "quiz-grader-v1.7.12", "quiz-grader-v1.7.13", "quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}


def test_whole_technical_unit_omission_is_caught() -> None:
    user = "ポール・シェラー研究所では、スイス光源の高度化に向けて、新しい硬X線ビームラインI-TOMCATの開発が計画されています。"
    back = "At the Paul Scherrer Institute, development of a new hard x-ray beamline I-TOMCAT is planned for the upgrade of the Swiss Light Source."
    anchors, witnessed = m._quiz_unit_identity_anchor_evidence(SOURCE_UNIT, user, back)
    assert len(anchors) >= 2
    assert witnessed == []
    out = m._audit_quiz_whole_unit_omissions(_evaluation(), user, back)
    assert out.semantic_units[0].status == "missing"
    assert out.key_points[0].status == "missing"


def test_free_paraphrase_with_identity_anchors_is_not_downgraded() -> None:
    user = "ポール・シェラー研究所では、スイス光源の高度化に向けて、長さ1 mの短周期バルク高温超伝導アンジュレータ（BHTSU）を搭載する新しい硬X線ビームラインI-TOMCATの開発が計画されています。"
    back = "At the Paul Scherrer Institute, development is planned of a new hard X-ray beamline I-TOMCAT equipped with a 1 m long short-period bulk high-temperature superconducting undulator (BHTSU)."
    anchors, witnessed = m._quiz_unit_identity_anchor_evidence(SOURCE_UNIT, user, back)
    assert len(witnessed) >= 1
    out = m._audit_quiz_whole_unit_omissions(_evaluation(), user, back)
    assert out.semantic_units[0].status == "correct"


def test_one_surviving_anchor_never_forces_whole_unit_missing() -> None:
    # Deliberately incomplete answer, but BHTSU survives.  The semantic grader may
    # call this partial; the deterministic guard must not exaggerate it to missing.
    user = "BHTSUを搭載する新しい硬X線ビームラインI-TOMCATの開発が計画されています。"
    out = m._audit_quiz_whole_unit_omissions(_evaluation(), user, "")
    assert out.semantic_units[0].status == "correct"


def test_anchor_guard_does_not_touch_units_without_two_identity_anchors() -> None:
    unit = m.SemanticUnit(
        id="u1", source="has been scheduled", translation="予定されている",
        importance="core", status="correct", note="",
    )
    evaluation = m.TranslationEvaluation(
        verdict="correct", score=100, feedback="", reference_translation="基準訳",
        semantic_units=[unit],
        key_points=[m.KeyPoint(source=unit.source, translation=unit.translation, status="correct")],
    )
    out = m._audit_quiz_whole_unit_omissions(evaluation, "計画されています。", "")
    assert out.semantic_units[0].status == "correct"


def test_known_missing_bhtsu_case_cannot_remain_95() -> None:
    units = [
        m.SemanticUnit(
            id="u1", source="The development of a new hard x-ray beamline I-TOMCAT",
            translation="新しい硬X線ビームラインI-TOMCATの開発", importance="core",
            status="correct", note="",
        ),
        m.SemanticUnit(
            id="u2", source=SOURCE_UNIT,
            translation="1メートルの短周期バルク高温超伝導アンジュレータ（BHTSU）を搭載した",
            importance="support", status="correct", note="",
        ),
        m.SemanticUnit(
            id="u3", source="has been scheduled for the upgrade of the Swiss Light Source at the Paul Scherrer Institute",
            translation="ポール・シェラー研究所のスイス光源のアップグレードに伴い計画されている",
            importance="core", status="partial", note="",
        ),
    ]
    evaluation = m.TranslationEvaluation(
        verdict="correct", score=95, feedback="", reference_translation="基準訳",
        semantic_units=units,
        key_points=[
            m.KeyPoint(source=u.source, translation=u.translation, status="correct" if u.status == "correct" else "warning")
            for u in units
        ],
    )
    user = "ポール・シェラー研究所では、スイス光源の高度化に向けて、新しい硬X線ビームラインI-TOMCATの開発が計画されています。"
    back = "At the Paul Scherrer Institute, development of a new hard x-ray beamline I-TOMCAT is planned for the upgrade of the Swiss Light Source."
    guarded = m._audit_quiz_whole_unit_omissions(evaluation, user, back)
    scored = m._apply_semantic_scoring(guarded)
    assert [u.status for u in scored.semantic_units] == ["correct", "missing", "partial"]
    assert scored.score == 77
    assert scored.verdict == "partial"
