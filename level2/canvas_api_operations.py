#!/usr/bin/env python3
"""Specialized, read-only Canvas analysis operations.

This program never reads a Canvas credential and never opens a network connection.  It calls
the installed Level 1 guard at its fixed path, so every underlying Canvas request keeps the
same credential isolation, host pinning, and audit record.
"""

import argparse
import json
import subprocess
import sys

GUARD = "/usr/local/libexec/canvas_api_guard.py"
USER_AGENT = "canvas-api-operations/0.1.0"


class OperationError(Exception):
    pass


def canvas_id(value, label):
    if not value.isdigit() or int(value) < 1:
        raise OperationError("%s must be a positive Canvas numeric ID" % label)
    return value


def guard_get(path):
    """Ask Level 1 for one JSON response; Level 2 has no token or HTTP client."""
    result = subprocess.run([GUARD, "get", path, "-o", "json"], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise OperationError("Level 1 guard failed: %s" % result.stderr.strip())
    try:
        response = json.loads(result.stdout)
    except ValueError as err:
        raise OperationError("Level 1 guard did not return JSON: %s" % err)
    if not isinstance(response, dict):
        raise OperationError("Level 1 guard returned an unexpected response")
    return response


def all_items(path):
    """Follow only the same-host pagination paths already validated by Level 1."""
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
    """Percent-encode a query value without adding an HTTP client to Level 2."""
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
    return {"operation": "student-attention", "course_id": args.course_id,
            "definition": "transparent Canvas engagement and submission signals; not a risk score or attendance record",
            "students": candidates[:args.limit]}


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
              "attendance-summary": attendance_summary}


def parser():
    result = argparse.ArgumentParser(description="Specialized read-only Canvas analysis via Level 1")
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
