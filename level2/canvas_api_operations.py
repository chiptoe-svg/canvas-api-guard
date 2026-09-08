#!/usr/bin/env python3
"""Specialized Canvas instructor operations.

This program never reads a Canvas credential and never opens a network connection.  It calls
the installed API Only guard at its fixed path, so every underlying Canvas request keeps the
same credential isolation, host pinning, and audit record.
"""

import argparse
import json
import os
import re
import stat
import subprocess
import sys

GUARD = "/usr/local/libexec/canvas_api_guard.py"
USER_AGENT = "canvas-api-operations/0.13.0"
MAX_REVIEW_ATTACHMENTS = 500


class OperationError(Exception):
    pass


class GuardUncertain(OperationError):
    """API Only sent a write and could not prove it (exit 3). It is never retried here."""


def canvas_id(value, label):
    if not value.isdigit() or int(value) < 1:
        raise OperationError("%s must be a positive Canvas numeric ID" % label)
    return value


def guard_get(path):
    """Ask API Only for one JSON response; Specialized Functions have no token or HTTP client."""
    result = subprocess.run([GUARD, "get", path, "-o", "json"], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise OperationError("API Only guard failed: %s" % result.stderr.strip())
    try:
        response = json.loads(result.stdout)
    except ValueError as err:
        raise OperationError("API Only guard did not return JSON: %s" % err)
    if not isinstance(response, dict):
        raise OperationError("API Only guard returned an unexpected response")
    return response


def guard_write(verb, path, body, phase, extra=None):
    """Delegate a reviewed write to API Only; Specialized Functions never get a token or HTTP client."""
    command = [GUARD, verb, path, "-d", json.dumps(body, sort_keys=True), "-o", "json"]
    command.extend(extra or [])
    command.append("--dry-run" if phase == "dry-run" else "--yes")
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.returncode == 3:
        raise GuardUncertain("the write was sent and API Only could not verify it; inspect "
                             "Canvas and the audit log rather than running this again: %s"
                             % result.stderr.strip())
    if result.returncode:
        raise OperationError("API Only guard failed: %s" % result.stderr.strip())
    if phase == "dry-run":
        return None
    try:
        evidence = json.loads(result.stdout)
    except ValueError as err:
        raise OperationError("API Only guard did not return write evidence: %s" % err)
    if evidence.get("verification") != "passed":
        raise OperationError("API Only guard did not prove the write")
    return evidence


def attachment_suffix(attachment):
    extension = os.path.splitext(os.path.basename(str(attachment.get("display_name") or "")))[1]
    return extension.lower() if re.fullmatch(r"\.[A-Za-z0-9]{1,16}", extension or "") else ".bin"


def guard_download_attachment(course_id, file_id, submission_id, suffix):
    """Ask API Only to retrieve one authorized attachment; this layer never opens a connection."""
    result = subprocess.run([GUARD, "download-submission-file", "--course-id", str(course_id), "--file-id", str(file_id),
                             "--submission-id", str(submission_id), "--suffix", suffix, "-o", "json"], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise OperationError("API Only guard failed: %s" % result.stderr.strip())
    try:
        response = json.loads(result.stdout)
        return response["object"]
    except (ValueError, KeyError, TypeError) as err:
        raise OperationError("API Only guard did not return attachment review evidence: %s" % err)


def definition_file(path):
    """Load one bounded, regular JSON definition. It is content, never executable code."""
    try:
        info = os.lstat(path)
    except OSError as err:
        raise OperationError("cannot read definition file: %s" % err)
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise OperationError("definition must be a regular file, not a link")
    if info.st_size > 1024 * 1024:
        raise OperationError("definition is larger than 1 MiB")
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError) as err:
        raise OperationError("definition is not valid JSON: %s" % err)
    if not isinstance(value, dict):
        raise OperationError("definition must be a JSON object")
    return value


def exact_object(value, required, optional=()):
    if not isinstance(value, dict):
        raise OperationError("definition section must be a JSON object")
    unknown = set(value) - set(required) - set(optional)
    missing = set(required) - set(value)
    if unknown:
        raise OperationError("definition has unsupported field(s): %s" % ", ".join(sorted(unknown)))
    if missing:
        raise OperationError("definition is missing required field(s): %s" % ", ".join(sorted(missing)))
    return value


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise OperationError("%s must be a non-empty string" % label)
    return value


def nonnegative(value, label):
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise OperationError("%s must be a non-negative number" % label)
    return value


def operation_phase(args):
    return "dry-run" if args.dry_run else "yes"


def write_plan(operation, args, target, body):
    """Read the course first, then show the exact specialized write before API Only sends it."""
    guard_get("courses/%s" % args.course_id)
    print(json.dumps({"operation": operation, "phase": operation_phase(args),
                      "course_id": args.course_id, "target": target, "body": body},
                     indent=2, sort_keys=True))


def criterion(value, number_key):
    definition = exact_object(value, ("description", "points", "ratings"), ("long_description",))
    text(definition["description"], "criterion description")
    nonnegative(definition["points"], "criterion points")
    if not isinstance(definition["ratings"], list) or not definition["ratings"]:
        raise OperationError("criterion ratings must be a non-empty array")
    ratings = []
    for rating in definition["ratings"]:
        rating = exact_object(rating, ("description", "points"), ("long_description",))
        text(rating["description"], "rating description")
        nonnegative(rating["points"], "rating points")
        if rating["points"] > definition["points"]:
            raise OperationError("rating points cannot exceed criterion points")
        ratings.append(rating)
    definition["ratings"] = ratings
    return definition


def rubric_body(value):
    definition = exact_object(value, ("title", "criteria"), ("free_form_criterion_comments",))
    text(definition["title"], "rubric title")
    if not isinstance(definition["criteria"], list) or not definition["criteria"]:
        raise OperationError("rubric criteria must be a non-empty array")
    criteria = {str(index): criterion(item, index) for index, item in enumerate(definition["criteria"])}
    return {"rubric": {"title": definition["title"], "criteria": criteria,
                        "free_form_criterion_comments": bool(
                            definition.get("free_form_criterion_comments", False))},
            "rubric_association": {"association_type": "Course", "purpose": "bookmark"}}


def create_rubric(args):
    body = rubric_body(definition_file(args.definition))
    body["rubric_association"]["association_id"] = int(args.course_id)
    path = "courses/%s/rubrics" % args.course_id
    write_plan("create-rubric", args, path, body)
    evidence = guard_write("post", path, body, operation_phase(args),
                           ["--created-id", "rubric.id"])
    if evidence:
        rubric_id = (evidence.get("object") or {}).get("id")
        if rubric_id is None:
            raise OperationError("Canvas created a rubric but did not return its ID for validation")
        created = guard_get("courses/%s/rubrics/%s" % (args.course_id, rubric_id)).get("object") or {}
        actual = created.get("data") or []
        expected = list(body["rubric"]["criteria"].values())
        if len(actual) != len(expected):
            raise GuardUncertain("WRITE STATUS UNCERTAIN: rubric criterion count did not read back")
        for expected_row, actual_row in zip(expected, actual):
            if (actual_row.get("description") != expected_row["description"]
                    or number(actual_row.get("points")) != expected_row["points"]):
                raise GuardUncertain("WRITE STATUS UNCERTAIN: rubric criterion did not read back")


def live_rubric(args):
    assignment = guard_get("courses/%s/assignments/%s" % (args.course_id, args.assignment_id)).get("object") or {}
    settings = assignment.get("rubric_settings") or {}
    rubric_id = settings.get("id") or assignment.get("rubric_id")
    association_id = settings.get("rubric_association_id") or assignment.get("rubric_association_id")
    if rubric_id is None or association_id is None:
        raise OperationError("assignment has no live Canvas rubric association; attach a rubric first")
    rubric = guard_get("courses/%s/rubrics/%s?include[]=associations" %
                       (args.course_id, rubric_id)).get("object") or {}
    association = next((row for row in rubric.get("associations") or []
                        if str(row.get("id")) == str(association_id)), None)
    if association is None or not association.get("use_for_grading"):
        raise OperationError("assignment's live rubric is not configured for grading")
    return assignment, rubric, str(association_id)


def grade_payload(value, rubric):
    definition = exact_object(value, ("student_id", "criteria"), ())
    student_id = canvas_id(str(definition["student_id"]), "student ID")
    criteria = definition["criteria"]
    if not isinstance(criteria, dict) or not criteria:
        raise OperationError("grade criteria must be a non-empty object keyed by live criterion ID")
    limits = {str(row.get("id")): number(row.get("points")) for row in rubric.get("data") or []}
    valid = set(limits)
    if not set(criteria).issubset(valid):
        raise OperationError("grade references a criterion not present in this assignment's live rubric")
    normalized, total = {}, 0
    for criterion_id, score in criteria.items():
        score = exact_object(score, ("points",), ("comments", "rating_id"))
        points = nonnegative(score["points"], "rubric points")
        if points > limits[str(criterion_id)]:
            raise OperationError("rubric points cannot exceed the live criterion maximum")
        normalized[str(criterion_id)] = score
        total += points
    return student_id, normalized, total


def verify_rubric_assessment(args, student_id, criteria):
    """API Only proves the grade it wrote, but a rubric criterion is not a field of the
    submission object, so it reports those leaves as null. Read the assessment back here and
    compare each criterion's points; the write has already happened, so a difference is
    uncertain, never a refusal."""
    submission = guard_get("courses/%s/assignments/%s/submissions/%s?include[]=rubric_assessment"
                           % (args.course_id, args.assignment_id, student_id)).get("object") or {}
    assessment = submission.get("rubric_assessment")
    if not isinstance(assessment, dict):
        raise GuardUncertain("WRITE STATUS UNCERTAIN: Canvas returned no rubric assessment for "
                             "student %s" % student_id)
    for criterion_id, score in criteria.items():
        scored = assessment.get(criterion_id)
        if not isinstance(scored, dict) or number(scored.get("points")) != score["points"]:
            raise GuardUncertain("WRITE STATUS UNCERTAIN: rubric criterion %s did not read back "
                                 "for student %s" % (criterion_id, student_id))


def grade_one(args, value):
    assignment, rubric, association_id = live_rubric(args)
    student_id, criteria, total = grade_payload(value, rubric)
    path = "courses/%s/assignments/%s/submissions/%s?include[]=rubric_assessment&include[]=user" % (
        args.course_id, args.assignment_id, student_id)
    guard_get(path)
    body = {"submission": {"posted_grade": total}, "rubric_assessment": criteria}
    write_plan("grade-with-rubric", args, path, body)
    guard_write("put", path, body, operation_phase(args))
    if operation_phase(args) != "dry-run":
        verify_rubric_assessment(args, student_id, criteria)
    return {"student_id": student_id, "rubric_association_id": association_id, "posted_grade": total}


def grade_with_rubric(args):
    print(json.dumps({"result": grade_one(args, definition_file(args.definition))}, indent=2, sort_keys=True))


def submission_attachments(submission):
    """Return each file once, retaining the earliest submission attempt that introduced it."""
    seen, result = set(), []

    def add(attempt, rows):
        for attachment in rows or []:
            file_id = str(attachment.get("id", "")) if isinstance(attachment, dict) else ""
            if not file_id.isdigit() or file_id in seen:
                continue
            seen.add(file_id)
            result.append({"attempt": attempt, "attachment": attachment})

    for historical in submission.get("submission_history") or []:
        if isinstance(historical, dict):
            add(historical.get("attempt"), historical.get("attachments"))
    add(submission.get("attempt"), submission.get("attachments"))
    return result


def download_submission_attachments(course_id, submission, limit):
    """Download an attachment set through API Only; this program never opens a connection."""
    submission_id = canvas_id(str(submission.get("id", "")), "submission ID")
    attachments = submission_attachments(submission)
    if len(attachments) > limit:
        raise OperationError("submission review refuses more than %s distinct attachments" % limit)
    downloaded = []
    for item in attachments:
        attachment = item["attachment"]
        evidence = guard_download_attachment(course_id, attachment["id"], submission_id, attachment_suffix(attachment))
        downloaded.append({"file_id": attachment.get("id"), "display_name": attachment.get("display_name"),
                           "content_type": attachment.get("content-type"), "attempt": item["attempt"],
                           "local_review_copy": evidence})
    return downloaded


def prepare_submission_review(args):
    """Resolve one submission and locally retrieve every distinct attachment across its attempts."""
    assignment = guard_get("courses/%s/assignments/%s" % (args.course_id, args.assignment_id)).get("object") or {}
    submission = guard_get("courses/%s/assignments/%s/submissions/%s?include[]=user&include[]=submission_history" %
                           (args.course_id, args.assignment_id, args.student_id)).get("object") or {}
    if str(submission.get("user_id")) != args.student_id:
        raise OperationError("Canvas submission did not belong to the requested student")
    attachments = submission_attachments(submission)
    if not attachments:
        raise OperationError("submission review requires at least one Canvas file attachment")
    downloaded = download_submission_attachments(args.course_id, submission, 20)
    return {"operation": "prepare-submission-review", "course_id": args.course_id,
            "assignment": {"assignment_id": assignment.get("id"), "title": assignment.get("name")},
            "student": {"student_id": submission.get("user_id"), "name": (submission.get("user") or {}).get("name")},
            "submission_id": int(canvas_id(str(submission.get("id", "")), "submission ID")), "attachments": downloaded,
            "next_step": "Review the local attachment set against the live rubric; no grade has been written."}


def download_assignment_submissions(args):
    """Retrieve every distinct attachment from every submission attempt in one assignment."""
    assignment = guard_get("courses/%s/assignments/%s" % (args.course_id, args.assignment_id)).get("object") or {}
    submissions = all_items("courses/%s/assignments/%s/submissions?include[]=submission_history&per_page=100" %
                            (args.course_id, args.assignment_id))
    planned = sum(len(submission_attachments(row)) for row in submissions if isinstance(row, dict))
    if planned > MAX_REVIEW_ATTACHMENTS:
        raise OperationError("assignment download has %s distinct attachments; the reviewed limit is %s" %
                             (planned, MAX_REVIEW_ATTACHMENTS))
    files, no_attachment = [], 0
    for submission in submissions:
        if not isinstance(submission, dict):
            continue
        if not submission_attachments(submission):
            no_attachment += 1
            continue
        for record in download_submission_attachments(args.course_id, submission, MAX_REVIEW_ATTACHMENTS):
            record.update({"student_id": submission.get("user_id"), "submission_id": submission.get("id")})
            files.append(record)
    return {"operation": "download-assignment-submissions", "course_id": args.course_id,
            "assignment": {"assignment_id": assignment.get("id"), "title": assignment.get("name")},
            "submission_count": len(submissions), "no_attachment_submission_count": no_attachment,
            "downloaded_file_count": len(files), "files": files,
            "next_step": "Files are private local review copies. Review against the live rubric; no grade has been written."}


def bulk_grade_with_rubric(args):
    definition = exact_object(definition_file(args.definition), ("grades",), ())
    if not isinstance(definition["grades"], list) or not definition["grades"]:
        raise OperationError("grades must be a non-empty array")
    if len(definition["grades"]) > 50:
        raise OperationError("bulk grading is limited to 50 students per reviewed batch")
    seen, results = set(), []
    try:
        for grade in definition["grades"]:
            student_id = str(grade.get("student_id")) if isinstance(grade, dict) else ""
            if student_id in seen:
                raise OperationError("bulk grading contains duplicate student ID %s" % student_id)
            seen.add(student_id)
            results.append(grade_one(args, grade))
    except GuardUncertain:
        raise
    except OperationError as err:
        if not results or operation_phase(args) == "dry-run":
            raise                     # nothing was written, so this is an ordinary refusal
        raise GuardUncertain("bulk grading stopped after %d of %d students; the grades already "
                             "written stand and are not retried: %s"
                             % (len(results), len(definition["grades"]), err))
    print(json.dumps({"operation": "bulk-grade-with-rubric", "phase": operation_phase(args),
                      "results": results}, indent=2, sort_keys=True))


def all_items(path):
    """Follow only the same-host pagination paths already validated by API Only."""
    items, current, seen = [], path, set()
    while current:
        if current in seen:
            raise OperationError("Canvas pagination loop at %s" % current)
        seen.add(current)
        response = guard_get(current)
        page = response.get("items")
        if not isinstance(page, list):
            raise OperationError("expected a Canvas list at %s" % current)
        items.extend(page)
        current = response.get("next")
    return items


def number(value):
    return value if isinstance(value, (int, float)) else 0


def student_identities(course_id, student_ids):
    """Retrieve names only for already-flagged students, never the whole roster."""
    identities = {}
    ids = [str(student_id) for student_id in student_ids if student_id is not None]
    for start in range(0, len(ids), 100):
        selected = ids[start:start + 100]
        path = ("courses/%s/users?enrollment_type[]=student&enrollment_state[]=active&per_page=100&" %
                course_id) + "&".join("user_ids[]=" + student_id for student_id in selected)
        for row in all_items(path):
            identities[str(row.get("id"))] = {"name": row.get("name"),
                                                "sortable_name": row.get("sortable_name")}
    return identities


def student_attention(args):
    rows = all_items("courses/%s/analytics/student_summaries?per_page=100" % args.course_id)
    candidates = []
    for row in rows:
        tardiness = row.get("tardiness_breakdown") or {}
        candidates.append({
            "student_id": row.get("id"),
            "missing": number(tardiness.get("missing")),
            "late": number(tardiness.get("late")),
            "on_time": number(tardiness.get("on_time")),
            "submission_total": number(tardiness.get("total")),
            "participations": number(row.get("participations")),
            "page_views": number(row.get("page_views")),
        })
    candidates.sort(key=lambda row: (row["missing"], row["late"],
                                      -row["participations"], -row["page_views"]), reverse=True)
    candidates = candidates[:args.limit]
    identities = student_identities(args.course_id, [row["student_id"] for row in candidates])
    for row in candidates:
        row.update(identities.get(str(row["student_id"]), {}))
    return {"operation": "student-attention", "course_id": args.course_id,
            "definition": "named, flagged active students with transparent Canvas engagement and submission signals; not a risk score or attendance record",
            "students": candidates}


# Each of these computes across several Canvas calls or validates structured input. An
# operation that is one API call belongs in API Only, with the Canvas documentation.
OPERATIONS = {"create-rubric": create_rubric, "grade-with-rubric": grade_with_rubric,
              "bulk-grade-with-rubric": bulk_grade_with_rubric,
              "prepare-submission-review": prepare_submission_review,
              "download-assignment-submissions": download_assignment_submissions,
              "student-attention": student_attention}


def parser():
    result = argparse.ArgumentParser(description="Specialized Canvas instructor operations via API Only")
    result.add_argument("--version", action="version", version=USER_AGENT)
    subs = result.add_subparsers(dest="operation", required=True)
    attention = subs.add_parser("student-attention")
    attention.add_argument("--course-id", type=lambda value: canvas_id(value, "course ID"), required=True)
    attention.add_argument("--limit", type=int, default=20)
    review = subs.add_parser("prepare-submission-review")
    review.add_argument("--course-id", type=lambda value: canvas_id(value, "course ID"), required=True)
    review.add_argument("--assignment-id", type=lambda value: canvas_id(value, "assignment ID"), required=True)
    review.add_argument("--student-id", type=lambda value: canvas_id(value, "student ID"), required=True)
    download = subs.add_parser("download-assignment-submissions")
    download.add_argument("--course-id", type=lambda value: canvas_id(value, "course ID"), required=True)
    download.add_argument("--assignment-id", type=lambda value: canvas_id(value, "assignment ID"), required=True)
    write = argparse.ArgumentParser(add_help=False)
    write.add_argument("--course-id", type=lambda value: canvas_id(value, "course ID"), required=True)
    write.add_argument("--definition", required=True, help="path to a reviewed JSON operation definition")
    phase = write.add_mutually_exclusive_group(required=True)
    phase.add_argument("--dry-run", action="store_true", help="read and show the exact write; send nothing")
    phase.add_argument("--yes", action="store_true", help="perform the previously reviewed write")
    subs.add_parser("create-rubric", parents=[write])
    for name in ("grade-with-rubric", "bulk-grade-with-rubric"):
        grade = subs.add_parser(name, parents=[write])
        grade.add_argument("--assignment-id", type=lambda value: canvas_id(value, "assignment ID"), required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if getattr(args, "limit", 1) < 1 or getattr(args, "limit", 1) > 1000:
            raise OperationError("--limit must be between 1 and 1000")
        result = OPERATIONS[args.operation](args)
        if result is not None:        # a grading operation prints its own evidence as it goes
            print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except GuardUncertain as err:      # the write was sent; only a person resolves this
        sys.stderr.write("canvas-api-operations: %s\n" % err)
        return 3
    except OperationError as err:
        sys.stderr.write("canvas-api-operations: %s\n" % err)
        return 2
    except OSError as err:             # the guard is not installed, or the filesystem refused
        sys.stderr.write("canvas-api-operations: cannot run %s: %s\n" % (GUARD, err))
        return 2


if __name__ == "__main__":
    sys.exit(main())
