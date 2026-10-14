# AGENTS.md

Pure-Python repo with no compile step. The machine's install is a symlink
(`~/.local/bin/anirss` -> this repo's `./anirss`), so edits go live the moment
they land — there is nothing to package or copy.

Building on anirss (frontend, embedding it as a library, new backend
capability): follow `docs/agents/README.md`; it routes to the steps and to
`docs/agents/api-reference.md` for exact shapes.

## Build (run after every change, before calling the work done)

    python3 -m pytest tests/ test_anirss.py -q   # criterion: all green
    ruff check .                                 # criterion: no NEW findings
    ./anirss --version                           # criterion: launcher runs

`ruff check` carries a pre-existing baseline (~58 findings: import sorting,
`subprocess.run` without `check=`, …). The bar is introducing zero new ones —
diff the (file, rule) pairs against the pre-change output rather than
expecting a clean run, and never reformat untouched code to silence them.
