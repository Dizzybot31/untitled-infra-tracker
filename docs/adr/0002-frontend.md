# ADR 0002: Zero-build frontend (ES modules + CDN, no bundler)

**Status:** accepted; revisit if the codebase outgrows this

## Context
The rendering stack research confirmed globe.gl (MIT) is the strongest fit
for a Flighty-style globe. The normal way to consume it is via npm + a
bundler (Vite/webpack). This machine had no Node, no npm, no Homebrew
available at the time this was built, and installing them needed
interactive sudo. Rather than block on that, the frontend was built to need
neither.

## Decision
`web/` is plain HTML/CSS/JS. Dependencies (`globe.gl`) load as ES modules
directly from a CDN (`esm.sh`), pinned to an exact verified version. No
`package.json`, no build step, no `node_modules`. `python3 -m http.server` is
sufficient to run it.

## Consequences
- Works today with nothing installed; deploys to GitHub Pages with no build
  job.
- No TypeScript, no tree-shaking, no local dependency cache — the page fetches
  globe.gl from `esm.sh` on every visitor's first load (browser-cached after).
  Acceptable at this project's traffic; reconsider if that ever changes.
- **Migration path, if outgrown:** swap `web/` for a Vite + React (or plain
  Vite) project once Node is available in the dev environment. The canonical
  record shape in `pipeline/core/schema.py` and the static JSON contract in
  `pipeline/core/publish.py` don't change — only the rendering layer would be
  rewritten. Nothing in the pipeline needs to know or care.
- Pin exact CDN versions (see `web/js/config.js`) — an unpinned `@latest`
  import can break the page with no warning and no way to `git diff` why.
