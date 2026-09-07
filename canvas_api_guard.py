#!/usr/bin/env python3
# canvas_api_guard - an audited passthrough to the Canvas REST API.
#
# WHAT IT IS. A single-file, stdlib-only wrapper around the Canvas REST API. It gives the user
# (or an agent acting for them) exactly the access their Canvas token already grants - it adds
# NO capability - plus three things: a required confirmation before any write, with a record of
# WHICH KIND it was (a human at a TTY, or an explicit --yes); before/after evidence read back
# from Canvas; and an append-only JSON-lines log written BEFORE the request is sent.
#
# THREAT MODEL - WHAT IT DOES NOT PROTECT AGAINST.
#   * It does not restrict what the token can reach. Scope is set in Canvas, not here.
#   * It does not stop anyone using curl, a browser or the Canvas UI instead. It is a chosen
#     path, not a chokepoint.
#   * It does not contain a determined user, or an agent that can run sudo: such an actor can
#     edit this script, delete the log, or bypass the tool entirely. install.sh prints optional
#     chflags commands that raise that cost without eliminating it, and the log is not
#     protected against root.
#   * It does not verify that the confirming human understood the change - only that a
#     confirmation of a recorded kind occurred.
#
# WHAT IT DOES GIVE. A complete, append-only, local record of everything done through it,
# written before the fact, and a required confirmation whose mode is recorded beside the change
# it authorised - or refused, if no confirmation was possible.
#
# READ TOP TO BOTTOM: constants, token, logging, host pinning, the one request function,
# confirmation, evidence, verbs, argparse, main.

import argparse, datetime, getpass, json, os, subprocess, sys
import urllib.parse, urllib.request

# --------------------------------------------------------------------------------- constants
USER_AGENT = "canvas-api-guard/1.0.0"
KEYCHAIN_SERVICE = "canvas-api-guard"
SECURITY_BIN = "/usr/bin/security"
DEFAULT_DIR = os.path.expanduser("~/.canvas-api-guard")
DEFAULT_LOG = os.path.join(DEFAULT_DIR, "audit.jsonl")
CONFIG_NAME = "config.json"          # sits beside the log; holds the host, never a secret
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
TIMEOUT = 30
REDACTED = "Bearer <redacted>"

class GuardError(Exception):
    """Any refusal or failure the user should see as one clear line."""

# ------------------------------------------------------------------------------------- token
# The token is in exactly two places in this file: read_token_from_keychain() reads it, and one
# line in send_request() puts it into the Authorization header. It is never printed, logged,
# echoed, stored in a file, or taken from argv or the environment - and under --dry-run, or on
# a refused write, it is never even read.
def read_token_from_keychain():
    if not os.path.exists(SECURITY_BIN):
        raise GuardError("macOS keychain not available at %s; refusing to run. There is no "
                         "file or environment fallback for the token." % SECURITY_BIN)
    proc = subprocess.run([SECURITY_BIN, "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a",
                           getpass.getuser(), "-w"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise GuardError("no Canvas token in the keychain for service '%s'. Run: "
                         "canvas_api_guard.py --set-token" % KEYCHAIN_SERVICE)
    token = proc.stdout.decode("utf-8").strip()
    if not token:
        raise GuardError("keychain returned an empty token")
    return token

def set_token():
    """Store a token, read with getpass: never from argv, never a file, never an env var."""
    if not os.path.exists(SECURITY_BIN):
        raise GuardError("macOS keychain not available at %s" % SECURITY_BIN)
    secret = getpass.getpass("Canvas API token (not echoed): ")
    if not secret.strip():
        raise GuardError("empty token; nothing stored")
    proc = subprocess.run([SECURITY_BIN, "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE,
                           "-a", getpass.getuser(), "-w"], input=secret.encode("utf-8"),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise GuardError("keychain refused to store the token: %s"
                         % proc.stderr.decode("utf-8", "replace").strip())
    print("stored in keychain: service=%s account=%s" % (KEYCHAIN_SERVICE, getpass.getuser()))

# ----------------------------------------------------------------------------------- logging
# One JSON object per line, file mode 0600. The "request" line is written and fsynced BEFORE
# the network call, the "response" line after it, and a "refusal" line stands alone. A request
# line with no matching response line means the call was attempted and did not complete.
# Response bodies and the token are never logged.
def log_event(log_path, fields):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {"timestamp": stamp, "pid": os.getpid()}
    record.update(fields)
    directory = os.path.dirname(log_path)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, 0o700)
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record

# ------------------------------------------------------------------------------- host pinning
# Every URL this tool builds comes from canvas_url(). A path carrying a scheme, a netloc or a
# ".." segment is refused: it could otherwise send the Authorization header off-host.
def normalise_path(path):
    """Accept '/api/v1/x', 'api/v1/x' and 'x'; return '/api/v1/x' (plus any query string)."""
    raw = (path or "").strip()
    if not raw:
        raise GuardError("empty path")
    if any(ch.isspace() for ch in raw) or "\\" in raw:
        raise GuardError("path contains whitespace or a backslash: %r" % path)
    query = ""
    if "?" in raw:
        raw, query = raw.split("?", 1)
    split = urllib.parse.urlsplit(raw)
    if split.scheme or split.netloc or raw.startswith("//") or "://" in raw:
        raise GuardError("path must not contain a scheme or a host: %r" % path)
    clean = raw.strip("/")
    if ".." in clean.split("/"):
        raise GuardError("path must not contain '..': %r" % path)
    if clean != "api/v1" and not clean.startswith("api/v1/"):
        clean = "api/v1/" + clean
    return "/" + clean + (("?" + query) if query else "")

def canvas_url(host, path):
    """The only place a URL is built. Pins the scheme and the host."""
    if not host:
        raise GuardError("no Canvas host configured; pass --host or write %s"
                         % os.path.join(DEFAULT_DIR, CONFIG_NAME))
    if "://" in host or "/" in host or "@" in host or any(c.isspace() for c in host):
        raise GuardError("invalid Canvas host: %r" % host)
    url = "https://" + host + normalise_path(path)
    check = urllib.parse.urlsplit(url)
    if check.scheme != "https" or check.netloc != host:
        raise GuardError("refusing a URL that leaves the pinned host: %r" % url)
    return url

# -------------------------------------------------------------------- the one request function
# There is exactly one call to urlopen in this file. Everything else routes through here.
def send_request(cfg, method, path, body=None):
    """The ONLY function that performs network I/O. It logs before it does."""
    method = method.upper()
    url, npath = canvas_url(cfg.host, path), normalise_path(path)
    is_write = method in WRITE_METHODS
    log_event(cfg.log_path, {
        "event": "request", "verb": method, "path": npath, "url": url,
        "kind": "write" if is_write else "read", "dry_run": cfg.dry_run,
        "confirmation": cfg.confirmation, "request_body": body if is_write else None})
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        payload = json.dumps(body).encode("utf-8")
    if cfg.dry_run:                          # print the exact request and send nothing
        shown = dict(headers, Authorization=REDACTED)
        print("DRY RUN - nothing is sent and no token is read")
        print("  method   %s\n  url      %s" % (method, url))
        print("\n".join("  header   %s: %s" % (k, shown[k]) for k in sorted(shown)))
        print("  body     %s" % (json.dumps(body) if body is not None else "(none)"))
        return None
    headers["Authorization"] = "Bearer " + read_token_from_keychain()     # the only use
    request = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        raw = urllib.request.urlopen(request, timeout=TIMEOUT)            # the only call
        status, head, text = raw.status, dict(raw.headers), raw.read()
        raw.close()
    except Exception as err:                       # HTTPError, DNS, TLS, timeout, ...
        log_event(cfg.log_path, {"event": "response", "verb": method, "path": npath, "ok": False,
                                 "status": getattr(err, "code", None), "error": type(err).__name__})
        raise GuardError("%s %s failed: %s: %s" % (method, url, type(err).__name__, err))
    log_event(cfg.log_path, {"event": "response", "verb": method, "path": npath,
                             "status": status, "ok": True, "bytes": len(text)})
    try:
        data = json.loads(text.decode("utf-8")) if text else None
    except ValueError:
        data = None
    return {"status": status, "headers": head, "data": data}

def get_or_none(cfg, path):
    """A GET whose failure is an answer rather than an error - used for read-back."""
    try:
        return send_request(cfg, "GET", path)
    except GuardError:
        return None

# ------------------------------------------------------------------------------ confirmation
# Reads need no confirmation. Writes need one, and the KIND of it is recorded in the log.
# A write that cannot be confirmed is refused by refuse_unconfirmed_write() before anything
# else happens; with a TTY the pre-read runs first so the prompt can show the change.
def refuse_unconfirmed_write(cfg, verb, path):
    """Refuse an unconfirmable write BEFORE the keychain is touched, before the pre-read and
    before any network call - so the refusal can be demonstrated with no token at all."""
    if verb.upper() not in WRITE_METHODS or cfg.dry_run or cfg.yes or sys.stdin.isatty():
        return
    log_event(cfg.log_path, {"event": "refusal", "verb": verb.upper(), "kind": "write",
                             "path": normalise_path(path), "confirmation": "refused-no-tty"})
    raise GuardError("refusing to write without confirmation: stdin is not a terminal; pass "
                     "--yes to confirm non-interactively, which will be recorded in the log")

def confirm(cfg, lines):
    if cfg.dry_run:
        return "dry-run"
    for line in lines:
        print(line)
    if cfg.yes:
        print("confirmation: --yes was passed explicitly")
        return "yes-flag"
    if not sys.stdin.isatty():          # unreachable from the CLI: main() refuses earlier
        raise GuardError("refusing to write without confirmation: stdin is not a terminal")
    if input("Type 'yes' to proceed: ").strip().lower() != "yes":
        raise GuardError("not confirmed; nothing was sent")
    return "human-tty"

# -------------------------------------------------------------------------- evidence helpers
def flatten_leaves(obj, prefix=""):
    """{'submission': {'posted_grade': 95}} -> {'submission.posted_grade': 95}"""
    if not isinstance(obj, dict):
        return {prefix.rstrip("."): obj}
    out = {}
    for key in obj:
        out.update(flatten_leaves(obj[key], prefix + key + "."))
    return out

def compare_fields(body, before, after):
    """Canvas wraps a write body in a resource key ({"submission": {...}}) while the read-back
    object does not, so each requested leaf is compared by its own field name."""
    rows, flat = [], flatten_leaves(body or {})
    for dotted in sorted(flat):
        leaf = dotted.split(".")[-1]
        got_after = after.get(leaf) if isinstance(after, dict) else None
        rows.append({"field": leaf, "requested": flat[dotted], "after": got_after,
                     "before": before.get(leaf) if isinstance(before, dict) else None,
                     "match": None if not isinstance(after, dict)
                     else str(got_after) == str(flat[dotted])})
    return rows

def summarise(obj, limit=10):
    return dict((k, obj[k]) for k in sorted(obj)[:limit]) if isinstance(obj, dict) else None

def emit(cfg, ev):
    """Render the evidence, and record a short form of it (before/after) in the log."""
    log_event(cfg.log_path, {"event": "evidence", "verb": ev.get("verb"), "note": ev.get("note"),
                             "path": ev.get("path"), "status": ev.get("status"),
                             "confirmation": ev.get("confirmation"), "changes": ev.get("changes")})
    if cfg.out == "json":
        print(json.dumps(ev, indent=2, sort_keys=True, default=str))
        return
    for key in ("verb", "path", "url", "confirmation", "status", "note"):
        if ev.get(key) is not None:
            print("%-14s %s" % (key + ":", ev[key]))
    for row in ev.get("changes") or []:
        print("  %-22s %s -> %s   (requested %s, match: %s)"
              % (row["field"], json.dumps(row["before"], default=str),
                 json.dumps(row["after"], default=str),
                 json.dumps(row["requested"], default=str), row["match"]))
    if ev.get("body") is not None:
        print("%-14s %s" % ("body:", json.dumps(ev["body"], sort_keys=True)))
    for item in ev.get("items") or []:
        print("  " + json.dumps(item, sort_keys=True, default=str)[:200])
    if ev.get("object") is not None:
        print("object:")
        for key in sorted(ev["object"]):
            print("  %-22s %s" % (key, json.dumps(ev["object"][key], default=str)[:120]))

# ------------------------------------------------------------------------------------- verbs
def do_get(cfg, path, body):
    resp = send_request(cfg, "GET", path)
    ev = {"verb": "GET", "path": normalise_path(path), "url": canvas_url(cfg.host, path),
          "status": resp["status"] if resp else None}
    if resp and isinstance(resp["data"], list):
        ev["note"], ev["items"] = "%d items returned" % len(resp["data"]), resp["data"]
    elif resp:
        ev["object"] = summarise(resp["data"])
    emit(cfg, ev)

def do_update(cfg, method, path, body):
    """PUT/PATCH: read, show the change, confirm, write, read back, print before and after."""
    if body is None:
        raise GuardError("%s needs a JSON body: -d '{\"...\": ...}'" % method)
    before = send_request(cfg, "GET", path)
    before_obj = before["data"] if before else None
    lines = ["about to %s %s" % (method, canvas_url(cfg.host, path)), "requested changes:"]
    for row in compare_fields(body, before_obj, None):
        lines.append("  %-22s %s -> %s" % (row["field"], json.dumps(row["before"], default=str),
                                           json.dumps(row["requested"], default=str)))
    cfg.confirmation = confirm(cfg, lines)
    resp = send_request(cfg, method, path, body)
    after = get_or_none(cfg, path)
    after_obj = after["data"] if after else None
    emit(cfg, {"verb": method, "path": normalise_path(path), "body": body,
               "url": canvas_url(cfg.host, path), "confirmation": cfg.confirmation,
               "status": resp["status"] if resp else None,
               "changes": compare_fields(body, before_obj, after_obj),
               "note": None if after_obj else "no read-back (dry run, or the GET failed)"})

def do_post(cfg, path, body):
    """POST: nothing exists before, so show the body, confirm, write, read the new object."""
    if body is None:
        raise GuardError("post needs a JSON body: -d '{\"...\": ...}'")
    cfg.confirmation = confirm(cfg, [
        "about to POST %s" % canvas_url(cfg.host, path), "request body:",
        "  " + json.dumps(body, sort_keys=True),
        "nothing exists before a POST; the created object is read back afterwards"])
    resp = send_request(cfg, "POST", path, body)
    created, note, read_path = None, None, None
    if resp is not None:
        location = resp["headers"].get("Location") or resp["headers"].get("location")
        new_id = resp["data"].get("id") if isinstance(resp["data"], dict) else None
        if new_id is not None:
            read_path = normalise_path(path).split("?")[0] + "/" + str(new_id)
        elif location:
            parsed = urllib.parse.urlsplit(location)
            if parsed.netloc and parsed.netloc != cfg.host:
                note = "Location header points off the pinned host: %s" % parsed.netloc
            else:
                read_path = parsed.path
        if read_path:
            back = get_or_none(cfg, read_path)
            created = summarise(back["data"]) if back else None
            if created is None:
                note = "the created object could not be read back at %s" % read_path
        elif note is None:
            note = ("Canvas returned neither an id nor a usable Location header: no read-back "
                    "was performed, and nothing about the created object is asserted here")
    emit(cfg, {"verb": "POST", "path": normalise_path(path), "body": body, "object": created,
               "url": canvas_url(cfg.host, path), "confirmation": cfg.confirmation,
               "status": resp["status"] if resp else None, "note": note})

def do_delete(cfg, path, body):
    """DELETE: read first, so the confirmation shows what is about to be destroyed."""
    before = send_request(cfg, "GET", path)
    before_obj = summarise(before["data"]) if before else None
    cfg.confirmation = confirm(cfg, [
        "about to DELETE %s" % canvas_url(cfg.host, path),
        "this object is about to be destroyed:",
        "  " + json.dumps(before_obj, sort_keys=True, default=str)])
    resp = send_request(cfg, "DELETE", path, body)
    after = get_or_none(cfg, path)
    note = ("dry run: nothing was deleted" if cfg.dry_run else "read-back after delete: gone"
            if after is None else "read-back after delete: STILL PRESENT (soft-deleted?)")
    emit(cfg, {"verb": "DELETE", "path": normalise_path(path), "object": before_obj,
               "url": canvas_url(cfg.host, path), "confirmation": cfg.confirmation,
               "status": resp["status"] if resp else None, "note": note})

VERBS = {"get": do_get, "post": do_post, "delete": do_delete,
         "put": lambda c, p, b: do_update(c, "PUT", p, b),
         "patch": lambda c, p, b: do_update(c, "PATCH", p, b)}

# ---------------------------------------------------------------------------------- argparse
def make_config(args):
    """What send_request needs. confirmation is set by confirm() before any write."""
    return argparse.Namespace(host=read_host(args.host, args.log_path) or "", out=args.output,
                              log_path=args.log_path, dry_run=args.dry_run, yes=args.yes,
                              confirmation=None)

def read_host(explicit, log_path):
    """--host wins; otherwise the host recorded beside the log. The host is not a secret."""
    path = os.path.join(os.path.dirname(log_path) or ".", CONFIG_NAME)
    if explicit or not os.path.exists(path):
        return explicit
    with open(path) as handle:
        return (json.load(handle) or {}).get("host")

def build_parser():
    parser = argparse.ArgumentParser(prog="canvas_api_guard.py", description=(
        "Audited passthrough to the Canvas REST API: confirmation, evidence and an "
        "append-only log. It adds no capability the Canvas token did not already have."))
    parser.add_argument("--set-token", action="store_true", help="store a token, then exit")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("path", help="/api/v1/courses/123, api/v1/courses/123 or courses/123")
    common.add_argument("-d", "--data", help="JSON object to send as the request body")
    common.add_argument("--host", help="Canvas host, e.g. school.instructure.com")
    common.add_argument("--log-path", default=DEFAULT_LOG, help="default: " + DEFAULT_LOG)
    common.add_argument("--dry-run", action="store_true", help="print the request, send nothing")
    common.add_argument("--yes", action="store_true", help="confirm a write non-interactively")
    common.add_argument("-o", "--output", choices=("text", "json"), default="text")
    subs = parser.add_subparsers(dest="verb")
    for name in sorted(VERBS):
        subs.add_parser(name, parents=[common], help="%s a Canvas path" % name)
    return parser

def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.set_token:
            set_token()
            return 0
        if not args.verb:
            parser.print_help()
            return 2
        body = json.loads(args.data) if args.data else None
        cfg = make_config(args)
        canvas_url(cfg.host, args.path)              # fail before anything else happens
        refuse_unconfirmed_write(cfg, args.verb, args.path)
        VERBS[args.verb](cfg, args.path, body)
        return 0
    except (GuardError, ValueError) as err:      # ValueError: an unparseable -d body
        sys.stderr.write("canvas-api-guard: %s\n" % err)
        return 2

if __name__ == "__main__":
    sys.exit(main())
