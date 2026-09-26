"""
timetable_runner.py - starting one command, watching it, and knowing when it has
genuinely wedged.

WHY EACH ENTRY CARRIES ITS OWN TIME LIMIT

  The obvious design is one limit over everything: no command may run longer than
  forty-five minutes. It is wrong, and here is the evidence rather than the
  argument.

  A job that walks a list one item at a time is paced by its own daily allowance,
  not by the clock. Forty items at three minutes each is two hours of correct,
  authorised work. Put a forty-five minute limit over it and the timetable ends
  the job in the middle of work it was allowed to do. On 2026-07-25 that cost 26
  actions the account was entitled to and had already decided to take. On
  2026-07-31 the same limit ended a run at 15 of 40, mid-page.

  So the limit belongs to the entry, not to the timetable. An entry that walks a
  long list declares an allowance with room in it; an entry that copies a file
  declares two minutes. A longer allowance can never raise how much work happens,
  because whatever the command's own limits are still bind - it only lets a
  command finish work it was already permitted to do.

WHY BEING ALIVE IS JUDGED ON PROGRESS, NOT ON ELAPSED TIME

  "It has been running for an hour" says nothing about whether it is working. A
  command that is walking a list slowly and a command that has hung both look
  identical from outside if all you measure is elapsed time.

  So output is read as it is produced, and every line read counts as progress and
  refreshes the sign of life. A command that keeps talking keeps the timetable
  looking healthy however long it takes. A command that goes silent for ten
  minutes stops refreshing it, so the sign of life ages and a genuine wedge is
  still caught. Refreshing merely because a command exists would blind that
  detection rather than serve it.

  Reading output as it is produced fixes a second fault as well. Reading it all
  at the end stamps every line with the moment the command was ENDED, so a log of
  a two-hour run reads as though the whole run happened in the final second.

Needs: Python 3.8 or newer. Nothing else.
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import timetable_platform as machine                          # noqa: E402
import timetable_store as store                               # noqa: E402

# Silence for this long means the command has stopped making progress, so the
# sign of life stops being refreshed on its behalf. It is NOT a limit: a silent
# command is left alone to finish or to hit its own allowance.
QUIET_MINUTES = 10

# How often the watching loop looks. Small enough to notice, large enough to cost
# nothing.
LOOK_EVERY_SECONDS = 2.0


def allowed_seconds(entry):
    """How long this entry may take, in seconds."""
    try:
        minutes = int(entry.get("allowed-minutes") or store.DEFAULT_ALLOWED_MINUTES)
    except (TypeError, ValueError):
        minutes = store.DEFAULT_ALLOWED_MINUTES
    return max(60, minutes * 60)


def watch(process, budget_seconds, alive_signal=None, quiet_seconds=None,
          clock=time.monotonic, wait=time.sleep, look_every=None):
    """Read a running command's output as it appears and hand back what it said.

    Returns (what it said, seconds after which it was ended or None).

    `alive_signal` is called while the command is making progress. `clock` and
    `wait` are arguments rather than fixed so this can be tested in a fraction of
    a second instead of forty-five minutes.
    """
    quiet_seconds = QUIET_MINUTES * 60 if quiet_seconds is None else quiet_seconds
    look_every = LOOK_EVERY_SECONDS if look_every is None else look_every
    lines = []
    lock = threading.Lock()
    last_spoke = [clock()]

    def drain():
        try:
            for line in process.stdout:
                with lock:
                    lines.append(line.rstrip("\n"))
                    last_spoke[0] = clock()
        except Exception:                                     # noqa: BLE001
            pass                                              # ended mid-read

    reader = threading.Thread(target=drain, name="timetable-reader")
    reader.daemon = True
    reader.start()

    started = clock()
    ended_after = None
    while process.poll() is None:
        elapsed = clock() - started
        if elapsed >= budget_seconds:
            process.kill()
            ended_after = int(elapsed)
            break
        with lock:
            quiet_for = clock() - last_spoke[0]
        if alive_signal is not None and quiet_for < quiet_seconds:
            alive_signal()
        wait(look_every)

    reader.join(timeout=10)
    try:
        process.wait(timeout=10)
    except Exception:                                         # noqa: BLE001
        pass
    with lock:
        return "\n".join(lines), ended_after


def start_process(parts, working_dir):
    """Start one command with no window, its output captured, its input closed.

    The no-window flag is on this call and not only on the background program
    that made it. A program with no console of its own that starts another
    program makes Windows give THAT one a console window, and capturing the
    output does not prevent it - capturing changes where the output goes, it does
    not stop the window being created. This is the 2026-07-27 correction and it
    has to be at every start, not at the top.

    Input is closed rather than left open so a command that asks a question gets
    an immediate end-of-input and stops, instead of waiting for an answer nobody
    is there to type.
    """
    environment = dict(os.environ)
    environment["PYTHONUNBUFFERED"] = "1"                     # so output arrives as it happens
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.Popen(
        machine.windowless_command(parts),
        cwd=str(working_dir),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        **machine.no_window()
    )


def run(entry, alive_signal=None, note=None, working_dir=None):
    """Start one entry's command, watch it, write down what happened.

    Returns a small record of the run. It never raises: a command that cannot be
    started is a result to be written down, not a fault that ends the timetable
    and takes every other entry down with it.
    """
    note = note or store.log
    working_dir = Path(working_dir or Path(__file__).resolve().parent)
    entry_id = entry.get("id") or "unnamed"
    parts = store.split_command(entry.get("command", ""))
    budget = allowed_seconds(entry)

    if not parts:
        note("[%s] there is no command to run" % entry_id)
        return {"id": entry_id, "started": False, "ended_after": None,
                "code": None, "output": "", "why": "no command"}

    note("[%s] starting: %s" % (entry_id, entry.get("command")))
    try:
        process = start_process(parts, working_dir)
    except OSError as err:
        note("[%s] could not start: %s" % (entry_id, err))
        return {"id": entry_id, "started": False, "ended_after": None,
                "code": None, "output": "", "why": str(err)}

    said, ended_after = watch(process, budget, alive_signal=alive_signal)
    for line in said.splitlines():
        note("    %s" % line)
    if ended_after is not None:
        note("[%s] ended by the timetable after %d seconds, having been allowed %d. "
             "It did not finish, and how much it completed is not knowable from here."
             % (entry_id, ended_after, budget))
    note("[%s] finished, result %s" % (entry_id, process.returncode))
    return {"id": entry_id, "started": True, "ended_after": ended_after,
            "code": process.returncode, "output": said, "why": ""}
