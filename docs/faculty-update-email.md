# Faculty email: install or update canvas-api-guard

A draft to send when a release is ready. Everything in it is what the installer does; keep it
in step with `install-from-github.sh` and the README's install section.

---

**Subject:** Canvas in ChatGPT: one command to install or update (about 3 minutes)

Hi all,

A new version of the Canvas helper for ChatGPT (Codex) is ready. This one adds rubric
grading with a private review window: Codex fills in the rubric and comments, nothing is
visible to students, and you release grades yourself with one click in Canvas when you have
looked them over.

**If you already have it installed**, the update is the same command as the install. Paste it
into Terminal (Applications, Utilities, Terminal), press Return, and follow the prompts:

    curl -fsSL https://raw.githubusercontent.com/chiptoe-svg/canvas-api-guard/release/install-from-github.sh | sh

It tells you what will change and asks for your Mac password once. It does not touch your
Canvas token. When it says Done, quit and reopen the ChatGPT app.

**If this is your first time**, two things come first:

1. Your Mac needs Apple's free Command Line Tools. In Terminal, paste
   `xcode-select --install`, click Install in the window that appears, and wait for it to
   finish (a few minutes). If your Mac already has them, it just says so.
2. Have a Canvas access token ready: in Canvas go to Account, Settings, scroll to Approved
   Integrations, click "+ New Access Token", and copy it. The installer opens that page for
   you and asks for the token at the end; it is stored in your Mac's Keychain and never shown
   again.

Then paste the same command above.

**If something stops it**, the message on screen says what to do; the most common one is
that the Command Line Tools were not installed yet, and the fix is step 1 above, then paste
the command again. Anything else, send me the last few lines of what Terminal showed.

Thanks,
[name]
