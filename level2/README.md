# Level 2: specialized Canvas operations

Level 2 is an additive layer over Level 1, not another credential or HTTP client. It supplies
task-aware operations that are more efficient and less error-prone for recurring instructor work.

## Boundary

- `canvas_api_operations.py` has no Canvas token logic and no network library.
- It calls only the installed Level 1 executable at `/usr/local/libexec/canvas_api_guard.py`.
- Consequently, every Canvas request uses Level 1's pinned host, token isolation, and audit log.
- Current operations are read-only analytics. The rubric, content, and grade-write operations
  proposed for this layer are intentionally unavailable until their validation and read-back
  contracts are implemented and tested.

## Current operations

| Operation | Purpose |
| --- | --- |
| `course-health` | Assignment-level score and late/missing patterns |
| `assignment-performance` | Same evidence, ordered for instructional review |
| `student-attention` | Transparent submission and engagement signals, not a risk score |
| `student-trajectory` | One student's assignment and activity evidence |
| `attendance-summary` | Course activity only; not verified attendance |

## Planned specialized write operations

`create-rubric`, `attach-rubric`, `grade-with-rubric`, `bulk-grade-with-rubric`,
`create-assignment`, `update-assignment`, `create-or-update-page`, and
`create-announcement` require their own live-object validation and operation-specific read-back.
They will not be exposed until those contracts are present in source and tests.
