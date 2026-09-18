#!/usr/bin/env python3
"""Report Canvas source drift against the `source:` citations recorded in this repo.

Build-side only. No Canvas token, no Canvas instance, no student data: this reads public files
from the canvas-lms repository and nothing else. It is never installed, and it writes nothing.

The authoring skill's rule is that a cited line number is a hint and the cited SYMBOL is the real
anchor, because `master` moves. This checks the anchors: for every ``source: `path#symbol```
citation it fetches that file once and reports whether the symbol is still defined there. It does
NOT check that the symbol still means what the claim says - only a person reading it can do that.

A miss means one of two things and this tool cannot tell them apart: Canvas moved, or the citation
was wrong when it was written. Both need a person.
"""
import argparse
import os
import re
import sys
import urllib.request

DEFAULT_PATHS = (".claude/skills/canvas-api-authoring/references",
                 "docs/superpowers/specs")
RAW = "https://raw.githubusercontent.com/instructure/canvas-lms/%s/%s"
CITE_RE = re.compile(r"source:\s*`([^`]+)`")


def parse_citations(text, origin):
    """Every `source:` citation in one markdown file, as {origin, path, symbol}.

    A citation is `path` or `path#symbol`; anything after the closing backtick (", line 574")
    is a hint this tool deliberately ignores, because line numbers move and symbols do not.
    """
    found = []
    for raw in CITE_RE.findall(text):
        path, _, symbol = raw.partition("#")
        found.append({"origin": origin, "path": path.strip(), "symbol": symbol.strip() or None})
    return found


def anchored(symbol, text):
    """How the symbol appears: as a definition, a constant, a class, plain text, or not at all.

    The trailing lookahead rather than \\b: a Ruby predicate ends in `?`, which is not a word
    character, so \\b would never match `def hide_grade_from_student?(...)`.
    """
    name = re.escape(symbol)
    tail = r"(?![A-Za-z0-9_?!])"
    if re.search(r"^\s*def\s+(?:self\.)?%s%s" % (name, tail), text, re.M):
        return "def"
    if re.search(r"^\s*%s\s*=" % name, text, re.M):
        return "const"
    if re.search(r"^\s*(?:class|module)\s+%s%s" % (name, tail), text, re.M):
        return "class"
    # A standalone occurrence, not a substring: `assess` must not be satisfied by the word
    # `assessment_count`, or every WEAK would be noise and nobody would read them.
    if re.search(r"(?<![A-Za-z0-9_])%s%s" % (name, tail), text):
        return "text"
    return None


def report(citations, fetch, ref="master"):
    """Check every citation and return the printed text and the exit code.

    Each distinct path is fetched once however often it is cited. WEAK is reported but does not
    fail the run: a symbol present only as prose may be a rename or may be a comment, and a
    person decides which.
    """
    pages, lines, missing, weak, errors, shown = {}, [], 0, 0, 0, None
    for cite in citations:
        path = cite["path"]
        if path not in pages:
            try:
                pages[path] = fetch(RAW % (ref, path))
            except Exception as error:      # any fetch failure is a result, not a crash
                pages[path] = error
        page = pages[path]
        verdict = None
        if isinstance(page, Exception):
            verdict, detail = "ERROR", str(page)
            errors += 1
        elif cite["symbol"] is None:
            continue                        # the file exists; there is no anchor to check
        else:
            how = anchored(cite["symbol"], page)
            if how is None:
                verdict, detail = "MISSING", "%s#%s" % (path, cite["symbol"])
                missing += 1
            elif how == "text":
                verdict, detail = "WEAK", "%s#%s appears only as text, not as a definition" % (
                    path, cite["symbol"])
                weak += 1
        if verdict is None:
            continue
        if cite["origin"] != shown:
            shown = cite["origin"]
            lines.append(shown)
        lines.append("    %-7s %s" % (verdict, detail))
    lines.append("")
    lines.append("%d citations across %d files checked, %d missing, %d weak, %d unreadable"
                 % (len(citations), len(pages), missing, weak, errors))
    if not (missing or errors):
        lines.append("every anchor still resolves" if not weak else
                     "every anchor resolves; the weak ones need a person")
    return "\n".join(lines), (1 if missing or errors else 0)


def markdown_files(paths):
    """Every markdown file under the given files or directories, in a stable order."""
    found = []
    for path in paths:
        if os.path.isdir(path):
            for root, _, names in os.walk(path):
                found.extend(os.path.join(root, name) for name in names if name.endswith(".md"))
        elif path.endswith(".md"):
            found.append(path)
    return sorted(set(found))


def _fetch(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", default=list(DEFAULT_PATHS),
                        help="markdown files or directories to scan (default: %s)"
                             % ", ".join(DEFAULT_PATHS))
    parser.add_argument("--ref", default="master",
                        help="canvas-lms ref to check against (default: master)")
    args = parser.parse_args(argv)
    citations = []
    for path in markdown_files(args.paths):
        with open(path) as handle:
            citations.extend(parse_citations(handle.read(), path))
    if not citations:
        sys.stderr.write("canvas-source-check: no `source:` citations found\n")
        return 2
    text, code = report(citations, _fetch, args.ref)
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
