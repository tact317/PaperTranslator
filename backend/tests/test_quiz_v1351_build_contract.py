from pathlib import Path


def _page_source() -> str:
    return (Path(__file__).resolve().parents[2] / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")


def test_grading_report_props_are_threaded_through_quiz_panel() -> None:
    page = _page_source()
    assert "gradingReportStatus={gradingReportStatus}" in page
    assert "onReportGrading={reportBadGrading}" in page
    assert "onOpenGradingReports={openGradingReportFolder}" in page
    quiz_start = page.index("function QuizPanel({")
    feedback_start = page.index("function FeedbackCard({")
    quiz_block = page[quiz_start:feedback_start]
    assert "gradingReportStatus," in quiz_block
    assert "onReportGrading," in quiz_block
    assert "onOpenGradingReports," in quiz_block
    assert 'gradingReportStatus: "idle" | "saving" | "saved" | "error"' in quiz_block
    assert "onReportGrading: () => void" in quiz_block
    assert "onOpenGradingReports: () => void" in quiz_block


def test_feedback_card_receives_grading_report_props_from_quiz_panel_scope() -> None:
    page = _page_source()
    quiz_start = page.index("function QuizPanel({")
    feedback_start = page.index("function FeedbackCard({")
    quiz_block = page[quiz_start:feedback_start]
    assert "<FeedbackCard" in quiz_block
    assert "gradingReportStatus={gradingReportStatus}" in quiz_block
    assert "onReportGrading={onReportGrading}" in quiz_block
    assert "onOpenGradingReports={onOpenGradingReports}" in quiz_block
