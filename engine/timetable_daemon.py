"""
timetable_daemon.py - the background program: the loop, the sign of life, and
knowing which running program is ours.

A background program is one that keeps running with no window and no terminal
attached to it, waking up regularly to see whether there is anything to do. This
one wakes every thirty seconds, asks the clock which entries are due, and starts
them one at a time.

THE SIGN OF LIFE IS WRITTEN THE INSTANT IT STARTS, AND AT THE TOP OF EVERY CYCLE

  A file with a timestamp in it is how anything outside can tell this is alive.
  The obvious place to write it is at the bottom of the loop, once the cycle's
  work is done. That is wrong, and on 2026-07-19 it cost two days.

  What happened: a freshly started background program had written its process
  number but not yet reached the bottom of its first cycle, so the sign-of-life
  file still carried the timestamp of the PREVIOUS run, which had died. The first
  job it fired was the checker. The checker read a live process number beside a
  timestamp hours old and reported "running, but hung". Nobody restarted it,
  because it looked as though restarting had already been tried. It was healthy
  the entire time.

  Being alive has to be asserted the moment the process number goes live, not
  after the first cycle of work. So it is written three times: at start-up before
  anything else, at the TOP of every cycle before any entry is started, and again
  after each entry finishes so that a cycle with several entries in it cannot age
  its own sign of life past the point of looking hung.

WHICH RUNNING PROGRAM IS OURS

  The file that records the running program holds two lines, not one: the process
  number, and the moment that program started. See `same_program` in
  timetable_platform.py for the day a reused number reported a dead job as
  running and refused to start the real one.

Needs: Python 3.8 or newer. Nothing else.
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import safe_write                                             # noqa: E402
import timetable_clock as clock                               # noqa: E402
import timetable_platform as machine                          # noqa: E402
import timetable_runner as runner                             # noqa: E402
import timetable_store as store                               # noqa: E402

# The shift on a firing time is measured in minutes, so waking twice a minute is
# more precision than the timetable needs and costs nothing at all.
WAKE_EVERY_SECONDS = 30

# A short pause between two entries that fall due together, so a heavy job is
# never starting while the last one is still letting go of what it held.
PAUSE_BETWEEN_SECONDS = 5

# Beyond this, the sign of life is old enough that something is wrong.
STALE_MINUTES = 15

SCRIPT = HERE / "timetable.py"


# ------------------------------------------------------------- sign of life

def beat(when=None):
    """Write the sign of life. Called at start-up, at the top of every cycle, and
    after every entry finishes. Never only at the end."""
    try:
        store.work_dir().mkdir(parents=True, exist_ok=True)
        safe_write.write_text(store.heartbeat_path(),
                              (when or datetime.now()).replace(microsecond=0).isoformat())
    except OSError:
        pass


def last_beat():
    """When the sign of life was last written, or None."""
    try:
        raw = store.heartbeat_path().read_text(encoding="utf-8").strip()
        return datetime.fromisoformat(raw)
    except (OSError, ValueError):
        return None


def beat_age_minutes(now=None):
    seen = last_beat()
    if seen is None:
        return None
    return max(0.0, ((now or datetime.now()) - seen).total_seconds() / 60.0)


# --------------------------------------------------- which program is running

def claim():
    """Write down that this program is the one running, and prove it is alive.

    The process number and the moment this program started go in together, and
    the sign of life is written in the same breath. Both halves matter: the
    number without the moment cannot survive the operating system reusing it, and
    the number without a fresh sign of life is what caused the 2026-07-19 two-day
    misreading described at the top of this file.
    """
    import os
    store.work_dir().mkdir(parents=True, exist_ok=True)
    number = os.getpid()
    started = machine.born(number)
    body = str(number) if started is None else "%s\n%r" % (number, started)
    safe_write.write_text(store.running_path(), body)
    beat()
    return number


def release():
    try:
        store.running_path().unlink()
    except OSError:
        pass


def running_number():
    """The process number of the background program, or None if it is not running.

    None here means genuinely not running. A number that is alive but belongs to
    an unrelated program - because the operating system reused it - also comes
    back as None, which is the correct answer and the point of recording the
    moment the program started alongside it.
    """
    try:
        lines = store.running_path().read_text(encoding="utf-8").strip().splitlines()
        number = int(lines[0].strip())
    except (OSError, ValueError, IndexError):
        return None
    recorded = lines[1].strip() if len(lines) > 1 else None
    return number if machine.same_program(number, recorded) else None


# --------------------------------------------------------------- the loop

def one_cycle(now=None, note=None):
    """One wake-up. Hands back the entries it started, for the tests to read."""
    now = now or datetime.now()
    note = note or store.log
    started = []
    state = store.read_state()
    for entry in store.load():
        if not clock.due(entry, now, state):
            continue
        # Written down BEFORE the command runs. An entry that is started and then
        # interrupted has had its turn; running it again on the next wake-up would
        # be the timetable doing the work twice.
        state = store.mark_ran(entry.get("id"), now.date(), state)
        runner.run(entry, alive_signal=beat, note=note)
        started.append(entry.get("id"))
        beat()                          # a finished entry refreshes the sign of life,
                                        # so a cycle with several entries in it cannot
                                        # age its own sign of life past looking hung
        time.sleep(PAUSE_BETWEEN_SECONDS)
    return started


def loop():
    """Run until stopped. This is what `timetable.py run` does."""
    number = claim()
    store.log("=== timetable up, process number %d ===" % number)
    try:
        while True:
            beat()                      # the top of the cycle, before any entry is
                                        # started. See the 2026-07-19 note above.
            try:
                one_cycle()
            except Exception as err:                          # noqa: BLE001
                store.log("[cycle] something went wrong: %s" % err)
            beat()
            time.sleep(WAKE_EVERY_SECONDS)
    except KeyboardInterrupt:
        pass
    finally:
        release()
        store.log("=== timetable down ===")
    return 0


# ------------------------------------------------------------------ control

def start():
    """Start the background program, detached, with no window. One sentence back."""
    already = running_number()
    if already:
        return "Already running, as process number %d." % already
    launcher = machine.quiet_python()
    try:
        process = subprocess.Popen(
            [launcher, str(SCRIPT), "run"],
            cwd=str(HERE),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **machine.detached_no_window()
        )
    except OSError as err:
        return "Could not start it: %s" % err
    time.sleep(1.5)
    if machine.alive(process.pid):
        return ("Started, as process number %d. Nothing appears on screen, which "
                "is deliberate.\n  What it does is written to %s"
                % (process.pid, store.log_path()))
    return "It did not stay running. The reason should be in %s" % store.log_path()


def stop():
    number = running_number()
    if not number:
        release()
        return "It was not running."
    machine.end(number)
    release()
    return "Stopped process number %d." % number


def health(now=None):
    """Everything `status` needs, as a small record."""
    now = now or datetime.now()
    number = running_number()
    age = beat_age_minutes(now)
    if number is None:
        word = "not running"
    elif age is None:
        word = "running, but it has not written a sign of life yet"
    elif age > STALE_MINUTES:
        word = "running, but its last sign of life was %d minutes ago" % int(age)
    else:
        word = "running"
    return {"number": number, "beat_age_minutes": age, "word": word,
            "log": store.log_path(), "timetable": store.timetable_path()}
