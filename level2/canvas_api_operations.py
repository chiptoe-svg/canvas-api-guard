#!/usr/bin/env python3
"""Specialized Canvas instructor operations.

This program never reads a Canvas credential and never opens a network connection.  It calls
the installed API Only guard at its fixed path, so every underlying Canvas request keeps the
same credential isolation, host pinning, and audit record.
"""

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import time

GUARD = "/usr/local/libexec/canvas_api_guard.py"
USER_AGENT = "canvas-api-operations/0.14.0"
MAX_REVIEW_ATTACHMENTS = 500
SCORE_TOLERANCE = 0.005        # API Only's own tolerance: Canvas rounds a score to two decimals


class OperationError(Exception):
    pass


class GuardUncertain(OperationError):
    """API Only sent a write and could not prove it (exit 3). It is never retried here."""


def canvas_id(value, label):
    if not value.isdigit() or int(value) < 1:
        raise OperationError("%s must be a positive Canvas numeric ID" % label)
    return value


def guard_failure(stderr):
    """The guard's own `canvas-api-guard:` line is the LAST non-empty line of its stderr;
    under -o json everything before it is the confirmation preamble, which would repeat the
    request body. A failure reported here stays one line."""
    lines = [line for line in (stderr or "").splitlines() if line.strip()]
    return lines[-1].strip() if lines else ""


def guard_get(path):
    """Ask API Only for one JSON response; Specialized Functions have no token or HTTP client."""
    result = subprocess.run([GUARD, "get", path, "-o", "json"], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise OperationError("API Only guard failed: %s" % guard_failure(result.stderr))
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
                             % guard_failure(result.stderr))
    if result.returncode:
        raise OperationError("API Only guard failed: %s" % guard_failure(result.stderr))
    if phase == "dry-run":
        return None
    try:
        evidence = json.loads(result.stdout)
    except ValueError as err:
        raise OperationError("API Only guard did not return write evidence: %s" % err)
    # "passed" means every requested leaf API Only could see matched, and at least one was
    # checked. It does not promise a PARTICULAR field was proved: a leaf the read-back object
    # does not expose is reported null. A caller that needs a specific field proved reads it
    # back itself - create_rubric and verify_rubric_assessment below both do.
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


def criterion(value):
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
    # Canvas wants ratings, like criteria, as an index-keyed hash: rubric[criteria][0][ratings][1]
    # [points]. An array here is what canvas-cli's live-tested encoder avoids, and a bare
    # HTTP 500 is how Canvas answers the wrong shape.
    return dict(definition, ratings={str(index): rating for index, rating in enumerate(ratings)})


def rubric_body(value):
    definition = exact_object(value, ("title", "criteria"), ("free_form_criterion_comments",))
    text(definition["title"], "rubric title")
    if not isinstance(definition["criteria"], list) or not definition["criteria"]:
        raise OperationError("rubric criteria must be a non-empty array")
    criteria = {str(index): criterion(item) for index, item in enumerate(definition["criteria"])}
    rubric = {"title": definition["title"], "criteria": criteria}
    # Sent only when true: Canvas stores false as null, which API Only's strict read-back of
    # an exposed field would report as a mismatch (seen live, rubric 138355).
    if definition.get("free_form_criterion_comments"):
        rubric["free_form_criterion_comments"] = True
    return {"rubric": rubric,
            # a bookmark on the course is what lists the rubric on the course's Rubrics page
            "rubric_association": {"association_type": "Course", "purpose": "bookmark"}}


def create_rubric(args):
    """One write. With --assignment-id, Canvas's create call also attaches the new rubric to
    that assignment for grading; the assignment is then read back to prove it."""
    body = rubric_body(definition_file(args.definition))
    assignment_id = getattr(args, "assignment_id", None)
    if assignment_id:
        attached = (guard_get("courses/%s/assignments/%s" % (args.course_id, assignment_id)).get("object") or {}
                    ).get("rubric_settings") or {}
        if attached.get("id") is not None:
            raise OperationError("assignment %s already has rubric %s attached for grading; detach it in Canvas "
                                 "first, or create this rubric without --assignment-id" % (assignment_id, attached["id"]))
        body["rubric_association"] = {"association_type": "Assignment", "association_id": int(assignment_id),
                                      "purpose": "grading", "use_for_grading": True}
    else:
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
            wanted = list(expected_row["ratings"].values())
            got = actual_row.get("ratings") or []
            if len(got) != len(wanted) or any(
                    row.get("description") != want["description"] or number(row.get("points")) != want["points"]
                    for row, want in zip(got, wanted)):
                raise GuardUncertain("WRITE STATUS UNCERTAIN: rubric ratings did not read back")
        result = {"rubric_id": rubric_id, "assignment_id": assignment_id, "speedgrader_url": None}
        if assignment_id:
            assignment = guard_get("courses/%s/assignments/%s" % (args.course_id, assignment_id)).get("object") or {}
            if str((assignment.get("rubric_settings") or {}).get("id")) != str(rubric_id):
                raise GuardUncertain("WRITE STATUS UNCERTAIN: assignment %s did not read back rubric %s"
                                     % (assignment_id, rubric_id))
            result["speedgrader_url"] = speedgrader_url(assignment)
        return {"result": result}


def live_rubric(args):
    """The assignment object carries its attached rubric's criteria (ids and points) in
    `rubric`; Canvas exposes no read for the association itself, and the grade write below
    needs none: the rubric rows ride the submission update, and the rubric total is posted
    as the grade, so the "use for grading" setting is not consulted."""
    assignment = guard_get("courses/%s/assignments/%s" % (args.course_id, args.assignment_id)).get("object") or {}
    criteria = assignment.get("rubric")
    if not isinstance(criteria, list) or not criteria:
        raise OperationError("assignment has no attached Canvas rubric; attach a rubric first")
    return assignment, {"data": criteria}


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
        if (not isinstance(scored, dict)
                or abs(number(scored.get("points")) - score["points"]) > SCORE_TOLERANCE):
            raise GuardUncertain("WRITE STATUS UNCERTAIN: rubric criterion %s did not read back "
                                 "for student %s" % (criterion_id, student_id))


def grade_one(args, value):
    assignment, rubric = live_rubric(args)
    student_id, criteria, total = grade_payload(value, rubric)
    path = "courses/%s/assignments/%s/submissions/%s?include[]=rubric_assessment&include[]=user" % (
        args.course_id, args.assignment_id, student_id)
    guard_get(path)
    body = {"submission": {"posted_grade": total}, "rubric_assessment": criteria}
    write_plan("grade-with-rubric", args, path, body)
    guard_write("put", path, body, operation_phase(args))
    if operation_phase(args) != "dry-run":
        verify_rubric_assessment(args, student_id, criteria)
    return {"student_id": student_id, "posted_grade": total,
            "speedgrader_url": speedgrader_url(assignment, student_id)}


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


def speedgrader_url(assignment, student_id=None):
    """The instructor's SpeedGrader page for this assignment, and for one student when given,
    built from the assignment's own html_url so the host is Canvas's; None without one."""
    match = re.match(r"(https://[^/]+)/courses/(\d+)/assignments/(\d+)$", str(assignment.get("html_url") or ""))
    if not match:
        return None
    url = "%s/courses/%s/gradebook/speed_grader?assignment_id=%s" % match.groups()
    return url if student_id is None else url + "&student_id=%s" % student_id


def current_grade(submission):
    """What Canvas already holds for this submission, so an already-graded one is never
    re-reviewed or regraded by accident."""
    return {key: submission.get(key) for key in ("workflow_state", "score", "grade", "graded_at")}


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
    grade = current_grade(submission)
    if grade["workflow_state"] == "graded":
        next_step = ("Already graded %s at %s: ask the instructor before reviewing or regrading; "
                     "no grade has been written." % (grade["grade"], grade["graded_at"]))
    else:
        next_step = "Review the local attachment set against the live rubric; no grade has been written."
    return {"operation": "prepare-submission-review", "course_id": args.course_id,
            "assignment": {"assignment_id": assignment.get("id"), "title": assignment.get("name")},
            "student": {"student_id": submission.get("user_id"), "name": (submission.get("user") or {}).get("name")},
            "submission_id": int(canvas_id(str(submission.get("id", "")), "submission ID")), "attachments": downloaded,
            "current_grade": grade, "speedgrader_url": speedgrader_url(assignment, args.student_id),
            "next_step": next_step}


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
            record.update({"student_id": submission.get("user_id"), "submission_id": submission.get("id"),
                           "current_grade": current_grade(submission)})
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


QUIZ_REGRADE_LIMIT = 100       # attempts in one reviewed batch: one section, refused whole
QUIZ_PAGE_CAP = 10             # 100 per page; past this the batch cap has already refused
CLASSIC_QUESTION_TYPES = ("multiple_choice_question", "true_false_question")
# The update REPLACES the answer set, so every answer is sent back as Canvas returned it with
# only its weight changed. These are the fields canvas-cli round-trips (internal/api
# QuizAnswer); anything else Canvas returns is not sent back.
ANSWER_FIELDS = ("id", "text", "html", "comments", "comments_html")


def regrade_definition(value):
    """Answer IDs only: a Canvas answer's identity is its ID, its text is instructor HTML that
    is not unique and that this write has to round-trip untouched."""
    definition = exact_object(value, ("quiz_id", "question_id", "correct_answer_ids"), ())
    ids = definition["correct_answer_ids"]
    if not isinstance(ids, list) or not ids:
        raise OperationError("correct_answer_ids must be a non-empty array of Canvas answer IDs")
    answer_ids = [canvas_id(str(answer_id), "answer ID") for answer_id in ids]
    if len(set(answer_ids)) != len(answer_ids):
        raise OperationError("correct_answer_ids contains a duplicate answer ID")
    return (canvas_id(str(definition["quiz_id"]), "quiz ID"),
            canvas_id(str(definition["question_id"]), "question ID"), answer_ids)


def regrade_answer_key(question, answer_ids):
    """Canvas encodes correctness as weight: 100 correct, 0 wrong. Every answer not listed
    drops to 0, so a student who picked the old answer loses those points - the plan shows it."""
    if question.get("question_type") not in CLASSIC_QUESTION_TYPES:
        raise OperationError("regrade supports multiple_choice_question and true_false_question; "
                             "question %s is %s" % (question.get("id"),
                                                    question.get("question_type")))
    available = [str(answer.get("id")) for answer in question.get("answers") or []]
    missing = [answer_id for answer_id in answer_ids if answer_id not in available]
    if missing:
        raise OperationError("answer %s is not an answer of question %s (available: %s)"
                             % (", ".join(missing), question.get("id"), ", ".join(available)))
    answers = []
    for answer in question["answers"]:
        kept = dict((field, answer[field]) for field in ANSWER_FIELDS if field in answer)
        kept["weight"] = 100 if str(answer.get("id")) in answer_ids else 0
        answers.append(kept)
    return answers


def quiz_submissions(course_id, quiz_id):
    """Canvas answers this list in a {"quiz_submissions": [...]} envelope, not a JSON array, so
    API Only reports one object with no rel="next" and the pages are walked here. A short page
    is not the end - an admin can cap per_page below the request - but a page that adds no new
    submission is."""
    found, seen = [], set()
    for page in range(1, QUIZ_PAGE_CAP + 1):
        response = guard_get("courses/%s/quizzes/%s/submissions?page=%d&per_page=100"
                             % (course_id, quiz_id, page))
        rows = (response.get("object") or {}).get("quiz_submissions")
        if not isinstance(rows, list):
            raise OperationError("Canvas did not return a quiz_submissions list for quiz %s"
                                 % quiz_id)
        added = [row for row in rows if str(row.get("id")) not in seen]
        seen.update(str(row.get("id")) for row in added)
        found.extend(added)
        if not added:
            return found
    raise OperationError("quiz %s lists more submission pages than this operation reads" % quiz_id)


def selected_answer_id(value):
    """Canvas may deliver the selected answer id as a JSON number, a whole-number float, or a
    numeric string (surrounding whitespace stripped). Anything else - including None or a value
    <= 0 - means unanswered. Mirrors the live-tested Go decoder (canvas-cli's selectedAnswerID)."""
    if isinstance(value, bool):
        parsed = None
    elif isinstance(value, int):
        parsed = value
    elif isinstance(value, float):
        parsed = int(value) if value == int(value) else None
    elif isinstance(value, str):
        stripped = value.strip()
        parsed = int(stripped) if stripped.isdigit() else None
    else:
        parsed = None
    return str(parsed) if parsed is not None and parsed > 0 else None


def attempt_row(course_id, assignment_id, submission, question, answer_ids):
    """One attempt's before/after, from the assignment submission's history - the per-question
    record a grader can see. Only answer_id and points are trusted: Canvas does not recompute
    submission_data's "correct" flag when an answer key changes (canvas-cli observed correct:
    true with points 0 after a regrade), so correctness is always answer_id against the key."""
    row = {"submission_id": submission.get("id"), "user_id": submission.get("user_id"),
           "attempt": submission.get("attempt"), "old_score": number(submission.get("score")),
           "selected_answer_id": None, "old_points": None, "new_points": None, "delta": 0}
    history = guard_get("courses/%s/assignments/%s/submissions/%s?include[]=submission_history"
                        % (course_id, assignment_id, submission.get("user_id"))).get("object") or {}
    entry = next((item for item in reversed(history.get("submission_history") or [])
                  if item.get("attempt") == row["attempt"] and item.get("submission_data")), None)
    answered = next((item for item in (entry or {}).get("submission_data") or []
                     if str(item.get("question_id")) == str(question.get("id"))), None)
    selected = selected_answer_id((answered or {}).get("answer_id")) if answered else None
    if answered is None or selected is None:
        row["skipped"] = ("no graded answer record for attempt %s" % row["attempt"]
                          if entry is None else "the student did not answer this question")
        return row
    row["old_score"] = number(entry.get("score"))
    row["selected_answer_id"] = selected
    row["old_points"] = number(answered.get("points"))
    row["new_points"] = (number(question.get("points_possible"))
                         if row["selected_answer_id"] in answer_ids else 0.0)
    row["delta"] = row["new_points"] - row["old_points"]
    row["expected_score"] = row["old_score"] + row["delta"]
    return row


def regrade_plan(args):
    """Read everything the regrade depends on and work out, per attempt, what would change.
    Nothing is written here, and the cap refuses the whole batch rather than part of a class."""
    quiz_id, question_id, answer_ids = regrade_definition(definition_file(args.definition))
    quiz = guard_get("courses/%s/quizzes/%s" % (args.course_id, quiz_id)).get("object") or {}
    if quiz.get("quiz_type") != "assignment" or not quiz.get("assignment_id"):
        raise OperationError("quiz %s is quiz_type %s with assignment_id %s; only a graded "
                             "classic quiz can be regraded, and a New Quizzes quiz is not in "
                             "this API at all" % (quiz_id, quiz.get("quiz_type"),
                                                  quiz.get("assignment_id")))
    question = guard_get("courses/%s/quizzes/%s/questions/%s"
                         % (args.course_id, quiz_id, question_id)).get("object") or {}
    regrade_answer_key(question, answer_ids)        # refuse an unsupported question first
    rows = [attempt_row(args.course_id, quiz["assignment_id"], submission, question, answer_ids)
            for submission in quiz_submissions(args.course_id, quiz_id)
            if submission.get("workflow_state") == "complete"]
    changed = [row for row in rows if abs(row["delta"]) > SCORE_TOLERANCE]
    if len(changed) > QUIZ_REGRADE_LIMIT:
        raise OperationError("regrade refuses more than %s attempts in one reviewed batch; %s "
                             "attempts would change" % (QUIZ_REGRADE_LIMIT, len(changed)))
    identities = student_identities(args.course_id, [row["user_id"] for row in rows])
    for row in rows:
        row.update(identities.get(str(row["user_id"]), {}))
    return quiz_id, question_id, answer_ids, question, rows, changed


READ_BACK_READS = 3            # Canvas applies a quiz score asynchronously (canvas-cli, live)
READ_BACK_DELAY = 1.0


def verify_answer_key(course_id, quiz_id, question_id, answer_ids):
    """API Only proves the weights it sent, answer by answer. This checks the resulting KEY -
    the set of answers Canvas now treats as correct - so neither the order Canvas returns
    answers in nor an answer this write did not name can hide a wrong outcome."""
    question = guard_get("courses/%s/quizzes/%s/questions/%s"
                         % (course_id, quiz_id, question_id)).get("object") or {}
    correct = sorted(str(answer.get("id")) for answer in question.get("answers") or []
                     if number(answer.get("weight")) == 100)
    if correct != sorted(answer_ids):
        raise GuardUncertain("WRITE STATUS UNCERTAIN: question %s reports correct answer(s) %s, "
                             "not %s" % (question_id, ", ".join(correct) or "none",
                                         ", ".join(answer_ids)))


def read_back_attempt(path, row):
    """The attempt's own score, at ?attempt=N: the assignment submission's history lags this
    write and must not be used. Canvas can still return the previous value on an immediate
    read, so the read is repeated a bounded number of times before it is a mismatch."""
    for read in range(READ_BACK_READS):
        if read:
            time.sleep(READ_BACK_DELAY)
        found = (((guard_get("%s?attempt=%s" % (path, row["attempt"])).get("object") or {})
                  .get("quiz_submissions") or [{}])[0])
        row["new_score"] = number(found.get("score"))
        if abs(row["new_score"] - row["expected_score"]) <= SCORE_TOLERANCE:
            row["verified"] = True
            return
    raise GuardUncertain("WRITE STATUS UNCERTAIN: submission %s attempt %s read back score %s, "
                         "expected %s" % (row["submission_id"], row["attempt"],
                                          row["new_score"], row["expected_score"]))


def write_attempt_score(args, quiz_id, question_id, row):
    """One attempt's per-question score. canvas-cli sends attempt and questions[qid][score] and
    nothing else - no fudge_points, no comment - so neither is sent here."""
    path = "courses/%s/quizzes/%s/submissions/%s" % (args.course_id, quiz_id,
                                                     row["submission_id"])
    body = {"quiz_submissions": [{"attempt": row["attempt"],
                                  "questions": {str(question_id): {"score": row["new_points"]}}}]}
    guard_write("put", path, body, operation_phase(args))
    if operation_phase(args) != "dry-run":
        read_back_attempt(path, row)


def plan_digest(changed):
    """One string naming exactly which attempts would be written and to what. The dry run prints
    it; --expect-plan on the --yes run refuses if a recomputed plan differs, so an attempt that
    arrived between the approval and the write is never scored unseen."""
    rows = sorted((str(row["submission_id"]), int(row["attempt"]), float(number(row["new_points"])))
                  for row in changed)
    return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()


def regrade_quiz_question(args):
    """Rewrite one classic-quiz question's answer key and rescore every completed attempt of
    that question: the answer key first, so a failure there touches no score, then one audited
    write per attempt, each read back at its own attempt number."""
    quiz_id, question_id, answer_ids, question, rows, changed = regrade_plan(args)
    digest = plan_digest(changed)
    expected = getattr(args, "expect_plan", None)
    if expected and expected != digest:
        raise OperationError("the attempts that would change are not the ones that were approved "
                             "(plan %s, approved %s): an attempt or score moved since the dry run; "
                             "run the dry run again and approve that plan" % (digest[:12], expected[:12]))
    print(json.dumps({"operation": "regrade-quiz-question", "phase": operation_phase(args),
                      "course_id": args.course_id, "quiz_id": quiz_id,
                      "question_id": question_id, "question_type": question.get("question_type"),
                      "points_possible": number(question.get("points_possible")),
                      "correct_answer_ids": answer_ids, "attempts_considered": len(rows),
                      "attempts_changed": len(changed), "rows": rows, "plan_digest": digest,
                      "warning": "every answer not listed is now worth 0; a student who picked "
                                 "one of those loses the points, shown as a negative delta"},
                     indent=2, sort_keys=True))
    path = "courses/%s/quizzes/%s/questions/%s" % (args.course_id, quiz_id, question_id)
    body = {"question": {"answers": regrade_answer_key(question, answer_ids)}}
    write_plan("regrade-quiz-question", args, path, body)
    guard_write("put", path, body, operation_phase(args))
    written = []
    if operation_phase(args) != "dry-run":
        verify_answer_key(args.course_id, quiz_id, question_id, answer_ids)
    try:
        for row in changed:
            write_attempt_score(args, quiz_id, question_id, row)
            if operation_phase(args) != "dry-run":
                written.append(row["submission_id"])
    except GuardUncertain:
        raise
    except OperationError as err:
        if not written or operation_phase(args) == "dry-run":
            raise                 # nothing was written, so this is an ordinary refusal
        raise GuardUncertain("regrade stopped after %d of %d attempts; the scores already "
                             "written stand and are not retried: %s"
                             % (len(written), len(changed), err))
    print(json.dumps({"operation": "regrade-quiz-question", "phase": operation_phase(args),
                      "attempts_written": len(written), "attempts_changed": len(changed),
                      "rows": changed}, indent=2, sort_keys=True))


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
              "student-attention": student_attention,
              "regrade-quiz-question": regrade_quiz_question}


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
    create = subs.add_parser("create-rubric", parents=[write])
    create.add_argument("--assignment-id", type=lambda value: canvas_id(value, "assignment ID"),
                        help="also attach the new rubric to this assignment for grading, in the same write")
    for name in ("grade-with-rubric", "bulk-grade-with-rubric"):
        grade = subs.add_parser(name, parents=[write])
        grade.add_argument("--assignment-id", type=lambda value: canvas_id(value, "assignment ID"), required=True)
    regrade = subs.add_parser("regrade-quiz-question", parents=[write])
    regrade.add_argument("--expect-plan", metavar="DIGEST",
                         help="the plan_digest the dry run printed; the write is refused if the "
                              "attempts that would change are no longer exactly those")
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
