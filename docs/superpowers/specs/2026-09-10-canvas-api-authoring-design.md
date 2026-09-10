# A build-side Canvas API authoring skill

Date: 2026-09-10
Status: approved in discussion (owner: make it the source of truth for how Canvas works;
the guard's current capability must not constrain it and must be looked up live)

## Purpose

Give the build side one authoritative reference for how Canvas works, organised by what an
instructor wants to do, so that new Level 2 functions, new guard verbs, and the faculty-facing
skill text are written from Canvas's documented behaviour rather than from guesses.

Today that knowledge is scattered. The faculty skills correctly point at the Canvas
documentation and deliberately carry no recipes, so nothing in this repo records what the
documentation actually says. Every task that needs a parameter name, an object shape, or the
order of a multi-step Canvas flow re-derives it, and a wrong guess costs a refused write or a
`WRITE STATUS UNCERTAIN`.

The skill also has to answer the design question that comes before any of that: should this
Canvas task be a passthrough call, a `run-plan` sequence, a named Level 2 function, or a new
guard verb.

## Decisions

- **Build side only.** It lives at `.claude/skills/canvas-api-authoring/`, so this session and
  its subagents discover it automatically. `install.sh` is not touched, nothing is installed to
  a faculty machine, and the IT review surface is unchanged.

- **Canvas first; the guard does not constrain the content.** The references describe what
  Canvas documents, in full, whether or not any local tool can reach it today. Canvas's
  three-step file upload flow is documented completely even though the guard sends JSON bodies
  only and pins the host, which means it cannot perform steps one and two. That is a fact about
  the guard, not about Canvas, and it does not belong in a Canvas reference.

- **Current tooling capability is looked up live, never written down.** A sentence about what
  the guard can do goes stale the moment the guard changes. `SKILL.md` instructs the reader to
  get the capability surface from CodeGraph and from the programs' own `--help`, and gives the
  queries that work. Verified 2026-09-10: one `codegraph_context` call for the guard's CLI
  surface returns both `VERBS` at `canvas_api_guard.py:1159` and `OPERATIONS` at
  `level2/canvas_api_operations.py:838`.

- **CodeGraph answers the surface, not behaviour.** Verb and operation tables are symbols and
  CodeGraph returns them accurately. Whether a write is refused, or whether a body may be
  multipart, is branching logic and is not a symbol. For behaviour the source is `--help` and
  the test suite. `SKILL.md` states this boundary so the reader does not over-trust either tool.

- **Organised by instructor intent, not by endpoint.** A reader arrives with "build a quiz and
  publish it", not with "GET /api/v1/courses/:id/quizzes". Each reference follows the arc of a
  real task and names the endpoints as it goes.

- **Parameters verbatim, sources recorded.** Every parameter name is copied from the official
  documentation rather than paraphrased or recalled. `sources.md` records each documentation URL
  and the date it was fetched.

- **Nothing is live-tested against Canvas.** There is no token in this environment. Every claim
  is documentation-grounded, and the skill says so on its face. Where a claim instead comes from
  this repo's own tested code, it is labelled as repo-verified so a reader can always tell
  proven from read.

- **Classic Quizzes covered; New Quizzes stubbed.** New Quizzes is a separate service with a
  different API, and nothing here has ever been pointed at it. A short section says exactly that,
  so an agent does not guess its way into it, without claiming coverage the skill does not have.

## Layout

```
.claude/skills/canvas-api-authoring/
  SKILL.md
  sources.md
  references/
    passthrough-or-function.md
    fundamentals.md
    assignments.md
    quizzes.md
    rubrics-and-grades.md
    submissions-and-files.md
    course-content.md
```

`SKILL.md` is short. It states what the skill is and what it is not, routes from intent to a
reference, and carries the one section on looking up current tooling capability live. It routes
to `passthrough-or-function.md` first, because that decision comes before any Canvas detail.

Its frontmatter is `name: canvas-api-authoring` with a description that fires on build-side
work: writing or changing a Canvas function, a guard verb, or Canvas skill text, and answering
what Canvas supports for an instructor task. It is not a runtime skill and must not read as one.

The six Canvas references are independent of each other and of
`passthrough-or-function.md`. They can be authored in parallel by separate agents, each given
its own documentation pages and the same section template.

## `passthrough-or-function.md`

A decision procedure with four outcomes, grounded in the precedent already in the repo.

1. **A documented passthrough call.** The default, and the bar the other three must clear.
   Level 2's README already states that an operation which would be a single documented API call
   is deliberately absent.
2. **A passthrough sequence through `run-plan`.** The option most often missed. Since `run-plan`
   shipped, an ordered series of writes is no longer by itself a reason to build a function.
   Ordered writes with no computation between them are a plan: approved once, each step still
   its own audited and read-back write.
3. **A named Level 2 function.** Earned when a result must be computed or joined across reads
   before any write is proposed, when verification needs evidence a single read-back cannot
   reach, when structured input must be validated against live Canvas state first, when a safety
   invariant must hold across the whole job, or when local files and their provenance are
   involved.
4. **A new guard verb.** Right only when what is needed is a property at the credential
   boundary. `draft` is there because the guard itself must hold the authority to refuse;
   `download-submission-file` is there because it must use the token without exposing it.

It also states what does not justify a function: a different projection of the same read is
`--fields`, a complete collection is `--all-pages`, and ergonomics alone is never enough.

The eight operations that exist on 2026-09-10 appear as worked precedent, each with the reason
it earned its place, dated as history. The live list is looked up, not read from here.

## References

| File | Covers |
| --- | --- |
| `fundamentals.md` | How Canvas models a course: pagination and `Link` headers, `include[]`, ids and SIS ids, the published and `workflow_state` model, date and override semantics, HTML fields, and the fact that quizzes and graded discussions are assignments underneath |
| `assignments.md` | The create, configure and publish arc: submission types, assignment groups, overrides, dates, peer review, posting policy |
| `quizzes.md` | The Classic quiz arc end to end: question types and their answer shapes, question groups and randomisation, how `points_possible` is computed rather than set, accommodations, publishing, attempts, statistics and reports. New Quizzes stubbed |
| `rubrics-and-grades.md` | Rubric shape, association and purpose, assessments, grading a submission, grading standards, final grades and the final grade override |
| `submissions-and-files.md` | Finding and filtering submissions, attachments and attempts, download, the full three-step upload flow and the URL alternative, folders |
| `course-content.md` | Announcements, modules and module items, pages, and setting a course home page |

Each reference carries, per section: the task in the instructor's terms, the endpoints and
verbatim parameters with their documentation URL, Canvas's behaviour around the call, and the
traps that break an obvious guess.

## Testing

Skills are prose and have no unit tests, so verification is by construction and by two checks
that can actually be run.

- **Endpoint check.** Every endpoint path named in a reference must appear in the Canvas
  documentation page cited for that section. Checked against the fetched pages during authoring.
- **No local command lines.** No file in the skill contains a `/usr/local/libexec/` command
  line. That is what keeps the references from going stale, and it is confirmed by grep. Naming a
  verb or a flag in prose is not a command line and is permitted, but only in
  `passthrough-or-function.md`, where the four outcomes cannot be described without naming them.
  The six Canvas references name no local verb or flag at all. The existing tests that check
  faculty skill text against the real argument parser therefore have nothing to police here, and
  are unaffected.
- **Each trap cites its evidence**, either the documentation line or the repo test that
  establishes it.

## Out of scope

- Any change to `canvas_api_guard.py`, `level2/canvas_api_operations.py`, `install.sh`, the
  Codex rules, or either faculty skill.
- Installing anything to a faculty machine, and any change to the release.
- New Quizzes coverage beyond the stub.
- A scraper that regenerates the references from the documentation. Scraped output is not
  reviewable, and the curated judgement is the value here.
- Live verification against a Canvas instance.
