# ADR 0001: Pipeline runs on the Python standard library only

**Status:** accepted

## Context
This is a solo side project. The single biggest risk to a side project isn't
a hard bug — it's the day, months from now, when the toolchain no longer
installs cleanly and the activation energy to fix it exceeds the interest in
the project.

## Decision
`pipeline/` uses nothing beyond Python 3.9+'s standard library: `urllib` for
HTTP, `sqlite3` for storage, `json`, `argparse`. No `requirements.txt`
dependency is required to run `python3 -m pipeline.run all`.

## Consequences
- Zero install step, zero version-pinning surface, works identically today
  and in three years on a stock machine.
- PDF-parsing adapters (Pink Book, Flash Report archives) will need an
  optional dependency (`pdfplumber` or similar) — that's fine as long as the
  rest of the pipeline keeps working without it. See `requirements.txt`.
- No `requests` niceties: `pipeline/core/fetch.py` hand-rolls retry, caching,
  and robots.txt handling that a library would give for free. That code is
  small and tested; the tradeoff is worth it for this project's size.
