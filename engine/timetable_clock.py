"""
timetable_clock.py - when each entry actually fires, and whether it still may.

Two decisions live here and both have a reason that is easy to get wrong.

THE FIRING MINUTE IS SHIFTED, AND THE SHIFT IS WORKED OUT RATHER THAN ROLLED

  An entry set to 09:30 does not fire at 09:30. Its minute is moved by up to a
  few minutes either way, so it lands at 09:27 one day and 09:33 the next. A job
  that fires at exactly the same minute every single day is a pattern no person
  produces, and being inside every limit does not help you if the rhythm gives
  you away.

  The shift is NOT a random number. It is worked out from the entry's name, run
  through a hash - a calculation that turns text into a number that looks
  scattered but is always the same number for the same text - and then moved on
  by one place for each day that passes. Same entry, same date, same answer,
  every time it is asked.

  That property is the whole point, and a random number would destroy it. The
  background program asks "when does this fire today?" on every wake-up, dozens
  of times an hour. With a rolled number the answer would be different each time
  it was asked: the entry would drift forwards and backwards through the morning,
  fire early, and fire again after a restart because the new answer no longer
  matched the old one. Worked out from the name and the date, a restart at noon
  computes the identical minute it computed at dawn, so the record of what has
  already run still lines up and nothing runs twice.

  The step from one day to the next is chosen so that it never lands back where
  it was yesterday, and so that over a fortnight it visits every minute in the
  range. That is the honest cost of the guarantee: a plain hash of the name and
  the date would occasionally hand you the same minute two days running, roughly
  one day in nine, and "occasionally identical" is exactly the pattern being
  avoided. One entry's minutes therefore walk the range in a repeating order
  rather than scattering freely, and each entry starts at a different place in
  that order and steps through it by a different amount.

THE LATE WINDOW

  A missed entry still runs, up to about two hours after its minute. A laptop
  asleep at nine still runs the nine o'clock job when it wakes at ten. Without
  this, closing the lid means the day's work never happens and there is nothing
  to say why. Two hours is long enough to cover a lie-in, a meeting or a reboot,
  and short enough that a job set for the morning never lands in the evening.

Needs: Python 3.8 or newer. Nothing else.
"""

import hashlib
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import timetable_store as store                               # noqa: E402

LATE_WINDOW_MINUTES = 120

DAY_NAMES = store.DAY_NAMES


def _number_from(text):
    """A scattered but always-identical number for a piece of text."""
    digest = hashlib.sha256(str(text).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def shift_minutes(entry_id, day, span):
    """How far this entry's minute moves on this date: between -span and +span.

    Worked out, never rolled. See the note at the top of this file for why that
    distinction is the difference between a timetable that holds and one that
    drifts and repeats itself.

    Two numbers come out of the entry's name: where in the range it starts, and
    how far it moves each day. The move is only ever a size that cannot land back
    on yesterday's minute and that reaches every minute in the range before it
    repeats - which is what makes "never the same minute two days running" a
    guarantee rather than a hope.
    """
    span = int(span or 0)
    if span <= 0:
        return 0
    places = 2 * span + 1
    steps = [k for k in range(1, places) if math.gcd(k, places) == 1]
    start = _number_from("%s|start" % entry_id) % places
    step = steps[_number_from("%s|step" % entry_id) % len(steps)]
    return (start + day.toordinal() * step) % places - span


def fire_time(entry, when):
    """The moment this entry fires on the day of `when`, or None if unreadable."""
    try:
        hour, minute = (int(part) for part in str(entry.get("at", "")).split(":")[:2])
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    day = when.date()
    base = when.replace(hour=hour, minute=minute, second=0, microsecond=0)
    span = entry.get("shift-minutes", store.DEFAULT_SHIFT_MINUTES)
    return base + timedelta(minutes=shift_minutes(entry.get("id", ""), day, span))


def runs_on(entry, when):
    days = [str(d).strip().lower()[:3] for d in (entry.get("days") or [])]
    return DAY_NAMES[when.weekday()] in days


def status_of(entry, when=None, state=None):
    """One word for where this entry stands right now, and its firing moment.

    The order the reasons are checked in is the order a person would ask them,
    and the word you get back is the FIRST reason that applies - the one that
    would still hold if you fixed all the others.
    """
    when = when or datetime.now()
    state = store.read_state() if state is None else state
    moment = fire_time(entry, when)
    if not entry.get("enabled"):
        return "switched off", moment
    if not runs_on(entry, when):
        return "not today", moment
    if moment is None:
        return "unreadable time", None
    if store.already_ran(entry.get("id"), when.date(), state):
        return "done today", moment
    if when < moment:
        return "waiting", moment
    if when <= moment + timedelta(minutes=LATE_WINDOW_MINUTES):
        return "due now", moment
    return "missed", moment


def due(entry, when=None, state=None):
    """May this entry be started at this moment? True only for 'due now'."""
    word, _ = status_of(entry, when, state)
    return word == "due now"


def plan(entries=None, when=None):
    """Today's timetable as a list, in firing order, for printing.

    This is what `list` shows and what `run --dry-run` shows. It reads files and
    works out times. It cannot start anything, which is what makes the dry run
    honest rather than a claim.
    """
    when = when or datetime.now()
    entries = store.load() if entries is None else entries
    state = store.read_state()
    rows = []
    for entry in entries:
        word, moment = status_of(entry, when, state)
        rows.append({"entry": entry, "at": moment, "status": word})
    rows.sort(key=lambda row: (row["at"] is None, row["at"] or when))
    return rows
