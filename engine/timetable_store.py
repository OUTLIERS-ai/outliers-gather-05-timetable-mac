"""
timetable_store.py - the timetable file, the record of what has already run, and
the log.

Three files, all inside the CRM you already have:

    _layers/timetable.json      the timetable. Yours. Edit it by hand if you like.
    _state/timetable/state.json what has already run, and on which date.
    _state/timetable/*.log      what happened, one line at a time.

WHY THE RECORD OF WHAT HAS ALREADY RUN IS A SEPARATE FILE

  A timetable on its own cannot stop an entry running twice. The background
  program wakes up every half minute or so; without a written record, an entry
  due at half past nine would fire on every wake-up between half past nine and
  whenever the window closed. The record is written the moment before an entry is
  started, never after it finishes, so a machine that is switched off mid-run
  restarts into "that one has been done today" rather than starting it again.

WHAT AN ENTRY LOOKS LIKE

    {
      "id": "morning-collect",        a short name, unique, yours to type
      "label": "Collect the day's list",
      "command": "python gather.py collect",
      "at": "09:30",                  the time you asked for
      "days": ["mon", "tue", "wed", "thu", "fri"],
      "enabled": true,
      "shift-minutes": 4,             see timetable_clock.py
      "allowed-minutes": 45           how long this one may take, see below
    }

  `allowed-minutes` is per entry rather than one limit over the whole timetable,
  and that is not a nicety. See the dated note in timetable_runner.py: a single
  45-minute limit sitting over work that paces itself will cut that work short
  every time, and it did, twice.

Needs: Python 3.8 or newer. Nothing else.
"""

import os
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import crm_paths                                              # noqa: E402
import safe_write                                             # noqa: E402

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# A few minutes, not a few hours. Enough that the same minute never repeats two
# days running; small enough that "half past nine" still means half past nine.
DEFAULT_SHIFT_MINUTES = 4

# A sensible ceiling for a job that has said nothing about how long it needs.
# Any entry that needs longer says so in its own `allowed-minutes`.
DEFAULT_ALLOWED_MINUTES = 45

# When the log passes this size it is rolled over rather than trimmed in place,
# because trimming a file in place is a truncating write and those are banned.
LOG_ROLL_BYTES = 2 * 1024 * 1024


def timetable_path():
    """The timetable itself. It sits with your other answers, not with the
    machine's working state, because it is yours to read and edit."""
    return crm_paths.vault() / "_layers" / "timetable.json"


def work_dir():
    return crm_paths.state_dir() / "timetable"


def state_path():
    return work_dir() / "state.json"


def heartbeat_path():
    return work_dir() / "heartbeat"


def running_path():
    return work_dir() / "running.id"


def log_path():
    return work_dir() / "timetable.log"


# ----------------------------------------------------------------- the timetable

def load():
    """Every entry, or an empty timetable if there is not one yet.

    A fresh install has NO entries. Nobody should inherit a timetable they did
    not write, and the documented first step is one entry, once a day, watched.
    """
    entries = safe_write.read_json(timetable_path(), [])
    if not isinstance(entries, list):
        return []
    return [e for e in entries if isinstance(e, dict) and e.get("id")]


def save(entries):
    timetable_path().parent.mkdir(parents=True, exist_ok=True)
    safe_write.write_json(timetable_path(), list(entries))
    return list(entries)


def find(entry_id):
    for entry in load():
        if entry.get("id") == entry_id:
            return entry
    return None


def make_id(text, taken=None):
    """A short, typeable name made from what you wrote, kept unique."""
    taken = set(taken or [])
    base = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    base = "-".join(base.split("-")[:4])[:32] or "job"
    if base not in taken:
        return base
    n = 2
    while "%s-%d" % (base, n) in taken:
        n += 1
    return "%s-%d" % (base, n)


def add(command, at, days, label=None, shift_minutes=None, allowed_minutes=None):
    """Put one entry on the timetable and hand it back."""
    entries = load()
    entry = {
        "id": make_id(label or command, [e.get("id") for e in entries]),
        "label": (label or command).strip(),
        "command": str(command).strip(),
        "at": tidy_time(at),
        "days": tidy_days(days),
        "enabled": True,
        "shift-minutes": DEFAULT_SHIFT_MINUTES if shift_minutes is None else int(shift_minutes),
        "allowed-minutes": DEFAULT_ALLOWED_MINUTES if allowed_minutes is None else int(allowed_minutes),
    }
    entries.append(entry)
    save(entries)
    return entry


def remove(entry_id):
    entries = load()
    kept = [e for e in entries if e.get("id") != entry_id]
    if len(kept) == len(entries):
        return False
    save(kept)
    forget(entry_id)
    return True


def set_enabled(entry_id, on):
    entries = load()
    for entry in entries:
        if entry.get("id") == entry_id:
            entry["enabled"] = bool(on)
            save(entries)
            return entry
    return None


def tidy_time(text):
    """Read a time you typed and hand back HH:MM, or raise ValueError."""
    raw = str(text).strip().replace(".", ":")
    match = re.match(r"^(\d{1,2}):?(\d{2})$", raw)
    if not match:
        raise ValueError("I could not read %r as a time. Write it as 09:30." % text)
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("%r is not a time on the clock." % text)
    return "%02d:%02d" % (hour, minute)


def tidy_days(text):
    """Read the days you typed and hand back a list like ["mon", "tue"]."""
    if isinstance(text, (list, tuple)):
        raw = list(text)
    else:
        raw = str(text).replace(" ", ",").split(",")
    named = [str(d).strip().lower()[:3] for d in raw if str(d).strip()]
    if named == ["all"] or named == ["eve"] or named == ["dai"]:
        return list(DAY_NAMES)
    if named == ["wee"]:                                       # weekdays
        return DAY_NAMES[:5]
    chosen = [d for d in named if d in DAY_NAMES]
    if not chosen:
        raise ValueError("I could not read %r as days. Write them as mon,tue,wed." % text)
    return [d for d in DAY_NAMES if d in chosen]               # in week order, no repeats


def split_command(text):
    """Break a typed command line into the pieces a program start expects.

    Windows is handled separately on purpose. The ordinary splitter treats a
    backslash as an escape character, which turns C:\\Tools\\run.py into
    C:Toolsrun.py and hands you a command that cannot possibly work. On Windows
    the splitter is told to leave backslashes alone and the surrounding quote
    marks are taken off afterwards.
    """
    text = str(text).strip()
    if not text:
        return []
    if os.name == "nt":
        parts = shlex.split(text, posix=False)
        out = []
        for part in parts:
            if len(part) > 1 and part[0] == part[-1] and part[0] in "\"'":
                part = part[1:-1]
            out.append(part)
        return out
    return shlex.split(text)


# --------------------------------------------- what has already run, and when

def read_state():
    state = safe_write.read_json(state_path(), {})
    return state if isinstance(state, dict) else {}


def write_state(state):
    work_dir().mkdir(parents=True, exist_ok=True)
    safe_write.write_json(state_path(), state)
    return state


def already_ran(entry_id, day, state=None):
    state = read_state() if state is None else state
    return state.get(entry_id) == day.isoformat()


def mark_ran(entry_id, day, state=None):
    """Write down that this entry has had its turn today.

    Called BEFORE the command is started, never after. An entry that is started
    and then interrupted has had its turn; starting it again on the next wake-up
    would be the timetable doing the work twice, which is the one failure a
    timetable must never produce.
    """
    state = read_state() if state is None else dict(state)
    state[entry_id] = day.isoformat()
    write_state(state)
    return state


def forget(entry_id):
    state = read_state()
    if entry_id in state:
        state.pop(entry_id)
        write_state(state)
    return state


# ------------------------------------------------------------------- the log

def log(message):
    line = "%s  %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), message)
    try:
        work_dir().mkdir(parents=True, exist_ok=True)
        path = log_path()
        if path.exists() and path.stat().st_size > LOG_ROLL_BYTES:
            os.replace(str(path), str(path) + ".old")
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    return line
