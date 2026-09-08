# Specialized Functions

Specialized Functions are additive over API Only, not another credential or HTTP client. They
supply the operations that compute across several Canvas calls or validate structured input.
An operation that would be a single documented API call is deliberately absent: API Only does
those, with the Canvas documentation, and does them as well.

## Boundary

- `canvas_api_operations.py` has no Canvas token logic and no network library.
- It calls only the installed API Only executable at `/usr/local/libexec/canvas_api_guard.py`.
- Consequently, every Canvas request uses API Only's pinned host, token isolation, and audit log.
- The guard's exit status is the contract: 0 done and verified, 2 refused or failed, 3 sent but
  unverified. A 3 propagates out of these operations unchanged and is never retried.

## Operations

| Operation | Why it is not a single API call |
| --- | --- |
| `student-attention` | joins analytics summaries with a name lookup for only the flagged students; transparent signals, not a risk score or a roster dump |
| `prepare-submission-review` | resolves one submission, deduplicates files across attempts, downloads each through API Only, reports provenance and SHA-256 |
| `download-assignment-submissions` | the same across one assignment, up to 500 files, with file/student/attempt provenance and no submission text |
| `create-rubric` | converts a flat criteria list into Canvas's indexed shape and reads every criterion back |
| `grade-with-rubric` | reads the live rubric, rejects criterion IDs absent from it, totals the points, writes grade and assessment as one verified write, then reads each scored criterion back - a criterion is not a field of the submission object, so API Only cannot prove it |
| `bulk-grade-with-rubric` | up to 50 students, duplicates refused, each an individually audited and read-back write |

The read operation is open; the two download operations and every write require the same Codex
prompt, dry-run, explicit approval, and API Only read-back evidence. See `SKILL.md` for the
operator workflow.
