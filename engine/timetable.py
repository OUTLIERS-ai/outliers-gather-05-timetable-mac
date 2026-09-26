"""
timetable.py - the one command you type. It runs any command you like, on a
schedule, without a window.

    python timetable.py list
    python timetable.py add "<command>" --at 09:30 --days mon,tue,wed,thu,fri
    python timetable.py remove <id>
    python timetable.py enable <id>
    python timetable.py disable <id>
    python timetable.py run
    python timetable.py run --dry-run
    python timetable.py start
    python timetable.py stop
    python timetable.py status
    python timetable.py install-startup

Run it from the `_engine` folder inside your CRM, which is where the installer
put it, alongside the tools your earlier layers installed.

This layer knows nothing about any website, and that is why it is the piece of
the set you will still be using in two years. It starts commands. What those
commands do is entirely their own affair, and every limit and refusal they carry
still applies, because this starts them exactly as you would from a terminal.

    START WITH ONE ENTRY, ONCE A DAY.

Add one, watch it for a few days, read the log. A timetable of six entries built
in one sitting is six ways to be wrong at once, and no way to tell which one
went wrong.

Needs: Python 3.8 or newer. Nothing else.
"""

import sys
from datetime import datetime
from pathlib import Path

# What a member types to start Python. A Mac has `python3` and no plain `python`; Windows
# keeps `python`, exactly as before.
PY = "python3" if sys.platform == "darwin" else "python"

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import crm_paths                                              # noqa: E402
import timetable_clock as clock                               # noqa: E402
import timetable_daemon as daemon                             # noqa: E402
import timetable_platform as machine                          # noqa: E402
import timetable_store as store                               # noqa: E402


def say(text=""):
    print(text, flush=True)


def rule():
    say("-" * 66)


# ---------------------------------------------------------- reading the flags

def flags(argv):
    """Read --name value pairs off the end of a command line."""
    out, loose, i = {}, [], 0
    while i < len(argv):
        piece = argv[i]
        if piece.startswith("--"):
            name = piece[2:]
            if "=" in name:
                name, value = name.split("=", 1)
                out[name] = value
            elif i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                out[name] = argv[i + 1]
                i += 1
            else:
                out[name] = True
        else:
            loose.append(piece)
        i += 1
    return out, loose


# ------------------------------------------------------------------ printing

def show_plan(rows, now):
    if not rows:
        say("  There is nothing on the timetable yet.")
        say()
        say("  Add one entry, running once a day, and watch it for a few days:")
        say()
        say('      %s timetable.py add "%s gather.py collect" \\' % (PY, PY))
        say('          --at 09:30 --days mon,tue,wed,thu,fri --label "Collect the list"')
        return
    # The id is never shortened to fit. It is what you type to remove or switch
    # off an entry, and a name printed shorter than it really is would be typed
    # back exactly as printed and refused.
    width = max([len(str(row["entry"].get("id", ""))) for row in rows] + [2])
    shape = "  %-" + str(width) + "s %-7s %-12s %s"
    say(shape % ("id", "at", "standing", "what it runs"))
    for row in rows:
        entry = row["entry"]
        moment = row["at"].strftime("%H:%M") if row["at"] else "--:--"
        say(shape % (entry.get("id", ""), moment, row["status"],
                     entry.get("command", "")[:60]))
        label = (entry.get("label") or "").strip()
        if label and label != entry.get("command"):
            say(shape % ("", "", "", label))
    say()
    say("  The minute is not the one you typed, and that is deliberate. Each entry")
    say("  moves by a few minutes, worked out from its name and today's date, so it")
    say("  never lands on the same minute two days running. Ask again in a minute")
    say("  and you will get the identical answer, because it is worked out rather")
    say("  than rolled.")
    say()
    say("  A missed entry still runs, up to %d minutes late. A laptop asleep at nine"
        % clock.LATE_WINDOW_MINUTES)
    say("  still runs the nine o'clock entry when it wakes at ten.")


def cmd_list():
    now = datetime.now()
    rows = clock.plan(when=now)
    say()
    say("TODAY, %s" % now.strftime("%A %d %B %Y"))
    rule()
    show_plan(rows, now)
    state = daemon.health(now)
    say()
    say("THE BACKGROUND PROGRAM")
    rule()
    say("  %s" % state["word"])
    say("  timetable file      %s" % state["timetable"])
    say("  what it did         %s" % state["log"])
    say()
    return 0


def cmd_status():
    now = datetime.now()
    state = daemon.health(now)
    say()
    say("THE BACKGROUND PROGRAM")
    rule()
    say("  %s" % state["word"])
    if state["number"]:
        say("  process number      %d" % state["number"])
    if state["beat_age_minutes"] is not None:
        say("  last sign of life   %d minutes ago" % int(state["beat_age_minutes"]))
    say("  records system      %s" % crm_paths.vault())
    say("  timetable file      %s" % state["timetable"])
    say("  what it did         %s" % state["log"])
    say()
    entries = store.load()
    on = len([e for e in entries if e.get("enabled")])
    say("  %d entries, %d switched on" % (len(entries), on))
    if not state["number"]:
        say()
        say("  Nothing fires while it is not running. Start it with:")
        say("      %s timetable.py start" % PY)
    say()
    return 0


# ------------------------------------------------------------- changing it

def cmd_add(argv):
    options, loose = flags(argv)
    command = (loose[0] if loose else options.get("command", "")) or ""
    if not str(command).strip():
        say("  Tell me what to run, in quotes:")
        say('      %s timetable.py add "%s gather.py collect" --at 09:30 --days mon' % (PY, PY))
        return 2
    if "at" not in options:
        say("  Tell me when, with --at 09:30")
        return 2
    try:
        at = store.tidy_time(options["at"])
        days = store.tidy_days(options.get("days", "mon,tue,wed,thu,fri"))
    except ValueError as err:
        say("  %s" % err)
        return 2

    minutes = options.get("minutes")
    shift = options.get("shift")
    try:
        entry = store.add(
            command=command,
            at=at,
            days=days,
            label=options.get("label"),
            shift_minutes=None if shift in (None, True) else int(shift),
            allowed_minutes=None if minutes in (None, True) else int(minutes),
        )
    except (TypeError, ValueError) as err:
        say("  %s" % err)
        return 2

    now = datetime.now()
    moment = clock.fire_time(entry, now)
    say()
    say("  Added, as %r." % entry["id"])
    say("    runs           %s" % entry["command"])
    say("    at             %s on %s" % (entry["at"], ", ".join(entry["days"])))
    say("    today that is  %s" % (moment.strftime("%H:%M") if moment else "unreadable"))
    say("    may take       up to %d minutes" % entry["allowed-minutes"])
    say()
    say("  It fires a few minutes either side of %s, worked out from its name and" % entry["at"])
    say("  the date, so the same minute never comes round twice.")
    if not daemon.running_number():
        say()
        say("  The background program is not running, so nothing fires yet:")
        say("      %s timetable.py start" % PY)
    say()
    return 0


def cmd_remove(argv):
    if not argv:
        say("  Which one? Run: %s timetable.py list" % PY)
        return 2
    if store.remove(argv[0]):
        say("  Removed %r." % argv[0])
        return 0
    say("  There is no entry called %r. Run: %s timetable.py list" % (argv[0], PY))
    return 2


def cmd_switch(argv, on):
    if not argv:
        say("  Which one? Run: %s timetable.py list" % PY)
        return 2
    entry = store.set_enabled(argv[0], on)
    if not entry:
        say("  There is no entry called %r. Run: %s timetable.py list" % (argv[0], PY))
        return 2
    say("  %r is now switched %s." % (argv[0], "on" if on else "off"))
    if not on:
        say("  It stays on the timetable and stops firing. Nothing was thrown away.")
    return 0


# ----------------------------------------------------------------- running

def cmd_run(argv):
    options, _ = flags(argv)
    if options.get("dry-run") or options.get("dry_run"):
        return cmd_dry_run()
    return daemon.loop()


def cmd_dry_run():
    """Show what today holds and stop. Nothing is started.

    This reads the timetable and works out times. It has no route to starting a
    command at all, which is what makes it honest rather than a promise.
    """
    now = datetime.now()
    rows = clock.plan(when=now)
    say()
    say("A DRY RUN - nothing below is started")
    rule()
    show_plan(rows, now)
    say()
    coming = [r for r in rows if r["status"] in ("waiting", "due now")]
    if coming:
        say("  Still to come today:")
        for row in coming:
            say("    %s  %s" % (row["at"].strftime("%H:%M"), row["entry"].get("id")))
    else:
        say("  Nothing else is due today.")
    say()
    return 0


def cmd_start():
    say()
    say("  " + daemon.start().replace("\n", "\n  "))
    say()
    return 0


def cmd_stop():
    say()
    say("  " + daemon.stop())
    say()
    return 0


def cmd_install_startup(argv):
    options, _ = flags(argv)
    say()
    if options.get("remove"):
        worked, message = machine.remove_startup()
        say("  " + message)
        say()
        return 0 if worked else 1
    store.work_dir().mkdir(parents=True, exist_ok=True)
    worked, message = machine.install_startup(HERE / "timetable.py", store.work_dir(),
                                              store.log_path())
    say("  " + message.replace("\n", "\n  "))
    say()
    if not worked:
        say("  Nothing is set to start by itself. Everything else still works: start it" if machine.IS_MAC
            else "  Nothing is scheduled at login. Everything else still works: start it")
        say("  by hand with `%s timetable.py start` whenever you want it going." % PY)
        say()
        return 1
    if machine.IS_WINDOWS:
        say("  It is pointed at the copy of Python that has no console window, so")
        say("  nothing appears on screen when you log in. That single detail is the")
        say("  difference between a timetable people keep and one they switch off.")
    elif machine.IS_MAC:
        say("  Nothing appears on your screen when it runs: on a Mac, a program running in the")
        say("  background has no window to show.")
    say()
    say("  To undo it:  %s timetable.py install-startup --remove" % PY)
    say()
    return 0


USAGE = """timetable - run any command on a schedule, without a window

  %(py)s timetable.py list
  %(py)s timetable.py add "<command>" --at 09:30 --days mon,tue,wed,thu,fri [--label "..."]
  %(py)s timetable.py remove <id>
  %(py)s timetable.py enable <id>
  %(py)s timetable.py disable <id>
  %(py)s timetable.py run                  the loop itself, in this window
  %(py)s timetable.py run --dry-run        what today holds, starting nothing
  %(py)s timetable.py start                the loop, in the background, no window
  %(py)s timetable.py stop
  %(py)s timetable.py status
  %(py)s timetable.py install-startup      %(startup)s

  add also takes:
    --minutes N     how long this one may take before it is ended. Default 45.
                    A job that walks a long list needs more, and should say so.
    --shift N       how far its minute may move, either way. Default 4.

Run this from the _engine folder inside your CRM.
""" % {"py": PY,
       # wave s2: on a Mac it starts "when you switch on your Mac and sign in"; Windows keeps its words
       "startup": ("start it by itself when you switch on your Mac and sign in" if sys.platform == "darwin"
                   else "start it every time you log in")}


def main(argv):
    command = (argv[1] if len(argv) > 1 else "list").strip().lower()
    rest = argv[2:]
    if command in ("list", "ls"):
        return cmd_list()
    if command == "add":
        return cmd_add(rest)
    if command in ("remove", "rm"):
        return cmd_remove(rest)
    if command == "enable":
        return cmd_switch(rest, True)
    if command == "disable":
        return cmd_switch(rest, False)
    if command == "run":
        return cmd_run(rest)
    if command == "start":
        return cmd_start()
    if command == "stop":
        return cmd_stop()
    if command == "status":
        return cmd_status()
    if command in ("install-startup", "install_startup"):
        return cmd_install_startup(rest)
    if command in ("help", "-h", "--help"):
        say(USAGE)
        return 0
    say("I do not know the command %r." % command)
    say()
    say(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
