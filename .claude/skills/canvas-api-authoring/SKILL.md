---
name: canvas-api-authoring
description: How Canvas works and what its REST API supports for the things an instructor does - quizzes, assignments, rubrics and grades, submissions and files, announcements, modules and pages. Use when writing or changing a Canvas function, a guard verb, or Canvas skill text, and when deciding whether a Canvas task should be a passthrough call, a plan, a named function, or a new guard verb.
---

# Canvas API authoring

## What this is

The build-side source of truth for how Canvas works, taken from the official Canvas REST API
documentation. It exists so that a Canvas function, a guard verb, or a line of skill text is
written from what Canvas documents rather than from a guess, because a guessed parameter name
costs a refused write or an unverifiable one.

It is not a runtime skill. Nothing here is installed, and no instructor ever reads it.

## What this is not

It is not a record of what the local tooling can do. Every capability claim about
`canvas_api_guard.py` or `canvas_api_operations.py` goes stale the moment either changes, so
none is written here. Look it up instead - see below.

Nothing here has been run against a live Canvas instance. Every claim is documentation-grounded.
A claim taken from this repo's own tested code is labelled repo-verified where it appears.

## Look up current capability, never recall it

Two sources, and they answer different questions.

**What exists** is a symbol, and CodeGraph returns it in one call. Ask `codegraph_context` for
`canvas_api_guard CLI verbs, subcommands and flags: what operations the guard exposes`. It
returns the guard's `VERBS` table and Level 2's `OPERATIONS` table together.

**How it behaves** is not a symbol. Whether a write is refused, whether a body may be multipart,
what a read-back can prove - all of that is branching logic. CodeGraph will not tell you. Read
`--help` on the programs (`canvas_api_guard.py`, `level2/canvas_api_operations.py`), then the
tests that name the behaviour.

Do not trust either tool past its boundary, and do not answer a capability question from memory.

## Where to look

| If you are | Read |
| --- | --- |
| deciding passthrough, plan, function, or guard verb | `references/passthrough-or-function.md` |
| working out how Canvas models a course at all | `references/fundamentals.md` |
| creating, configuring or publishing an assignment | `references/assignments.md` |
| building, publishing or scoring a quiz | `references/quizzes.md` |
| building a rubric, grading with it, or touching final grades | `references/rubrics-and-grades.md` |
| finding, downloading or uploading student work and files | `references/submissions-and-files.md` |
| posting an announcement, or building modules, pages or a home page | `references/course-content.md` |

Start with `references/passthrough-or-function.md`. The shape of the thing you are building
decides more than any endpoint detail does.

## Provenance

`sources.md` records every documentation page these references draw on, the date it was fetched,
and the endpoints and parameter names taken from it. `tools/canvas-docs-check.py` re-fetches
those pages and reports anything that no longer appears. Run it by hand when you want to know
whether Canvas has moved. It changes nothing.

A clean run proves every recorded claim still appears on its page. It does not prove a list is
complete or exclusive. A reference that names 21 values checked clean has confirmed 21 values
still appear, not that no 22nd exists.
