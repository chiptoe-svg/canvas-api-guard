# Specialized Functions

Specialized Functions are additive over API Only, not another credential or HTTP client. They supply
task-aware operations that are more efficient and less error-prone for recurring instructor work.

## Boundary

- `canvas_api_operations.py` has no Canvas token logic and no network library.
- It calls only the installed API Only executable at `/usr/local/libexec/canvas_api_guard.py`.
- Consequently, every Canvas request uses API Only's pinned host, token isolation, and audit log.
- Read operations are open; named writes are schema-limited and always require the same
  dry-run, explicit approval, and API Only read-back evidence as a raw API Only write.

## Current operations

| Operation | Purpose |
| --- | --- |
| `current-courses` | Compact list of active teacher courses and term data |
| `roster-count` | Distinct active-student count; never enrollment-row count |
| `find-student` | Course-scoped active-student lookup |
| `needs-grading` | Assignment queue and total needing grading |
| `course-health` | Assignment-level score and late/missing patterns |
| `assignment-performance` | Same evidence, ordered for instructional review |
| `student-attention` | Named flagged students and transparent signals, not a risk score or full roster |
| `student-trajectory` | One student's assignment and activity evidence |
| `attendance-summary` | Course activity only; not verified attendance |

## Specialized write operations

`create-rubric`, `attach-rubric`, `grade-with-rubric`, `bulk-grade-with-rubric`,
`create-assignment`, `update-assignment`, `create-or-update-page`, and
`create-announcement` accept only an allowlisted JSON definition. Rubric grading resolves the
assignment's live rubric/association and rejects criterion IDs that do not occur there. Each
bulk batch is capped at 50 students and is submitted as individually audited, read-back writes;
there is no opaque asynchronous bulk request. See `SKILL.md` for the operator workflow.

`set-assignment-dates` handles base availability, due, and close times for regular assignments
and Classic Quizzes only. It validates timestamp order against the live object and stops when
date overrides exist. `excuse-submission` and `excuse-attendance` set Canvas's submission excuse
state and verify its `excused` response; attendance excusal is deliberately limited to a Canvas
attendance assignment identified by the instructor, not an unverified external attendance tool.
