"""
Outliers Gather - Layer 5 - The Timetable

Everything you have built so far runs when you type the command. This layer runs
it when you are not there.

    python install.py

It finds the CRM you built, asks you a few questions, and installs the layer into
it.

Nothing here reaches the outside world. It writes files, asks the questions, and
stops. It starts no command and it will not put a window on your screen, now or
ever - which is the single detail this layer is most careful about.

This is the piece of the set with nothing to do with any particular website, so
it is the piece you will still be using long after the rest. It runs ANY command
on a schedule.

Needs: Python 3.8 or newer. Nothing else.
"""

import json
import os
import shutil
import sys
from pathlib import Path

# What a member types to start Python. A Mac has `python3` and no plain `python`; Windows
# keeps `python`, exactly as before.
PY = "python3" if sys.platform == "darwin" else "python"

# How starting by itself is said. On a Mac it "starts by itself when you switch on your Mac and sign in":
# "log in" reads as needing an account (Mac build plan V3, wave s2: the Session 7 ruling on the words
# installers print). Windows keeps its words, exactly as before.
# The question keeps its Windows words as the first literal in the ask_yes call, because the Gather guide
# checker (check_repo_matches_guide.py) reads the installer's questions out of this source.
if sys.platform == "darwin":
    AT_LOGIN_LATER = "  and set it to start by itself later with:"
else:
    AT_LOGIN_LATER = "  and set it to start at login later with:"

LAYER = 5
LAYER_NAME = "The Timetable"
SERIES = "Gather"

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "engine"

# crm_paths and safe_write are shared with your CRM and are IDENTICAL there. They
# are only written if missing, never overwritten, so installing this can never
# replace one of your existing files with a narrower version of itself.
SHARED = ["crm_paths.py", "safe_write.py"]
MINE = ["timetable_platform.py", "timetable_store.py", "timetable_clock.py",
        "timetable_runner.py", "timetable_daemon.py", "timetable.py"]


# No colour codes anywhere. Plenty of terminals print them as literal gibberish and
# a member's first minute with this must not look broken.
def say(msg=""):
    print(msg, flush=True)


def ask(question, default=None, helptext=None):
    say()
    say(question)
    if helptext:
        say("  " + helptext)
    prompt = "  > " if default is None else "  [%s] > " % default
    try:
        answer = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        say("\nStopped. Nothing was changed.")
        sys.exit(1)
    return answer or (default or "")


def ask_yes(question, default="yes", helptext=None):
    answer = ask(question, default=default, helptext=helptext)
    return str(answer).strip().lower().startswith("y")


# ------------------------------------------------------------- finding your CRM

def config_path(home):
    return Path(home) / "_layers" / "config.json"


def looks_like_a_crm(home):
    try:
        return config_path(home).exists()
    except OSError:
        return False


def find_vault():
    """Find the CRM you built, by looking for its config file."""
    tried = []
    env = os.environ.get("OUTLIERS_CRM")
    if env:
        tried.append(Path(env).expanduser())
    pointer = Path.home() / ".outliers-crm"
    if pointer.exists():
        try:
            noted = pointer.read_text(encoding="utf-8").strip()
            if noted:
                tried.append(Path(noted))
        except OSError:
            pass
    tried.append(Path.home() / "CRM")
    here = Path.cwd()
    tried.append(here)
    tried.extend(here.parents)

    for candidate in tried:
        if looks_like_a_crm(candidate):
            return Path(candidate)

    say()
    say("  Could not find your CRM automatically.")
    raw = ask("Where is it?", default=str(Path.home() / "CRM"),
              helptext="The folder your first layer built. It has a _layers folder inside it.")
    candidate = Path(raw.strip().strip('"').strip("'")).expanduser()
    return candidate if looks_like_a_crm(candidate) else None


def refuse(reason, fix=None):
    say()
    say("=" * 66)
    say("  Not yet.")
    say("=" * 66)
    say()
    say("  " + reason)
    if fix:
        say()
        say("  " + fix)
    say()
    sys.exit(1)


# --------------------------------------------------------------------- the work

def install_modules(engine_dir):
    engine_dir.mkdir(parents=True, exist_ok=True)
    written, kept = [], []
    for name in SHARED:
        target = engine_dir / name
        if target.exists():
            kept.append(name)
            continue
        shutil.copy2(ENGINE / name, target)
        written.append(name)
    for name in MINE:
        shutil.copy2(ENGINE / name, engine_dir / name)
        written.append(name)
    return written, kept


def load_installed(engine_dir):
    """Import the modules written a moment ago, from where they now live."""
    sys.path.insert(0, str(engine_dir))
    import timetable_store as store                           # noqa: E402
    import timetable_platform as machine                      # noqa: E402
    return store, machine


def main():
    say()
    say("=" * 66)
    say("  Outliers %s - Layer %d - %s" % (SERIES, LAYER, LAYER_NAME))
    say("=" * 66)
    say()
    say("  This installs a timetable that runs any command you like, on a")
    say("  schedule, while you are doing something else. It knows nothing about")
    say("  any website, which is why it outlasts the rest of the set.")
    say()
    say("  Nothing here reaches the outside world, and nothing here will ever put")
    say("  a window on your screen.")

    home = find_vault()
    if not home:
        refuse("That folder does not look like your CRM - there is no _layers folder inside it.",
               "Install the first layer of your CRM before this one.")

    engine_dir = Path(home) / "_engine"
    say()
    say("  Found your CRM: %s" % home)

    say()
    say("-" * 66)
    say("  One entry. Once a day. Watched.")
    say("-" * 66)
    say()
    say("  A timetable of six entries built in one sitting is six ways to be wrong")
    say("  at once, and no way to tell which one went wrong. So the first step is")
    say("  one entry, running once a day, that you read the log of for a week.")

    command = ask("What is the first command you want it to run?",
                  default="",
                  helptext="Exactly as you would type it in a terminal. Leave it empty "
                           "to install with an empty timetable and add one later.")
    at, days, label = "09:30", "mon,tue,wed,thu,fri", ""
    if command.strip():
        at = ask("At what time?", default="09:30",
                 helptext="On the 24-hour clock. The actual minute moves by a few "
                          "minutes each day, worked out from the entry's name and the "
                          "date, so it never lands on the same minute twice running.")
        days = ask("On which days?", default="mon,tue,wed,thu,fri",
                   helptext="Comma separated. A missed day still runs up to two hours "
                            "late, so a laptop asleep at nine still runs the nine "
                            "o'clock entry when it wakes at ten.")
        label = ask("What would you call it?", default=command.strip()[:40],
                    helptext="A short description, for you, when you read the list in "
                             "three months.")

    if sys.platform == "darwin":
        at_login_help = ("It is a LaunchAgent: a small file in your ~/Library/LaunchAgents "
                         "folder that tells your Mac to start the timetable by itself when you "
                         "switch on your Mac and sign in. "
                         "It does not ask for an administrator password, and it puts "
                         "nothing on your screen.")
    else:
        at_login_help = ("On Windows this is a logon task pointed at the copy of "
                         "Python that has no console window. On a Mac it is a "
                         "LaunchAgent. Neither asks for an administrator "
                         "password, and neither puts anything on your screen.")
    at_login = ask_yes("Should it start every time you log in?" if sys.platform != "darwin" else
                       "Should it start by itself when you switch on your Mac and sign in?",
                       default="yes",
                       helptext=at_login_help)

    written, kept = install_modules(engine_dir)
    store, machine = load_installed(engine_dir)

    added = None
    if command.strip():
        try:
            added = store.add(command=command.strip(), at=at, days=days,
                              label=label or None)
        except ValueError as err:
            say()
            say("  I could not add that entry: %s" % err)
            say("  Everything else installed. Add it by hand when you are ready.")

    startup_note, startup_worked = "", True
    if at_login:
        store.work_dir().mkdir(parents=True, exist_ok=True)
        startup_worked, startup_note = machine.install_startup(
            engine_dir / "timetable.py", store.work_dir(), store.log_path())

    # A record of what you chose, beside your other answers.
    whole = {}
    try:
        whole = json.loads(config_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        whole = {}
    whole["timetable"] = {"start-at-login": bool(at_login and startup_worked)}
    config_path(home).parent.mkdir(parents=True, exist_ok=True)
    config_path(home).write_text(json.dumps(whole, indent=2), encoding="utf-8")

    say()
    say("-" * 66)
    say("  Installed.")
    say("-" * 66)
    say()
    say("  Written into %s:" % engine_dir)
    for n in written:
        say("    %s" % n)
    for n in kept:
        say("    %s (already there, left alone)" % n)
    say()
    say("  Your timetable is %s" % store.timetable_path())
    say("  What it does is written to %s" % store.log_path())

    if added:
        say()
        say("  One entry is on it, called %r:" % added["id"])
        say("    %s" % added["command"])
        say("    %s on %s" % (added["at"], ", ".join(added["days"])))
    else:
        say()
        say("  The timetable is empty. Nobody should inherit a schedule they did")
        say("  not write, so it arrives with nothing on it.")

    if startup_note:
        say()
        say("  " + startup_note.replace("\n", "\n  "))
        if not startup_worked:
            say("  Everything else installed. Start it by hand when you want it going,")
            say(AT_LOGIN_LATER)
            say("      %s timetable.py install-startup" % PY)

    say()
    say("  Now, in a terminal in that _engine folder:")
    say()
    say("      %s timetable.py run --dry-run" % PY)
    say()
    say("  That shows what today holds and starts nothing at all. Read it, then:")
    say()
    say("      %s timetable.py start" % PY)
    say()
    say("  Nothing appears on screen when it starts, and nothing appears when an")
    say("  entry fires. That is the whole design. Watch it through the log and")
    say("  through:")
    say()
    say("      %s timetable.py status" % PY)
    say()
    return 0


if __name__ == "__main__":
    sys.exit(main())
