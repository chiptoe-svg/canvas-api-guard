# Passthrough, plan, function, or guard verb

## The question

Every Canvas task a developer is asked to support is one of four shapes: a single documented
API call, an ordered sequence of writes with nothing to compute between them, a result that has
to be computed, validated, or proven beyond what one read-back reaches, or a property that can
only be held at the credential boundary itself. Picking a shape heavier than the task needs
produces a program nobody can review as easily as the endpoint it wraps. Picking one lighter than
the task needs produces a program that writes to Canvas without the validation, the ordering
guarantee, or the boundary control the task actually required. Decide the shape before writing
anything.

## Start here: is it one documented call?

The default is the documented passthrough, and the bar for leaving it is high. `level2/README.md`
states the standing rule directly: "An operation that would be a single documented API call is
deliberately absent: API Only does those, with the Canvas documentation, and does them as well."
Every Canvas function in this repo exists because it does more than issue one call.

Two things feel like reasons to leave passthrough and are not:

- **A different projection of the same read is `--fields`.** Wanting only certain fields back, or
  a nested field by dotted path, is not computation. It is the flag.
- **A complete collection is `--all-pages`.** Wanting every page rather than one is not
  computation either. It is the flag.

If the task reduces to "call this endpoint, but shaped differently," it is still a passthrough
call.

## Four outcomes

| Outcome | Choose it when |
| --- | --- |
| A documented passthrough call | one endpoint does it |
| A plan through `run-plan` | ordered writes with no computation between them |
| A named Level 2 function | a result must be computed, validated or proven beyond what one read-back reaches |
| A new guard verb | what is needed is a property at the credential boundary |

### A documented passthrough call

**Test:** one endpoint, taken from the Canvas API documentation as documented, does the whole
task. No result needs to be computed from more than one response before a write is proposed, and
nothing needs proof beyond what the guard's own read-back gives.

**Worked example:** attaching a rubric to an assignment is one documented Canvas call, so
`level2/SKILL.md`'s own "Not here" section routes it to the guard skill instead of to a function -
even though it sits right next to `create-rubric`, which is a function. Canvas documents no read
for a single rubric association, so that read-back may come back `WRITE STATUS UNCERTAIN`; the
association is still confirmed by reading the assignment's `rubric_settings` back, which is still
just a `get`.

### A plan through `run-plan`

**Test:** the task is several writes in a fixed order, and nothing needs computing between them
beyond capturing an id one step created for a later step's placeholder.

**Worked example:** building a quiz - create it, add each question, set points, publish last - is
exactly this shape. `level2/README.md` describes `run-plan` as "an ordered list of writes shown as
one dry run and approved once," where "a post may capture a field of what it created for later
steps' `{name}` placeholders." `level2/SKILL.md` shows the same shape as a plan definition: create
the quiz, capture its id, post the questions against that captured id, and publish last, because
the guard refuses a plan that publishes first.

`run-plan` changed this decision. Before it existed, "it takes several ordered writes" was itself
an argument for a named function, because nothing else in this repo could get one approval for a
sequence. It no longer is. A task is not a function candidate just because it has more than one
step. It is a function candidate only if something in the sequence has to be computed, validated,
or proven - which is the next outcome.

### A named Level 2 function

**Test:** something in the task cannot be expressed as a fixed sequence of writes, because a
result has to be computed or joined across reads before any write is proposed, or because what
the write did cannot be proven by the guard's own read-back.

Five things still earn a function, and only these:

1. A result computed or joined across reads before any write is proposed.
2. Verification that needs evidence a single read-back cannot reach.
3. Structured input that must be validated against live Canvas state first.
4. A safety invariant that must hold across the whole job, not just one step.
5. Local files and their provenance.

**Worked example:** `regrade-quiz-question` rewrites a classic quiz question's answer key, then
has to rescore every completed attempt of that question - a computation `run-plan` cannot express,
because the set of attempts to rescore and each one's new score depend on live quiz data, not on a
fixed step list. Each attempt's new score is read back at `?attempt=N`, because the assignment
submission's history lags it - evidence a plain read-back does not reach. And the dry run's
`plan_digest`, refused by `--expect-plan` if the attempts that would change are no longer exactly
those, is a safety invariant across the whole job: the set of attempts approved must be the set of
attempts actually rescored.

### A new guard verb

**Test:** the task needs a property that can only be held at the credential boundary itself -
something no amount of computation in a function sitting above the guard could produce, because
the function never holds the token.

This is the rarest outcome. Wanting convenience - a shorter call, fewer flags, one fewer script to
maintain - is never the reason for one.

`codex/skills/canvas-api-guard/SKILL.md` names the guard's two added verbs and why each one had to
be the guard itself, not a function calling it:

- **`draft`** exists because the guard itself has to hold the authority to decide whether a write
  needs approval, by reading the object first and refusing if it is published or the body would
  publish it. A function cannot grant itself that authority; only the credential-holding process
  that already enforces every other approval rule can.
- **`download-submission-file`** exists because saving a submission attachment has to use the
  token to fetch it without ever handing the token to anything above the guard. That is a property
  of who holds the bearer credential, not a computation a function could perform with the token
  already denied to it.

## Worked precedent

This is history as of 2026-09-10: the eight operations that existed on that date, and the reason
each one earned its place, per the table in `level2/README.md`. The live list does not come from
this file - run the CodeGraph query in `SKILL.md` for what exists now.

| Operation | Why it is not a single API call |
| --- | --- |
| `student-attention` | joins analytics summaries with a name lookup for only the flagged students; transparent signals, not a risk score or a roster dump |
| `prepare-submission-review` | resolves one submission, deduplicates files across attempts, downloads each through API Only, reports provenance and SHA-256 |
| `download-assignment-submissions` | the same across one assignment, up to 500 files, with file/student/attempt provenance and no submission text |
| `run-plan` | an ordered list of writes shown as one dry run and approved once; each step is its own audited, read-back write; a post may capture a field of what it created for later steps' `{name}` placeholders; stops at the first uncertain result and reports which steps ran; up to 50 steps |
| `create-rubric` | converts a flat criteria list into Canvas's indexed shape and reads every criterion back; with `--assignment-id`, the same write attaches it to that assignment for grading, proven by reading the assignment back |
| `grade-with-rubric` | reads the live rubric, rejects criterion IDs absent from it, totals the points, writes grade and assessment as one verified write, then reads each scored criterion back - a criterion is not a field of the submission object, so API Only cannot prove it |
| `bulk-grade-with-rubric` | up to 50 students, duplicates refused, each an individually audited and read-back write |
| `regrade-quiz-question` | rewrites a classic quiz question's answer key and rescores every completed attempt of that question: one write for the key, then one audited, individually read-back write per attempt, with the attempt's score read at ?attempt=N because the assignment submission's history lags it; the dry run prints a `plan_digest` and `--expect-plan DIGEST` on the `--yes` run refuses if the attempts that would change are no longer exactly those |

## What does not justify a function

- **Ergonomics.** A shorter command, fewer flags to type, or one fewer thing to explain is not
  computation, verification, validation, an invariant, or provenance. It is convenience, and
  convenience is not on the five-item list.
- **A wrapper over one call.** If the function's body is one Canvas request with some argument
  plumbing around it, it is a passthrough call wearing a name.
- **A shape a projection already gives.** Reformatting, filtering to named fields, or renaming a
  key is `--fields`, not a function.
- **A sequence a plan already gives.** An ordered list of writes with nothing to compute between
  steps, even a long one, is `run-plan`, not a function.
