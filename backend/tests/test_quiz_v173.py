from backend import main as m


def test_v173_revision_and_grader_version() -> None:
    assert m.read_root()["quiz_revision"] in {"v1.7.3-paraphrase-safe-cache", "v1.7.4-anchor-omission-guard", "v1.7.5-predicate-argument-guard", "v1.7.6-importance-japanese-quality", "v1.7.7-japanese-consistency-eval-harness", "v1.7.8-quantitative-integrity-fluency-guard", "v1.7.9-semantic-evidence-hardening", "v1.7.10-evidence-span-verified-omission", "v1.7.11-single-pass-evidence-consensus", "v1.7.12-magnitude-equivalence-rescue", "v1.7.13-consensus-severity-equivalence", "v1.7.14-japanese-surface-fluency", "v1.7.15-blind-generalization-hardening", "v1.7.16-relation-magnitude-hardening", "v1.7.17-conservative-evidence-fluency", "v1.7.18-relative-clause-spatial-equivalence", "v1.7.19-relation-concept-normalization", "v1.7.20-relative-clause-role-preserving-rescue", "v1.7.21-glossary-anchored-reverse-typo", "v1.7.22-evidence-span-relative-rescue", "v1.7.23-japanese-surface-fluency-and-feedback", "v1.7.24-apparatus-contact-and-general-fluency", "v1.7.26-scientific-pairings-and-evidence-backed-ja-rescue", "v1.7.27-source-anchored-science-and-japanese-fluency"}
    assert m.QUIZ_GRADER_VERSION in {"quiz-grader-v1.7.3", "quiz-grader-v1.7.4", "quiz-grader-v1.7.5", "quiz-grader-v1.7.6", "quiz-grader-v1.7.7", "quiz-grader-v1.7.8", "quiz-grader-v1.7.9", "quiz-grader-v1.7.10", "quiz-grader-v1.7.11", "quiz-grader-v1.7.12", "quiz-grader-v1.7.13", "quiz-grader-v1.7.14", "quiz-grader-v1.7.15", "quiz-grader-v1.7.16", "quiz-grader-v1.7.17", "quiz-grader-v1.7.18", "quiz-grader-v1.7.19", "quiz-grader-v1.7.20", "quiz-grader-v1.7.21", "quiz-grader-v1.7.22", "quiz-grader-v1.7.23", "quiz-grader-v1.7.24", "quiz-grader-v1.7.26", "quiz-grader-v1.7.27"}


def test_backtranslation_is_optional_when_azure_off(monkeypatch) -> None:
    monkeypatch.setattr(m, "_quiz_audit_config", lambda: {
        "enabled": False, "key": "", "region": "",
        "endpoint": "https://api.cognitive.microsofttranslator.com",
        "monthly_soft_limit": 1800000,
    })
    monkeypatch.setattr(m, "_quiz_audit_usage", lambda: {"month": "2099-01", "characters": 0})
    result = m._azure_quiz_backtranslate_user_answer("自然な言い換え")
    assert result["status"] == "local_only"
    assert result["translation"] == ""
