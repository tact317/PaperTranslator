# Translation profile: Scientific Japanese / Phase 10

## Responsibility split

- Model: generic language capability (`qwen2.5:14b` baseline).
- `layout_prompt_ja.txt`: translation policy only.
- `glossary_*.csv`: stable terminology only.
- generated `protected_terms.csv`: document-specific exact strings that must remain unchanged.
- PDFMathTranslate/BabelDOC: segmentation, formula placeholders, figures, layout and PDF reconstruction.
- PaperTranslator post-processing: author-line and bibliography restoration.
- PaperTranslator QA: deterministic integrity checks + bounded semantic relation audit.

Do not move domain knowledge back into an Ollama Modelfile unless an A/B test proves a benefit under the same prompt/glossary/QA pipeline.

## Invariants

The translation artifact must not alter:

- numeric values or units,
- equations and variables,
- citation / figure / table / equation numbers,
- DOI, URL, e-mail, ORCID,
- personal names,
- bibliography metadata,
- PDFMathTranslate placeholders and markup,
- logical polarity, comparisons, direction, cause/effect, or possibility/impossibility.

A generated PDF with critical or high QA findings is not considered a validated translation artifact.
