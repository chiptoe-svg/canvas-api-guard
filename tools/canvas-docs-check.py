#!/usr/bin/env python3
"""Report Canvas documentation drift against the claims recorded in the skill's sources.md.

Build-side only. No Canvas token, no Canvas instance, no student data: this reads the public
Canvas documentation host and nothing else. It is never installed, and it writes nothing.

Pages are fetched as raw HTML and are decoded before matching, so a claim may be recorded
exactly as the documentation renders it. A miss means one of two things and this tool cannot
tell them apart: Canvas moved, or the reference was wrong when it was written. Both need
a person.
"""
import argparse
import html
import re
import sys
import urllib.request

DEFAULT_SOURCES = ".claude/skills/canvas-api-authoring/sources.md"
KEYS = ("endpoints", "params")

FILE_RE = re.compile(r"^## (\S+)\s*$")
URL_RE = re.compile(r"^### (https://\S+)\s*$")
FETCHED_RE = re.compile(r"^fetched:\s*(\S+)\s*$")
ITEM_RE = re.compile(r"^-\s+(.+?)\s*$")
VERB_RE = re.compile(r"^(GET|POST|PUT|PATCH|DELETE)\s+(\S+)$")


def parse_sources(text):
    """Read the sources record format into a list of dicts.

    Each dict has file, url, fetched, endpoints and params.
    """
    records, current_file, current, key = [], None, None, None
    for line in text.splitlines():
        match = FILE_RE.match(line)
        if match:
            current_file, current, key = match.group(1), None, None
            continue
        match = URL_RE.match(line)
        if match:
            current = {"file": current_file, "url": match.group(1), "fetched": None,
                       "endpoints": [], "params": []}
            records.append(current)
            key = None
            continue
        if current is None:
            continue
        match = FETCHED_RE.match(line)
        if match:
            current["fetched"] = match.group(1)
            key = None
            continue
        stripped = line.strip()
        if stripped[:-1] in KEYS and stripped.endswith(":"):
            key = stripped[:-1]
            continue
        match = ITEM_RE.match(line)
        if match and key:
            current[key].append(match.group(1))
            continue
        if stripped:
            key = None
    return records


def _path_of(endpoint):
    """The path part of a 'VERB /api/v1/...' entry, or the entry unchanged."""
    match = VERB_RE.match(endpoint)
    return match.group(2) if match else endpoint


def _joins(char):
    """True if char would make an adjacent claim part of a longer name or path."""
    return char == "/" or char.isalnum() or char == "_" or char == "-"


def _appears(claim, page):
    """True if claim occurs in page whole, not as part of a longer name.

    Both kinds of claim need this. Canvas paths nest, so /courses/:course_id/quizzes is a
    substring of /courses/:course_id/quizzes/:id. Short names nest too: page sits inside
    per_page, id inside grid, and the enum value available inside unavailable. A plain
    substring test would keep reporting any of them as present long after it was removed,
    which is the one drift this tool exists to catch.

    Each edge is checked only when the claim's own character on that edge is a word
    character. A path begins with `/`, which is already its own left boundary, so checking
    its left edge would make it read as missing inside a rendered absolute URL. A bracketed
    parameter ends with `]`, which is likewise its own right boundary.
    """
    if not claim:
        return True
    check_left = claim[0].isalnum() or claim[0] == "_"
    check_right = claim[-1].isalnum() or claim[-1] == "_"
    start = 0
    while True:
        found = page.find(claim, start)
        if found < 0:
            return False
        left = page[found - 1:found] if found else ""
        right = page[found + len(claim):found + len(claim) + 1]
        if not (check_left and _joins(left)) and not (check_right and _joins(right)):
            return True
        start = found + 1


def missing(record, page):
    """Claims in record that no longer appear in page, as (kind, claim) pairs.

    Endpoints match on the path alone: a rendered page routinely puts the verb in a table
    cell away from the path, so requiring them adjacent would report drift that is not there.
    """
    gone = []
    for endpoint in record["endpoints"]:
        if not _appears(_path_of(endpoint), page):
            gone.append(("endpoint", endpoint))
    for param in record["params"]:
        if not _appears(param, page):
            gone.append(("param", param))
    return gone


def report(records, fetch):
    """Check every record and return the printed text and the exit code."""
    lines, bad, shown = [], 0, None
    for record in records:
        try:
            page = fetch(record["url"])
        except Exception as error:  # any fetch failure is a result, not a crash
            if record["file"] != shown:
                shown = record["file"]
                lines.append(shown)
            lines.append("  %s" % record["url"])
            lines.append("    ERROR  %s" % error)
            bad += 1
            continue
        gone = missing(record, html.unescape(page))
        if not gone:
            continue
        if record["file"] != shown:
            shown = record["file"]
            lines.append(shown)
        lines.append("  %s (fetched %s)" % (record["url"], record["fetched"]))
        for kind, claim in gone:
            lines.append("    MISSING %-9s %s" % (kind, claim))
        bad += 1
    lines.append("")
    lines.append("%d pages checked, %d with something missing" % (len(records), bad))
    if not bad:
        lines.append("nothing missing")
    return "\n".join(lines), (1 if bad else 0)


def _fetch(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sources", default=DEFAULT_SOURCES,
                        help="path to sources.md (default: %s)" % DEFAULT_SOURCES)
    args = parser.parse_args(argv)
    with open(args.sources) as handle:
        records = parse_sources(handle.read())
    if not records:
        sys.stderr.write("canvas-docs-check: no source records in %s\n" % args.sources)
        return 2
    text, code = report(records, _fetch)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
