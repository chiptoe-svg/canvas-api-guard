#!/usr/bin/env python3
"""Specialized Canvas instructor operations.

This program never reads a Canvas credential and never opens a network connection.  It calls
the installed API Only guard at its fixed path, so every underlying Canvas request keeps the
same credential isolation, host pinning, and audit record.
"""

import argparse
import datetime
import json
import os
import re
import stat
import subprocess
import sys

GUARD = "/usr/local/libexec/canvas_api_guard.py"
USER_AGENT = "canvas-api-operations/0.6.0"
MAX_REVIEW_ATTACHMENTS = 500


class OperationError(Exception):
    pass


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


ASSIGNMENT_FIELDS = ("name", "description", "points_possible", "due_at", "unlock_at",
                     "lock_at", "published", "submission_types", "grading_type",
                     "assignment_group_id", "allowed_extensions")


def assignment_body(value, require_name):
    required = ("name",) if require_name else ()
    definition = exact_object(value, required, ASSIGNMENT_FIELDS)
    if not definition:
        raise OperationError("assignment definition cannot be empty")
    if "name" in definition:
        text(definition["name"], "assignment name")
    if "points_possible" in definition:
        nonnegative(definition["points_possible"], "points_possible")
    if "submission_types" in definition and (not isinstance(definition["submission_types"], list)
                                             or not all(isinstance(item, str)
                                                        for item in definition["submission_types"])):
        raise OperationError("submission_types must be an array of strings")
    return {"assignment": definition}


DATE_FIELDS = {"available_at": "unlock_at", "due_at": "due_at", "closed_at": "lock_at"}


def iso_time(value, label):
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise OperationError("%s must be an ISO 8601 timestamp or null" % label)
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise OperationError("%s must be an ISO 8601 timestamp or null" % label)
    if parsed.tzinfo is None:
        raise OperationError("%s must include a time zone" % label)
    return parsed


def classic_or_assignment(assignment):
    """New Quizzes have a different API; this release intentionally supports Classic only."""
    if assignment.get("is_quiz_assignment") and not assignment.get("quiz_id"):
        raise OperationError("this appears to be a New Quiz; Specialized Functions currently support Classic Quizzes only")


def set_assignment_dates(args):
    definition = exact_object(definition_file(args.definition), (), tuple(DATE_FIELDS))
    if not definition:
        raise OperationError("date definition must set at least one of available_at, due_at, closed_at")
    path = "courses/%s/assignments/%s" % (args.course_id, args.assignment_id)
    assignment = guard_get(path).get("object") or {}
    classic_or_assignment(assignment)
    if assignment.get("has_overrides"):
        raise OperationError("assignment has section or student date overrides; use a dedicated override workflow rather than changing its base dates")
    merged = {target: assignment.get(target) for target in DATE_FIELDS.values()}
    body_dates = {}
    for source, target in DATE_FIELDS.items():
        if source in definition:
            iso_time(definition[source], source)
            merged[target] = definition[source]
            body_dates[target] = definition[source]
    available, due, closed = (iso_time(merged[key], key) for key in
                              ("unlock_at", "due_at", "lock_at"))
    if available and due and available > due:
        raise OperationError("available_at must be before or equal to due_at")
    if due and closed and due > closed:
        raise OperationError("due_at must be before or equal to closed_at")
    body = {"assignment": body_dates}
    write_plan("set-assignment-dates", args,
               {"path": path, "current": {key: assignment.get(key) for key in DATE_FIELDS.values()},
                "proposed": merged}, body)
    guard_write("put", path, body, operation_phase(args))


def excuse_submission(args, attendance=False):
    definition = exact_object(definition_file(args.definition), ("student_id",), ())
    student_id = canvas_id(str(definition["student_id"]), "student ID")
    path = "courses/%s/assignments/%s" % (args.course_id, args.assignment_id)
    assignment = guard_get(path).get("object") or {}
    classic_or_assignment(assignment)
    submission_path = "courses/%s/assignments/%s/submissions/%s?include[]=user" % (
        args.course_id, args.assignment_id, student_id)
    submission = guard_get(submission_path).get("object") or {}
    if str(submission.get("user_id")) != student_id:
        raise OperationError("Canvas did not return the requested student's submission")
    body = {"submission": {"excuse": True}}
    operation = "excuse-attendance" if attendance else "excuse-submission"
    write_plan(operation, args, submission_path,
               {"assignment_id": args.assignment_id, "assignment_title": assignment.get("name"),
                "student_id": student_id, "student_name": (submission.get("user") or {}).get("name"),
                "previously_excused": submission.get("excused"), "requested_excused": True})
    guard_write("put", submission_path, body, operation_phase(args))


def excuse_attendance(args):
    """Excuse the student from the instructor-identified Canvas attendance assignment."""
    excuse_submission(args, attendance=True)


def create_assignment(args):
    body = assignment_body(definition_file(args.definition), True)
    path = "courses/%s/assignments" % args.course_id
    write_plan("create-assignment", args, path, body)
    guard_write("post", path, body, operation_phase(args))


def update_assignment(args):
    body = assignment_body(definition_file(args.definition), False)
    path = "courses/%s/assignments/%s" % (args.course_id, args.assignment_id)
    guard_get(path)
    write_plan("update-assignment", args, path, body)
    guard_write("put", path, body, operation_phase(args))


PAGE_FIELDS = ("title", "body", "published", "editing_roles", "notify_of_update", "front_page")


def page_body(value):
    definition = exact_object(value, ("title", "body"), PAGE_FIELDS)
    text(definition["title"], "page title")
    if not isinstance(definition["body"], str):
        raise OperationError("page body must be a string")
    return {"wiki_page": definition}


def create_or_update_page(args):
    body = page_body(definition_file(args.definition))
    if args.page_url:
        path = "courses/%s/pages/%s" % (args.course_id, quote_query(args.page_url))
        guard_get(path)
        write_plan("create-or-update-page", args, path, body)
        guard_write("put", path, body, operation_phase(args))
        return
    path = "courses/%s/pages" % args.course_id
    write_plan("create-or-update-page", args, path, body)
    guard_write("post", path, body, operation_phase(args),
                ["--post-readback", "courses/%s/pages/{value}" % args.course_id,
                 "--post-readback-field", "url", "--post-verify-field", "wiki_page",
                 "--verify-fields", "title,body"])


ANNOUNCEMENT_FIELDS = ("title", "message", "published", "is_section_specific",
                       "specific_sections", "delayed_post_at", "require_initial_post")


def announcement_body(value):
    definition = exact_object(value, ("title", "message"), ANNOUNCEMENT_FIELDS)
    text(definition["title"], "announcement title")
    if not isinstance(definition["message"], str):
        raise OperationError("announcement message must be a string")
    definition["is_announcement"] = True
    return definition


def create_announcement(args):
    body = announcement_body(definition_file(args.definition))
    path = "courses/%s/discussion_topics" % args.course_id
    write_plan("create-announcement", args, path, body)
    guard_write("post", path, body, operation_phase(args))


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
                           ["--post-readback", "courses/%s/rubrics/{value}" % args.course_id,
                            "--post-readback-field", "rubric.id", "--post-verify-field", "rubric",
                            "--verify-fields", "title"])
    if evidence:
        rubric_id = (evidence.get("object") or {}).get("id")
        if rubric_id is None:
            raise OperationError("Canvas created a rubric but did not return its ID for validation")
        created = guard_get("courses/%s/rubrics/%s" % (args.course_id, rubric_id)).get("object") or {}
        actual = created.get("data") or []
        expected = list(body["rubric"]["criteria"].values())
        if len(actual) != len(expected):
            raise OperationError("WRITE STATUS UNCERTAIN: rubric criterion count did not read back")
        for expected_row, actual_row in zip(expected, actual):
            if (actual_row.get("description") != expected_row["description"]
                    or number(actual_row.get("points")) != expected_row["points"]):
                raise OperationError("WRITE STATUS UNCERTAIN: rubric criterion did not read back")


def attach_rubric(args):
    rubric_path = "courses/%s/rubrics/%s" % (args.course_id, args.rubric_id)
    assignment_path = "courses/%s/assignments/%s" % (args.course_id, args.assignment_id)
    guard_get(rubric_path)
    guard_get(assignment_path)
    value = exact_object(definition_file(args.definition), (), ("use_for_grading", "purpose"))
    purpose = value.get("purpose", "grading")
    if purpose not in ("grading", "bookmark"):
        raise OperationError("rubric association purpose must be grading or bookmark")
    body = {"rubric_association": {"rubric_id": int(args.rubric_id),
                                    "association_id": int(args.assignment_id),
                                    "association_type": "Assignment", "purpose": purpose,
                                    "use_for_grading": bool(value.get("use_for_grading", True))}}
    path = "courses/%s/rubric_associations" % args.course_id
    write_plan("attach-rubric", args, assignment_path, body)
    guard_write("post", path, body, operation_phase(args))


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


def grade_one(args, value):
    assignment, rubric, association_id = live_rubric(args)
    student_id, criteria, total = grade_payload(value, rubric)
    path = "courses/%s/assignments/%s/submissions/%s?include[]=rubric_assessment&include[]=user" % (
        args.course_id, args.assignment_id, student_id)
    guard_get(path)
    body = {"submission": {"posted_grade": total}, "rubric_assessment": criteria}
    write_plan("grade-with-rubric", args, path, body)
    guard_write("put", path, body, operation_phase(args), ["--verify-fields", "posted_grade"])
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
    for grade in definition["grades"]:
        student_id = str(grade.get("student_id")) if isinstance(grade, dict) else ""
        if student_id in seen:
            raise OperationError("bulk grading contains duplicate student ID %s" % student_id)
        seen.add(student_id)
        results.append(grade_one(args, grade))
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


def quote_query(value):
    """Percent-encode a query value without adding an HTTP client to Specialized Functions."""
    safe = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
    return "".join(chr(byte) if byte in safe else "%%%02X" % byte
                   for byte in value.encode("utf-8"))


def compact_course(course):
    term = course.get("term") or {}
    return {"course_id": course.get("id"), "course_code": course.get("course_code"),
            "name": course.get("name"), "term_id": term.get("id"),
            "term_name": term.get("name"), "term_start_at": term.get("start_at"),
            "term_end_at": term.get("end_at")}


def current_courses(args):
    rows = all_items("courses?enrollment_type=teacher&enrollment_state=active&state[]=available&include[]=term&per_page=100")
    return {"operation": "current-courses",
            "definition": "available courses with an active teacher enrollment",
            "courses": [compact_course(row) for row in rows]}


def roster_count(args):
    rows = all_items("courses/%s/users?enrollment_type[]=student&enrollment_state[]=active&per_page=100" %
                     args.course_id)
    student_ids = {row.get("id") for row in rows if row.get("id") is not None}
    return {"operation": "roster-count", "course_id": args.course_id,
            "definition": "distinct active students, not enrollment rows",
            "active_student_count": len(student_ids)}


def find_student(args):
    rows = all_items("courses/%s/users?enrollment_type[]=student&enrollment_state[]=active&search_term=%s&per_page=100" %
                     (args.course_id, quote_query(args.query)))
    matches = []
    for row in rows:
        matches.append({"student_id": row.get("id"), "name": row.get("name"),
                        "sortable_name": row.get("sortable_name"), "sis_user_id": row.get("sis_user_id")})
    return {"operation": "find-student", "course_id": args.course_id,
            "query": args.query, "matches": matches}


def needs_grading(args):
    rows = all_items("courses/%s/assignments?per_page=100" % args.course_id)
    assignments = []
    for row in rows:
        count = number(row.get("needs_grading_count"))
        if count:
            assignments.append({"assignment_id": row.get("id"), "title": row.get("name"),
                                "due_at": row.get("due_at"), "needs_grading_count": count})
    assignments.sort(key=lambda row: (row["needs_grading_count"], row["due_at"] or ""), reverse=True)
    return {"operation": "needs-grading", "course_id": args.course_id,
            "total_needing_grading": sum(row["needs_grading_count"] for row in assignments),
            "assignments": assignments[:args.limit]}


def assignment_rows(course_id, limit):
    rows = all_items("courses/%s/analytics/assignments?per_page=100" % course_id)
    compact = []
    for row in rows:
        tardiness = row.get("tardiness_breakdown") or {}
        compact.append({
            "assignment_id": row.get("assignment_id"),
            "title": row.get("title"),
            "due_at": row.get("due_at"),
            "points_possible": row.get("points_possible"),
            "median": row.get("median"),
            "first_quartile": row.get("first_quartile"),
            "third_quartile": row.get("third_quartile"),
            "missing_rate": number(tardiness.get("missing")),
            "late_rate": number(tardiness.get("late")),
            "on_time_rate": number(tardiness.get("on_time")),
        })
    compact.sort(key=lambda row: (row["missing_rate"], row["late_rate"]), reverse=True)
    return compact[:limit]


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


def course_health(args):
    return {"operation": "course-health", "course_id": args.course_id,
            "definition": "assignment-level submission and score patterns; not attendance",
            "assignments": assignment_rows(args.course_id, args.limit)}


def assignment_performance(args):
    return {"operation": "assignment-performance", "course_id": args.course_id,
            "definition": "assignments ordered by missing rate, then late rate",
            "assignments": assignment_rows(args.course_id, args.limit)}


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


def student_trajectory(args):
    assignments = all_items("courses/%s/analytics/users/%s/assignments?per_page=100" %
                            (args.course_id, args.student_id))
    activity = guard_get("courses/%s/analytics/users/%s/activity" %
                         (args.course_id, args.student_id)).get("object") or {}
    rows = []
    for row in assignments:
        submission = row.get("submission") or {}
        rows.append({"assignment_id": row.get("assignment_id"), "title": row.get("title"),
                     "due_at": row.get("due_at"), "points_possible": row.get("points_possible"),
                     "median": row.get("median"), "score": submission.get("score"),
                     "submitted_at": submission.get("submitted_at"),
                     "posted_at": submission.get("posted_at")})
    return {"operation": "student-trajectory", "course_id": args.course_id,
            "student_id": args.student_id,
            "definition": "student-specific assignment and Canvas activity evidence; review before outreach",
            "assignments": rows, "activity": activity}


def attendance_summary(args):
    rows = all_items("courses/%s/analytics/activity?per_page=100" % args.course_id)
    return {"operation": "attendance-summary", "course_id": args.course_id,
            "definition": "Canvas activity counts only. This is not verified attendance; use a designated Roll Call or attendance source for attendance decisions.",
            "daily_activity": rows[-args.limit:]}


OPERATIONS = {"current-courses": current_courses, "roster-count": roster_count,
              "find-student": find_student, "needs-grading": needs_grading,
              "course-health": course_health, "assignment-performance": assignment_performance,
              "student-attention": student_attention, "student-trajectory": student_trajectory,
              "attendance-summary": attendance_summary,
              "prepare-submission-review": prepare_submission_review,
              "download-assignment-submissions": download_assignment_submissions,
              "create-rubric": create_rubric, "attach-rubric": attach_rubric,
              "grade-with-rubric": grade_with_rubric,
              "bulk-grade-with-rubric": bulk_grade_with_rubric,
              "create-assignment": create_assignment, "update-assignment": update_assignment,
              "create-or-update-page": create_or_update_page,
              "create-announcement": create_announcement,
              "set-assignment-dates": set_assignment_dates,
              "excuse-submission": excuse_submission, "excuse-attendance": excuse_attendance}


def parser():
    result = argparse.ArgumentParser(description="Specialized Canvas instructor operations via API Only")
    result.add_argument("--version", action="version", version=USER_AGENT)
    subs = result.add_subparsers(dest="operation", required=True)
    subs.add_parser("current-courses")
    for name in ("roster-count", "needs-grading", "course-health", "assignment-performance",
                 "student-attention", "attendance-summary"):
        item = subs.add_parser(name)
        item.add_argument("--course-id", type=lambda value: canvas_id(value, "course ID"), required=True)
        item.add_argument("--limit", type=int, default=20)
    find = subs.add_parser("find-student")
    find.add_argument("--course-id", type=lambda value: canvas_id(value, "course ID"), required=True)
    find.add_argument("--query", required=True)
    trajectory = subs.add_parser("student-trajectory")
    trajectory.add_argument("--course-id", type=lambda value: canvas_id(value, "course ID"), required=True)
    trajectory.add_argument("--student-id", type=lambda value: canvas_id(value, "student ID"), required=True)
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
    for name in ("create-rubric", "create-assignment", "create-announcement"):
        subs.add_parser(name, parents=[write])
    attach = subs.add_parser("attach-rubric", parents=[write])
    attach.add_argument("--rubric-id", type=lambda value: canvas_id(value, "rubric ID"), required=True)
    attach.add_argument("--assignment-id", type=lambda value: canvas_id(value, "assignment ID"), required=True)
    assignment = subs.add_parser("update-assignment", parents=[write])
    assignment.add_argument("--assignment-id", type=lambda value: canvas_id(value, "assignment ID"), required=True)
    schedule = subs.add_parser("set-assignment-dates", parents=[write])
    schedule.add_argument("--assignment-id", type=lambda value: canvas_id(value, "assignment ID"), required=True)
    for name in ("excuse-submission", "excuse-attendance"):
        excuse = subs.add_parser(name, parents=[write])
        excuse.add_argument("--assignment-id", type=lambda value: canvas_id(value, "assignment ID"), required=True,
                            help="assignment ID; for attendance, the Canvas attendance assignment ID")
    page = subs.add_parser("create-or-update-page", parents=[write])
    page.add_argument("--page-url", help="existing Canvas page URL slug; omit to create a page")
    for name in ("grade-with-rubric", "bulk-grade-with-rubric"):
        grade = subs.add_parser(name, parents=[write])
        grade.add_argument("--assignment-id", type=lambda value: canvas_id(value, "assignment ID"), required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if getattr(args, "limit", 1) < 1 or getattr(args, "limit", 1) > 1000:
            raise OperationError("--limit must be between 1 and 1000")
        print(json.dumps(OPERATIONS[args.operation](args), indent=2, sort_keys=True))
        return 0
    except OperationError as err:
        sys.stderr.write("canvas-api-operations: %s\n" % err)
        return 2


if __name__ == "__main__":
    sys.exit(main())
