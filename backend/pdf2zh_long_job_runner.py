from __future__ import annotations

"""Run PDFMathTranslate/BabelDOC in-process without enabling BabelDOC debug output.

pdf2zh-next 2.9.0 normally executes BabelDOC in a child process guarded by a
30-minute AsyncCallback inactivity timeout.  The CLI's --debug flag bypasses that
child process, but it also sets BabelDOC's debug=True and contaminates the output
PDF with layout/debug overlays.  PaperTranslator needs the former behavior without
the latter.

This runner intentionally reuses pdf2zh-next's own ConfigManager and
create_babeldoc_config(), then calls BabelDOC's async_translate() directly while
forcing config.debug=False.  That removes the watchdog without changing the PDF
rendering mode.
"""

import asyncio
import logging
import sys
import traceback
from pathlib import Path

import babeldoc.assets.assets
from babeldoc.format.pdf.high_level import async_translate as babeldoc_translate
from pdf2zh_next.config import ConfigManager
from pdf2zh_next.high_level import create_babeldoc_config


def _progress_line(event: dict) -> str | None:
    overall = event.get("overall_progress")
    if isinstance(overall, (int, float)):
        return f"PAPER_TRANSLATOR_PROGRESS {float(overall):.1f}%"
    stage = event.get("stage_progress")
    if isinstance(stage, (int, float)):
        return f"PAPER_TRANSLATOR_STAGE_PROGRESS {float(stage):.1f}%"
    return None


async def _run() -> int:
    # Keep logs plain/UTF-8 friendly. Rich's legacy Windows renderer is the source
    # of the CP932 U+2022 failure observed during long jobs.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )

    settings = ConfigManager().initialize_config()

    # Match pdf2zh-next's official high-level path. SettingsModel validation is
    # not cosmetic: transform-style engines such as OpenAICompatible are
    # converted to OpenAISettings here, so get_translator() imports the real
    # translator_impl.openai module instead of a non-existent
    # translator_impl.openaicompatible module.
    settings.validate_settings()

    if getattr(settings.basic, "version", False):
        # The normal CLI owns version reporting; this runner is only for jobs.
        print("papertranslator pdf2zh in-process runner")
        return 0

    input_files = list(settings.basic.input_files)
    if not input_files:
        raise RuntimeError("No input PDF was supplied to the PDFMathTranslate runner.")

    babeldoc.assets.assets.warmup()

    for file in input_files:
        path = Path(file)
        config = create_babeldoc_config(settings, path)
        # Critical distinction from pdf2zh-next --debug: run in this process but
        # render a normal production PDF, not BabelDOC's debug overlay PDF.
        config.debug = False

        saw_finish = False
        async for event in babeldoc_translate(translation_config=config):
            if not isinstance(event, dict):
                continue
            progress = _progress_line(event)
            if progress:
                print(progress, flush=True)
            if event.get("type") == "error":
                raise RuntimeError(str(event.get("error") or "BabelDOC translation error"))
            if event.get("type") != "finish":
                continue

            saw_finish = True
            result = event.get("translate_result")
            if result is None:
                raise RuntimeError("BabelDOC finished without translate_result.")
            print(f"Original PDF: {getattr(result, 'original_pdf_path', None)}", flush=True)
            print(f"Mono PDF: {getattr(result, 'mono_pdf_path', None) or 'None'}", flush=True)
            print(f"Dual PDF: {getattr(result, 'dual_pdf_path', None) or 'None'}", flush=True)
            break

        if not saw_finish:
            raise RuntimeError(f"BabelDOC ended without a finish event for: {path}")

    return 0


def main() -> int:
    try:
        return asyncio.run(_run())
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"PAPER_TRANSLATOR_RUNNER_ERROR: {exc}", file=sys.stderr, flush=True)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
