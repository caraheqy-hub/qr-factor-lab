# QR factor research workflow

This repository is a small, inspectable research project. Keep the Python path short and the reader-facing README in plain Chinese.

## When asked to reproduce a brokerage report

1. Search the web at that time for a recent factor report. Prefer the brokerage's own public PDF/page. Record publication date, brokerage, author, direct source URL, and access limitations. Never invent a formula from a title or summary.
2. Read the report and create one copy of `research_template.md`. Quote only brief compliant excerpts; paraphrase the methodology with page references.
3. Check that every input was available by the signal date. If data, corporate-action treatment, universe history, or exact formula is missing, label the work an approximation and list the differences before coding.
4. Implement the factor as a small named function in `research.py`, with its parameters visible in CLI output metadata. Add a timing test when the factor uses publication dates, rolling windows, or delayed execution.
5. Tune parameters only in the discovery period. Record every trial and keep the holdout period untouched until selecting a candidate. Never present the best in-sample run as a validated result.
   Compare candidates on the same dates; different warm-up lengths otherwise distort selection. If a complete-data rule removes names using future availability, disclose the resulting sample-selection bias.
6. Report IC, coverage, turnover, costs, baseline comparison, and failure modes. Link claims to the saved data snapshot and generated CSV/JSON. Do not invoke live trading APIs.

Use the installed Jupyter skill only when a notebook materially helps a reader inspect an experiment. The CLI and CSV/JSON files remain the source of reproducible results.
