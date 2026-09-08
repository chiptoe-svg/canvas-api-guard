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
#     immutable/append-only commands that raise that cost without eliminating it, and the log
#     is not protected against root.
#   * It does not verify that the confirming human understood the change - only that a
#     confirmation of a recorded kind occurred.
#   * Under Codex: the sandbox is Codex's boundary and the rules file is Codex's prompt. Both
#     are configuration in the user's home directory, and the user can change them. A write
#     wrapped in a shell script, invoked by an unlisted path, or built through a variable may
#     miss the rules; it then runs inside the sandbox, fails there (no network, no credential
#     store), and Codex asks the person to escalate it - a prompt, not a silent write, as long
#     as approvals_reviewer is "user". A Codex write is logged as confirmation "yes-flag": the
#     person's approval happened in Codex's prompt, which this script cannot observe.
#   * The token is readable by any command running as the user OUTSIDE the sandbox, including
#     one the person approved without reading closely. Closing that requires running this
#     script as a different user; it is not done here. The shipped rules authorize only the
#     absolute, root-owned installed guard; the guard independently pins its host and log paths.
#   * Every read this script returns flows through the agent to its provider. Nothing here
#     changes where that data goes.
#
# WHAT IT DOES GIVE. A complete, append-only, local record of everything done through it,
# written before the fact, and a required confirmation whose mode is recorded beside the change
# it authorised - or refused, if no confirmation was possible. And one invariant above all:
# THE TOKEN IS ONLY EVER SENT TO THE HOST RECORDED IN THE FIXED SYSTEM CONFIGURATION.
#
# READ TOP TO BOTTOM: constants, token, logging, host pinning, the one request function,
# confirmation, evidence, verbs, argparse, main.

import argparse, datetime, getpass, hashlib, json, os, pty, pwd, re, stat, subprocess, sys, tempfile, time
import urllib.error, urllib.parse, urllib.request

# --------------------------------------------------------------------------------- constants
USER_AGENT = "canvas-api-guard/1.5.0"
KEYCHAIN_SERVICE = "canvas-api-guard"
SECURITY_BIN = "/usr/bin/security"
SECRET_TOOL_PATHS = ("/usr/bin/secret-tool", "/usr/local/bin/secret-tool")
DEFAULT_DIR = os.path.join(pwd.getpwuid(os.getuid()).pw_dir, ".canvas-api-guard")
DEFAULT_LOG = os.path.join(DEFAULT_DIR, "audit.jsonl")
REVIEW_DIR = os.path.join(DEFAULT_DIR, "submission-reviews")
CONFIG_PATH = "/usr/local/etc/canvas-api-guard/config.json"  # root/admin-owned; not a secret
WRITE_METHODS = ("POST", "PUT", "PATCH", "DELETE")
TIMEOUT = 30
REDACTED = "Bearer <redacted>"
AGENT_MARKERS = ("AI_AGENT", "CLAUDE_CODE_SESSION_ID", "CODEX_SANDBOX",
                 "CODEX_SANDBOX_NETWORK_DISABLED")   # names recorded if present; never values
_SOURCE = None

class GuardError(Exception):
    """Any refusal or failure the user should see as one clear line."""

class RequestFailure(GuardError):
    """A Canvas request failed; status is None for transport failures."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status

class VerificationFailure(GuardError):
    """The write returned, but the required read-back did not prove the outcome."""

# ------------------------------------------------------------------------------------- token
# The token is in exactly two places in this file: read_token() reads it, and one line in
# send_request() puts it into the Authorization header. It is never printed, logged, echoed,
# stored in a file, or taken from argv or the environment - and under --dry-run, or on a
# refused write, it is never even read. It lives in the macOS keychain or the Linux secret
# service; any other platform is refused.
def account_name():
    """The OS account running the guard, independent of forgeable USER/LOGNAME variables."""
    return pwd.getpwuid(os.getuid()).pw_name

def trusted_linux_secret_tool():
    """Return a fixed, root-owned secret-tool path; never select credential code from PATH."""
    for path in SECRET_TOOL_PATHS:
        try:
            info = os.stat(path)
        except OSError:
            continue
        if stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not (info.st_mode & 0o022):
            return path
    raise GuardError("trusted secret-tool not found at %s; install libsecret-tools "
                     "(Debian/Ubuntu) or libsecret (Fedora). There is no PATH, file, or "
                     "environment fallback." % " or ".join(SECRET_TOOL_PATHS))

def credential_command(action):
    """The platform command that reads ("read") or stores ("store") the token."""
    user = account_name()
    if sys.platform == "darwin":
        if not os.path.exists(SECURITY_BIN):
            raise GuardError("macOS keychain tool not found at %s; refusing to run" % SECURITY_BIN)
        if action == "read":
            return [SECURITY_BIN, "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", user, "-w"]
        return [SECURITY_BIN, "add-generic-password", "-U", "-s", KEYCHAIN_SERVICE, "-a", user, "-w"]
    if sys.platform.startswith("linux"):
        tool = trusted_linux_secret_tool()
        if action == "read":
            return [tool, "lookup", "service", KEYCHAIN_SERVICE, "account", user]
        return [tool, "store", "--label=" + KEYCHAIN_SERVICE, "service", KEYCHAIN_SERVICE,
                "account", user]
    raise GuardError("unsupported platform %r: the token can live only in the macOS keychain "
                     "or the Linux secret service" % sys.platform)

def read_token():
    proc = subprocess.run(credential_command("read"), stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise GuardError("no Canvas token stored for service '%s'. Run: "
                         "canvas_api_guard.py --set-token" % KEYCHAIN_SERVICE)
    token = proc.stdout.decode("utf-8").strip()
    if not token:
        raise GuardError("the credential store returned an empty token; run --set-token again")
    return token

def _macos_keychain_output(fd):
    """Relay Keychain output while replacing its misleading generic-password labels."""
    output = os.read(fd, 1024)
    return output.replace(
        b"retype password for new item:", b"Retype Canvas API token (hidden):").replace(
        b"password data for new item:", b"Canvas API token (hidden):")

def _macos_store_token(command):
    """Let security(1) read directly from the TTY; rewrite display labels only."""
    if not sys.stdin.isatty():
        raise GuardError("macOS token entry requires a visible terminal")
    status = pty.spawn(command, master_read=_macos_keychain_output)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise GuardError("the macOS Keychain refused the token")

def set_token():
    """Store a token through hidden terminal input, never argv, a file, or an env var."""
    command = credential_command("store")            # refuses an unsupported platform first
    if sys.platform == "darwin":
        _macos_store_token(command)
        read_token()                                  # prove the new item is accessible and nonempty
    else:
        secret = getpass.getpass("Canvas API token (hidden): ").strip()
        if not secret:
            raise GuardError("empty token; nothing stored")
        proc = subprocess.run(command, input=(secret + "\n").encode("utf-8"),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise GuardError("the credential store refused the token: %s"
                             % proc.stderr.decode("utf-8", "replace").strip())
        if read_token() != secret:
            raise GuardError("the token did not read back as stored; nothing usable was stored")
    print("stored for service=%s account=%s" % (KEYCHAIN_SERVICE, account_name()))

# ----------------------------------------------------------------------------------- logging
# One JSON object per line, file mode 0600. The "request" line is written and fsynced BEFORE
# the network call, the "response" line after it, and a "refusal" line stands alone. A request
# line with no matching response line means the call was attempted and did not complete.
# Response bodies and the token are never logged. Every line also carries a "source" object
# saying how the guard was invoked, for correlating a line with an agent's transcript or a
# person's terminal session.
def parent_process_name():
    """The parent process's command name, or None. Never raises: it is a hint, not a gate."""
    try:
        ppid = os.getppid()
        if sys.platform.startswith("linux"):
            with open("/proc/%d/comm" % ppid) as handle:
                return handle.read().strip() or None
        proc = subprocess.run(["ps", "-o", "comm=", "-p", str(ppid)], stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL)
        return os.path.basename(proc.stdout.decode("utf-8", "replace").strip()) or None
    except Exception:
        return None

def invocation_source():
    """How the guard was invoked, for correlating a log line with an agent's own transcript
    or a person's terminal session. It is NOT an identity: an environment can be forged and
    a parent can be a wrapper shell. The confirmation field says who confirmed a write."""
    global _SOURCE
    if _SOURCE is None:
        _SOURCE = {"tty": bool(sys.stdin.isatty()), "parent": parent_process_name(),
                   "agent_env": sorted(name for name in AGENT_MARKERS if name in os.environ)}
    return _SOURCE

def secure_log_fd(log_path):
    """Open the fixed audit log without following a link; refuse weak ownership or modes."""
    directory = os.path.dirname(log_path)
    if directory:
        try:
            dinfo = os.lstat(directory)
        except FileNotFoundError:
            try:
                os.makedirs(directory, 0o700)
                dinfo = os.lstat(directory)
            except OSError as err:
                raise GuardError("cannot securely create audit directory %s: %s"
                                 % (directory, err))
        except OSError as err:
            raise GuardError("cannot inspect audit directory %s: %s" % (directory, err))
        if (not stat.S_ISDIR(dinfo.st_mode) or stat.S_ISLNK(dinfo.st_mode)
                or dinfo.st_uid != os.getuid() or (dinfo.st_mode & 0o077)):
            raise GuardError("audit directory must be a real directory owned by the current "
                             "user and mode 0700: %s" % directory)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(log_path, flags, 0o600)
    except OSError as err:
        raise GuardError("cannot securely open audit log %s: %s" % (log_path, err))
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or (info.st_mode & 0o077):
        os.close(fd)
        raise GuardError("audit log must be a regular file owned by the current user and mode 0600: %s"
                         % log_path)
    return fd

def log_event(log_path, fields):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {"timestamp": stamp, "pid": os.getpid(), "source": invocation_source()}
    record.update(fields)
    fd = secure_log_fd(log_path)
    with os.fdopen(fd, "a") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record

def elapsed_ms(start):
    """Return a rounded monotonic duration suitable for non-sensitive diagnostics."""
    return int(round((time.monotonic() - start) * 1000))

# ------------------------------------------------------------------------------- host pinning
# Every URL this tool builds comes from canvas_url(). A path carrying a scheme, a netloc or a
# ".." segment is refused: it could otherwise send the Authorization header off-host. And the
# host itself is pinned to the fixed, administrator-owned config file, so no command-line flag
# can point a request at another host.
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
        raise GuardError("no Canvas host configured in %s" % CONFIG_PATH)
    if "://" in host or "/" in host or "@" in host or any(c.isspace() for c in host):
        raise GuardError("invalid Canvas host: %r" % host)
    url = "https://" + host + normalise_path(path)
    check = urllib.parse.urlsplit(url)
    if check.scheme != "https" or check.netloc != host:
        raise GuardError("refusing a URL that leaves the pinned host: %r" % url)
    return url

# -------------------------------------------------------------------- the one request function
# There is exactly one call to urlopen in this file. Everything else routes through here, and
# the URL it opens is the one canvas_url() built: urllib would otherwise follow a redirect and
# forward the Authorization header to the new location, another host or an http:// downgrade
# included, so every redirect is refused instead.
class RefuseRedirects(urllib.request.HTTPRedirectHandler):
    """Installed as the opener below: no redirect is ever followed."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GuardError("refusing to follow a redirect (%s) to %r: the token is sent only to "
                         "the pinned URL" % (code, newurl))


class CredentialFreeRedirects(urllib.request.HTTPRedirectHandler):
    """Follow Canvas-issued attachment redirects only after stripping every sensitive header."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise GuardError("refusing a non-HTTPS or malformed attachment redirect")
        clean_headers = dict((name, value) for name, value in req.header_items()
                             if name.lower() not in ("authorization", "cookie", "proxy-authorization"))
        return urllib.request.Request(newurl, headers=clean_headers, method="GET")

urllib.request.install_opener(urllib.request.build_opener(RefuseRedirects))
_CREDENTIAL_FREE_OPENER = urllib.request.build_opener(CredentialFreeRedirects)

def open_request(request, credential_free_redirects=False):
    """Open a pinned authenticated request, or a Canvas-issued credential-free attachment URL."""
    if credential_free_redirects:
        return _CREDENTIAL_FREE_OPENER.open(request, timeout=TIMEOUT)
    return urllib.request.urlopen(request, timeout=TIMEOUT)

def send_request(cfg, method, path, body=None):
    """Perform an authenticated request to the pinned Canvas host and log before it does."""
    started = time.monotonic()
    method = method.upper()
    url, npath = canvas_url(cfg.host, path), normalise_path(path)
    is_write = method in WRITE_METHODS
    audit_started = time.monotonic()
    log_event(cfg.log_path, {
        "event": "request", "verb": method, "path": npath, "url": url,
        "kind": "write" if is_write else "read", "dry_run": cfg.dry_run,
        "confirmation": cfg.confirmation, "request_body": body if is_write else None})
    request_audit_ms = elapsed_ms(audit_started)
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
    credential_started = time.monotonic()
    headers["Authorization"] = "Bearer " + read_token()                   # the only use
    credential_ms = elapsed_ms(credential_started)
    request = urllib.request.Request(url, data=payload, headers=headers, method=method)
    network_started = time.monotonic()
    try:
        raw = open_request(request)
        status, head, text = raw.status, dict(raw.headers), raw.read()
        raw.close()
    except Exception as err:                       # HTTPError, DNS, TLS, timeout, ...
        status = getattr(err, "code", None)
        timing_ms = {"request_audit": request_audit_ms, "credential": credential_ms,
                     "network": elapsed_ms(network_started),
                     "total_before_response_audit": elapsed_ms(started)}
        log_event(cfg.log_path, {"event": "response", "verb": method, "path": npath, "ok": False,
                                 "status": status, "error": type(err).__name__,
                                 "timing_ms": timing_ms})
        raise RequestFailure("%s %s failed: %s: %s"
                             % (method, url, type(err).__name__, err), status=status)
    timing_ms = {"request_audit": request_audit_ms, "credential": credential_ms,
                 "network": elapsed_ms(network_started),
                 "total_before_response_audit": elapsed_ms(started)}
    log_event(cfg.log_path, {"event": "response", "verb": method, "path": npath,
                             "status": status, "ok": True, "bytes": len(text),
                             "timing_ms": timing_ms})
    try:
        data = json.loads(text.decode("utf-8")) if text else None
    except ValueError:
        data = None
    return {"status": status, "headers": head, "data": data, "timing_ms": timing_ms}

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
        # Canvas accepts submission[excuse] but returns the state as "excused".
        response_leaf = "excused" if leaf == "excuse" else leaf
        got_after = after.get(response_leaf) if isinstance(after, dict) else None
        rows.append({"field": leaf, "requested": flat[dotted], "after": got_after,
                     "before": before.get(response_leaf) if isinstance(before, dict) else None,
                     "match": None if not isinstance(after, dict)
                     else str(got_after) == str(flat[dotted])})
    return rows


def selected_changes(changes, fields):
    """Limit verification only when a reviewed specialized operation names stable fields."""
    if not fields:
        return changes
    wanted = {field.strip() for field in fields.split(",") if field.strip()}
    if not wanted:
        raise GuardError("verification field list is empty")
    selected = [row for row in changes if row["field"] in wanted]
    if not selected:
        raise GuardError("none of the requested verification fields occur in the request body")
    return selected

def summarise(obj, limit=10):
    return dict((k, obj[k]) for k in sorted(obj)[:limit]) if isinstance(obj, dict) else None

def target_identity(*objects):
    """Return the student/user identity Canvas supplied, for human and audit evidence.

    Canvas submission responses normally expose user_id and may include a user object when
    include[]=user is requested. A name is never guessed from another field.
    """
    identity = {}
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        user = obj.get("user") if isinstance(obj.get("user"), dict) else {}
        if identity.get("user_id") is None:
            identity["user_id"] = user.get("id", obj.get("user_id"))
        if not identity.get("student_name"):
            identity["student_name"] = (user.get("name") or user.get("display_name")
                                        or user.get("sortable_name"))
    return dict((key, value) for key, value in identity.items() if value is not None)

def uncertain(cfg, evidence, reason):
    """Record the failed verification and return a non-success outcome to the caller."""
    evidence["verification"] = "failed"
    evidence["note"] = "WRITE STATUS UNCERTAIN: " + reason
    emit(cfg, evidence)
    raise VerificationFailure(evidence["note"])

def next_link(headers, host):
    """Canvas paginates lists with a Link header. Return the rel="next" URL's path and query,
    pinned to the host, or None. Raises GuardError if that link leaves the pinned host.
    Nothing is followed automatically."""
    link = headers.get("Link") or headers.get("link") or ""
    match = re.search(r'<([^>]+)>\s*;\s*rel="?next"?', link)
    if not match:
        return None
    parsed = urllib.parse.urlsplit(match.group(1))
    if parsed.netloc != host:
        raise GuardError("next-page link points off the pinned host: %r" % parsed.netloc)
    return parsed.path + (("?" + parsed.query) if parsed.query else "")

def emit(cfg, ev):
    """Render the evidence, and record a short form of it (before/after) in the log."""
    log_event(cfg.log_path, {"event": "evidence", "verb": ev.get("verb"), "note": ev.get("note"),
                             "path": ev.get("path"), "status": ev.get("status"),
                             "confirmation": ev.get("confirmation"),
                             "verification": ev.get("verification"),
                             "target": ev.get("target"), "changes": ev.get("changes"),
                             "timing_ms": ev.get("timing_ms")})
    if cfg.out == "json":
        print(json.dumps(ev, indent=2, sort_keys=True, default=str))
        return
    for key in ("verb", "path", "url", "confirmation", "status", "verification", "note",
                "count", "pages", "next", "timing_ms"):
        if ev.get(key) is not None:
            print("%-14s %s" % (key + ":", ev[key]))
    if ev.get("target"):
        print("%-14s %s" % ("target:", json.dumps(ev["target"], sort_keys=True)))
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
          "status": resp["status"] if resp else None,
          "timing_ms": resp.get("timing_ms") if resp else None}
    if resp and isinstance(resp["data"], list):
        count = len(resp["data"])
        ev["note"] = "%d item%s returned" % (count, "" if count == 1 else "s")
        ev["items"] = resp["data"]
        try:
            ev["next"] = next_link(resp["headers"], cfg.host)
        except GuardError as err:
            ev["next"], ev["note"] = None, ev["note"] + "; " + str(err)
    elif resp:
        # Text output stays compact for a human, while a root-owned specialized operation that
        # asks for JSON can validate fields Canvas places beyond the first display summary.
        ev["object"] = resp["data"] if cfg.out == "json" else summarise(resp["data"])
    emit(cfg, ev)

def do_count(cfg, path, body):
    """GET every same-host page and return one count, avoiding agent-side shell parsing."""
    if cfg.dry_run:
        send_request(cfg, "GET", path)
        return
    first_path, current = normalise_path(path), path
    seen, total, pages, status = set(), 0, 0, None
    while current:
        normalised = normalise_path(current)
        if normalised in seen:
            raise GuardError("pagination loop detected at %s" % normalised)
        seen.add(normalised)
        resp = send_request(cfg, "GET", current)
        status = resp["status"]
        if not isinstance(resp["data"], list):
            raise GuardError("count requires a Canvas list response at %s" % normalised)
        total += len(resp["data"])
        pages += 1
        current = next_link(resp["headers"], cfg.host)
    emit(cfg, {"verb": "COUNT", "path": first_path, "url": canvas_url(cfg.host, path),
               "status": status, "note": "all Canvas pages counted",
               "count": total, "pages": pages})

def secure_review_dir():
    """Return the user-private persistent review directory without following a link."""
    try:
        info = os.lstat(REVIEW_DIR)
    except FileNotFoundError:
        os.makedirs(REVIEW_DIR, 0o700)
        info = os.lstat(REVIEW_DIR)
    except OSError as err:
        raise GuardError("cannot inspect submission review directory: %s" % err)
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or info.st_uid != os.getuid() or (info.st_mode & 0o077)):
        raise GuardError("submission review directory must be user-owned mode 0700: %s" % REVIEW_DIR)
    return REVIEW_DIR

def numeric_id(value, label):
    if not str(value).isdigit() or int(value) < 1:
        raise GuardError("%s must be a positive Canvas numeric ID" % label)
    return str(value)

def safe_download_suffix(value):
    if not re.fullmatch(r"\.[A-Za-z0-9]{1,16}", value or ""):
        raise GuardError("download suffix must be a simple extension of at most 16 letters or digits")
    return value.lower()

def do_download_submission_file(cfg, file_id, submission_id, suffix):
    """Download one Canvas-authorized submission attachment, never forwarding the token."""
    file_id, submission_id = numeric_id(file_id, "file ID"), numeric_id(submission_id, "submission ID")
    suffix = safe_download_suffix(suffix)
    metadata = send_request(cfg, "GET", "files/%s/public_url?submission_id=%s" % (file_id, submission_id))
    public_url = (metadata.get("data") or {}).get("public_url")
    parsed = urllib.parse.urlsplit(public_url or "")
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise GuardError("Canvas did not return a usable HTTPS submission download URL")
    directory = secure_review_dir()
    fd, output = tempfile.mkstemp(prefix="canvas-submission-", suffix=suffix, dir=directory)
    digest, total = hashlib.sha256(), 0
    try:
        log_event(cfg.log_path, {"event": "download", "kind": "read", "file_id": file_id,
                                 "submission_id": submission_id, "confirmation": None})
        request = urllib.request.Request(public_url, headers={"User-Agent": USER_AGENT}, method="GET")
        raw = open_request(request, credential_free_redirects=True)
        with os.fdopen(fd, "wb") as handle:
            fd = None
            while True:
                chunk = raw.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > 50 * 1024 * 1024:
                    raise GuardError("submitted attachment exceeds the 50 MiB review limit")
                digest.update(chunk)
                handle.write(chunk)
            handle.flush(); os.fsync(handle.fileno())
        raw.close()
    except Exception as err:
        if fd is not None:
            os.close(fd)
        try: os.unlink(output)
        except OSError: pass
        log_event(cfg.log_path, {"event": "download-response", "kind": "read", "file_id": file_id,
                                 "submission_id": submission_id, "ok": False, "error": type(err).__name__})
        # Network exceptions can embed an expiring signed URL. Preserve only the exception class.
        raise GuardError("submission attachment download failed (%s)" % type(err).__name__)
    log_event(cfg.log_path, {"event": "download-response", "kind": "read", "file_id": file_id,
                             "submission_id": submission_id, "ok": True, "bytes": total,
                             "sha256": digest.hexdigest()})
    emit(cfg, {"verb": "DOWNLOAD", "path": "/api/v1/files/%s/public_url" % file_id,
               "note": "submitted attachment saved for local review", "object": {"path": output,
               "bytes": total, "sha256": digest.hexdigest(), "file_id": int(file_id),
               "submission_id": int(submission_id)}})

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
    evidence = {"verb": method, "path": normalise_path(path), "body": body,
                "url": canvas_url(cfg.host, path), "confirmation": cfg.confirmation,
                "status": resp["status"] if resp else None}
    if cfg.dry_run:
        evidence.update({"changes": compare_fields(body, before_obj, None),
                         "verification": "not-run", "note": "dry run: nothing was sent"})
        emit(cfg, evidence)
        return
    try:
        after = send_request(cfg, "GET", path)
    except RequestFailure as err:
        evidence["target"] = target_identity(before_obj, resp.get("data") if resp else None)
        uncertain(cfg, evidence, "the write returned, but read-back failed: %s" % err)
    after_obj = after["data"]
    evidence["target"] = target_identity(before_obj, resp.get("data"), after_obj)
    evidence["changes"] = selected_changes(compare_fields(body, before_obj, after_obj),
                                             cfg.verify_fields)
    mismatches = [row["field"] for row in evidence["changes"] if row["match"] is not True]
    if mismatches:
        uncertain(cfg, evidence, "read-back did not match requested field(s): %s"
                  % ", ".join(mismatches))
    evidence["verification"] = "passed"
    emit(cfg, evidence)

def template_value(data, template):
    """Resolve a dot-separated response field for an explicit POST read-back template."""
    value = data
    for part in template.split("."):
        if not part or not isinstance(value, dict) or part not in value:
            raise GuardError("POST read-back template did not resolve %r" % template)
        value = value[part]
    if not isinstance(value, (str, int)) or not str(value):
        raise GuardError("POST read-back template resolved to an invalid path value")
    return urllib.parse.quote(str(value), safe="-._~")


def post_read_path(cfg, path, response, readback_template):
    """Choose the exact object to verify after a create, never following another host."""
    if readback_template:
        if readback_template.count("{value}") != 1:
            raise GuardError("POST read-back template must contain exactly one {value} placeholder")
        try:
            read_path = readback_template.format(
                value=template_value(response["data"], cfg.post_readback_field))
        except (KeyError, IndexError, ValueError) as err:
            raise GuardError("invalid POST read-back template: %s" % err)
        canvas_url(cfg.host, read_path)
        return read_path
    location = response["headers"].get("Location") or response["headers"].get("location")
    new_id = response["data"].get("id") if isinstance(response["data"], dict) else None
    if new_id is not None:
        return normalise_path(path).split("?")[0] + "/" + str(new_id)
    if location:
        parsed = urllib.parse.urlsplit(location)
        if parsed.netloc and parsed.netloc != cfg.host:
            raise GuardError("Location header points off the pinned host: %s" % parsed.netloc)
        return parsed.path + (("?" + parsed.query) if parsed.query else "")
    return None


def do_post(cfg, path, body):
    """POST: nothing exists before, so show the body, confirm, write, read the new object."""
    if body is None:
        raise GuardError("post needs a JSON body: -d '{\"...\": ...}'")
    cfg.confirmation = confirm(cfg, [
        "about to POST %s" % canvas_url(cfg.host, path), "request body:",
        "  " + json.dumps(body, sort_keys=True),
        "nothing exists before a POST; the created object is read back afterwards"])
    resp = send_request(cfg, "POST", path, body)
    evidence = {"verb": "POST", "path": normalise_path(path), "body": body,
                "url": canvas_url(cfg.host, path), "confirmation": cfg.confirmation,
                "status": resp["status"] if resp else None}
    if cfg.dry_run:
        evidence.update({"verification": "not-run", "note": "dry run: nothing was sent"})
        emit(cfg, evidence)
        return
    try:
        read_path = post_read_path(cfg, path, resp, cfg.post_readback)
    except GuardError as err:
        uncertain(cfg, evidence, str(err))
    if not read_path:
        uncertain(cfg, evidence, "Canvas returned neither an id nor a usable Location header; "
                  "the created object could not be read back")
    try:
        back = send_request(cfg, "GET", read_path)
    except RequestFailure as err:
        evidence["target"] = target_identity(resp.get("data"))
        uncertain(cfg, evidence, "the create returned, but read-back at %s failed: %s"
                  % (read_path, err))
    created = summarise(back["data"])
    if created is None:
        uncertain(cfg, evidence, "read-back at %s was not a Canvas object" % read_path)
    expected = body
    if cfg.post_verify_field:
        if not isinstance(body, dict) or not isinstance(body.get(cfg.post_verify_field), dict):
            raise GuardError("POST verification field is not an object in the request body: %s"
                             % cfg.post_verify_field)
        expected = body[cfg.post_verify_field]
    evidence.update({"object": created, "target": target_identity(resp["data"], back["data"]),
                     "changes": selected_changes(compare_fields(expected, None, back["data"]),
                                                 cfg.verify_fields)})
    mismatches = [row["field"] for row in evidence["changes"] if row["match"] is not True]
    if mismatches:
        uncertain(cfg, evidence, "created object did not match requested field(s): %s"
                  % ", ".join(mismatches))
    evidence["verification"] = "passed"
    emit(cfg, evidence)

def do_delete(cfg, path, body):
    """DELETE: read first, so the confirmation shows what is about to be destroyed."""
    before = send_request(cfg, "GET", path)
    before_obj = summarise(before["data"]) if before else None
    cfg.confirmation = confirm(cfg, [
        "about to DELETE %s" % canvas_url(cfg.host, path),
        "this object is about to be destroyed:",
        "  " + json.dumps(before_obj, sort_keys=True, default=str)])
    resp = send_request(cfg, "DELETE", path, body)
    evidence = {"verb": "DELETE", "path": normalise_path(path), "object": before_obj,
                "target": target_identity(before["data"] if before else None),
                "url": canvas_url(cfg.host, path), "confirmation": cfg.confirmation,
                "status": resp["status"] if resp else None}
    if cfg.dry_run:
        evidence.update({"verification": "not-run", "note": "dry run: nothing was deleted"})
        emit(cfg, evidence)
        return
    try:
        send_request(cfg, "GET", path)
    except RequestFailure as err:
        if err.status == 404:
            evidence.update({"verification": "passed", "note": "read-back after delete: 404 gone"})
            emit(cfg, evidence)
            return
        uncertain(cfg, evidence, "the delete returned, but read-back failed with %s" % err)
    uncertain(cfg, evidence, "read-back after delete still returned the object")

VERBS = {"get": do_get, "count": do_count, "post": do_post, "delete": do_delete,
         "put": lambda c, p, b: do_update(c, "PUT", p, b),
         "patch": lambda c, p, b: do_update(c, "PATCH", p, b)}

# ---------------------------------------------------------------------------------- argparse
def make_config(args):
    """What send_request needs. confirmation is set by confirm() before any write."""
    configured = read_config()
    return argparse.Namespace(host=configured["host"], profile=configured["profile"],
                              out=args.output, log_path=DEFAULT_LOG, dry_run=args.dry_run,
                              yes=args.yes, confirmation=None, post_readback=args.post_readback,
                              post_readback_field=args.post_readback_field,
                              post_verify_field=args.post_verify_field,
                              verify_fields=args.verify_fields)

def read_config():
    """Read the fixed config after checking that untrusted users cannot modify it."""
    parent = os.path.dirname(CONFIG_PATH)
    try:
        parent_info = os.lstat(parent)
        info = os.lstat(CONFIG_PATH)
    except OSError:
        raise GuardError("no Canvas configuration at %s; run the reviewed installer with --host"
                         % CONFIG_PATH)
    if (not stat.S_ISDIR(parent_info.st_mode) or stat.S_ISLNK(parent_info.st_mode)
            or parent_info.st_uid not in (0, os.getuid()) or (parent_info.st_mode & 0o022)):
        raise GuardError("Canvas configuration directory must be a real directory owned by root "
                         "or the current user and not writable by group or others: %s" % parent)
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise GuardError("Canvas configuration must be a regular file, not a link: %s" % CONFIG_PATH)
    if info.st_uid not in (0, os.getuid()) or (info.st_mode & 0o022):
        raise GuardError("Canvas configuration must be owned by root or the current user and "
                         "not writable by group or others: %s" % CONFIG_PATH)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(CONFIG_PATH, flags)
        opened = os.fstat(fd)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != info.st_uid
                or opened.st_dev != info.st_dev or opened.st_ino != info.st_ino
                or opened.st_mode & 0o022):
            os.close(fd)
            raise GuardError("Canvas configuration changed during validation: %s" % CONFIG_PATH)
        with os.fdopen(fd) as handle:
            configured = json.load(handle)
    except GuardError:
        raise
    except (OSError, ValueError) as err:
        raise GuardError("cannot read Canvas configuration %s: %s" % (CONFIG_PATH, err))
    if not isinstance(configured, dict):
        raise GuardError("Canvas configuration must be a JSON object: %s" % CONFIG_PATH)
    host = configured.get("host")
    canvas_url(host, "courses")                 # validate without reading a token or networking
    profile = configured.get("profile", "level-1")
    if profile not in ("level-1", "level-2"):
        raise GuardError("unsupported policy profile %r" % profile)
    return {"host": host, "profile": profile}

def build_parser():
    parser = argparse.ArgumentParser(prog="canvas_api_guard.py", description=(
        "Audited passthrough to the Canvas REST API: confirmation, evidence and an "
        "append-only log. It adds no capability the Canvas token did not already have."))
    parser.add_argument("--version", action="version", version=USER_AGENT)
    parser.add_argument("--set-token", action="store_true", help="store a token, then exit")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("path", help="/api/v1/courses/123, api/v1/courses/123 or courses/123")
    common.add_argument("-d", "--data", help="JSON object to send as the request body")
    common.add_argument("--dry-run", action="store_true", help="print the request, send nothing")
    common.add_argument("--yes", action="store_true", help="confirm a write non-interactively")
    common.add_argument("--post-readback", metavar="PATH{value}",
                        help="POST only: exact pinned-host read-back path; {value} is filled "
                             "from the Canvas response field named by --post-readback-field")
    common.add_argument("--post-readback-field", default="id", metavar="FIELD",
                        help="POST only: dot-separated Canvas response field for {value} (default: id)")
    common.add_argument("--post-verify-field", metavar="FIELD",
                        help="POST only: verify this object inside the request body against read-back")
    common.add_argument("--verify-fields", metavar="FIELD[,FIELD...]",
                        help="verify only these requested leaf fields after a write")
    common.add_argument("-o", "--output", choices=("text", "json"), default="text")
    subs = parser.add_subparsers(dest="verb")
    for name in sorted(VERBS):
        subs.add_parser(name, parents=[common], help="%s a Canvas path" % name)
    download = subs.add_parser("download-submission-file", help="download one submitted attachment for local review")
    download.add_argument("--file-id", required=True)
    download.add_argument("--submission-id", required=True)
    download.add_argument("--suffix", default=".bin", help="safe local filename extension, for example .pdf")
    download.add_argument("-o", "--output", choices=("text", "json"), default="json")
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
        if args.verb == "download-submission-file":
            cfg = make_config(argparse.Namespace(output=args.output, dry_run=False, yes=False,
                                                  post_readback=None, post_readback_field="id",
                                                  post_verify_field=None, verify_fields=None))
            do_download_submission_file(cfg, args.file_id, args.submission_id, args.suffix)
            return 0
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
