"""
test_timetable.py - the behaviours that exist because of a dated failure, pinned.

SHOULD: an entry fires once and once only; a missed entry still fires inside the
late window; the firing minute is worked out rather than rolled, so a restart
computes the identical minute and never the same minute two days running; the
sign of life is written the instant the program starts; a reused process number
cannot impersonate a dead run; each entry gets its own time allowance; being
alive is judged on progress; and nothing this layer starts is ever given a
window.

DID (2026-08-13, the reason each test below exists):

  * 2026-07-19. A freshly started background program was reported as hung for two
    days. The sign of life was written at the BOTTOM of the loop, so until the
    first cycle finished it still carried the dead previous run's timestamp. The
    sign-of-life test writes a stale timestamp, starts up, and fails if it is
    still stale.
  * 2026-07-26. The operating system handed a dead job's process number, 31192,
    to an unrelated laptop utility. The checker reported a dead program as
    running AND refused to start the real one. The identity test fails if a
    recorded start moment that disagrees is accepted.
  * 2026-07-25 and 2026-07-31. One 45-minute limit stretched over work paced by
    its own daily allowance cut that work short: 26 actions lost on the first
    date, a job ended at 15 of 40 on the second. The allowance test fails if an
    entry's own declared limit is ignored.
  * 2026-07-27. About forty scheduled jobs each opened a console window when they
    fired, which was very nearly the reason the whole set was switched off.
    Capturing output does not prevent it. The no-window tests read the source of
    every file in the layer and fail on any start of another program that does
    not carry the flag.

Run it:  python tests/test_timetable.py        (exit 0 = green)

It schedules nothing, starts no background program, and writes nowhere near your
real CRM: every test points crm_paths at a throwaway folder first. A test that
reads and writes your real CRM is not a test.
"""

import os
import shutil
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE.parent / "engine"

sys.path.insert(0, str(ENGINE))


def find_installed_crm():
    """Your CRM, found the same way the installer finds it.

    Deliberately NOT a path relative to this repository. A test that reaches back
    into the folder it was authored in passes for its author and fails for every
    person who clones it, which is the whole family of fault this series exists
    to avoid. It never prompts: a test that asks a question cannot be run
    unattended.
    """
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
    cwd = Path.cwd()
    tried.append(cwd)
    tried.extend(cwd.parents)
    for candidate in tried:
        try:
            engine = Path(candidate) / "_engine"
            if (engine / "crm_paths.py").exists() and (engine / "safe_write.py").exists():
                return engine
        except OSError:
            continue
    return None


CRM_ENGINE = find_installed_crm()

if CRM_ENGINE is None:
    print("=" * 66)
    print("  Your CRM was not found, so the tests stop here.")
    print("=" * 66)
    print()
    print("  This layer writes your timetable and its record of what has already")
    print("  run through two files that belong to your CRM and are shared by every")
    print("  layer: crm_paths.py and safe_write.py. The promise that a write can")
    print("  never damage the file already there lives in YOUR copy of the second")
    print("  one, not in ours, so the tests below run against your copy.")
    print()
    print("  Without it there is nothing to test against, and a test that did not")
    print("  run is not a test that passed.")
    print()
    print("  This is not a fault in this layer. Install the first layer of your")
    print("  CRM, then run this again. If your CRM is somewhere unusual, point")
    print("  at it:")
    print()
    print("      OUTLIERS_CRM=/path/to/your/CRM python tests/test_timetable.py")
    print()
    sys.exit(2)


FAILS = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (" :: " + detail if detail else ""))
    if not ok:
        FAILS.append(name)


# --- a throwaway CRM, using YOUR copies of the two shared files ---------------
root = Path(tempfile.mkdtemp(prefix="timetable-"))
(root / "_layers").mkdir(parents=True, exist_ok=True)
(root / "_state").mkdir(parents=True, exist_ok=True)
(root / "_engine").mkdir(parents=True, exist_ok=True)
for name in ("crm_paths.py", "safe_write.py"):
    shutil.copy2(CRM_ENGINE / name, root / "_engine" / name)
sys.path.insert(0, str(root / "_engine"))

import crm_paths                                              # noqa: E402
crm_paths.use_vault(root)

import safe_write                                             # noqa: E402
import timetable_clock as clock                               # noqa: E402
import timetable_daemon as daemon                             # noqa: E402
import timetable_platform as machine                          # noqa: E402
import timetable_runner as runner                             # noqa: E402
import timetable_store as store                               # noqa: E402

# Noted before a single test runs, so the last check in this file can prove these
# tests registered nothing on your machine.
AGENT_PATH = (Path.home() / "Library" / "LaunchAgents"
              / ("%s.plist" % machine.LAUNCH_AGENT_LABEL))
AGENT_EXISTED = AGENT_PATH.exists()


# --- the two shared files are your CRM's, and they still do what we rely on ---
print("=== the shared files come from your CRM, not from this repository ===")

for name in ("vault", "use_vault", "state_dir"):
    check("your crm_paths offers %s()" % name, hasattr(crm_paths, name))
for name in ("write_text", "write_json", "read_json"):
    check("your safe_write offers %s()" % name, hasattr(safe_write, name))

shared_source = (CRM_ENGINE / "safe_write.py").read_text(encoding="utf-8")
check("your safe_write writes to one side and swaps, rather than emptying a file",
      "os.replace" in shared_source,
      "this layer's timetable and its record of what has run depend on that")

# COMPARED AS TEXT, NOT AS BYTES, AND THE DIFFERENCE COST US A REAL FAILURE.
#
# Git rewrites line endings on checkout, so the copy in a freshly cloned repository
# and the copy installed from this machine differ by invisible characters while
# being the same file. Comparing bytes made these two checks pass for whoever built
# the layer and fail for every member who cloned it -- and fail with advice
# ("reinstall the newer one") that would have sent them chasing nothing.
#
# What matters here is that the two files say the same, not that they were written
# on the same operating system.
def _same_text(a, b):
    norm = lambda p: p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").rstrip()
    return norm(a) == norm(b)


for name in ("crm_paths.py", "safe_write.py"):
    check("your %s matches the copy this layer ships" % name,
          _same_text(CRM_ENGINE / name, ENGINE / name),
          "these are meant to be identical in every layer; reinstall the newer one")

check("this layer wrote its throwaway timetable inside the throwaway CRM",
      str(root) in str(store.timetable_path()), str(store.timetable_path()))


# --- the timetable file -------------------------------------------------------
print()
print("=== the timetable: adding, switching off, removing ===")

first = store.add("python gather.py collect", "9:30", "fri,mon,tue",
                  label="Collect the day's list")
check("an entry comes back with a short name of its own", bool(first["id"]), first["id"])
check("the time is tidied to a full clock time", first["at"] == "09:30", first["at"])
check("the days come back in week order", first["days"] == ["mon", "tue", "fri"],
      str(first["days"]))
check("it arrives switched on", first["enabled"] is True)
check("it has an allowance of its own", first["allowed-minutes"] > 0,
      "%d minutes" % first["allowed-minutes"])

second = store.add("echo hello", "09:30", "mon")
check("a second entry does not take the first one's name",
      second["id"] != first["id"], "%s / %s" % (first["id"], second["id"]))

store.set_enabled(second["id"], False)
check("switching one off leaves it on the timetable",
      store.find(second["id"]) is not None and not store.find(second["id"])["enabled"])

store.remove(second["id"])
check("removing takes it off the timetable", store.find(second["id"]) is None)

for bad in ("half nine", "25:00", "9:99"):
    try:
        store.tidy_time(bad)
        check("a time it cannot read is refused (%r)" % bad, False, "it was accepted")
    except ValueError:
        check("a time it cannot read is refused (%r)" % bad, True)

if os.name == "nt":
    parts = store.split_command(r'python C:\Tools\run.py --at 09:30')
    check("a Windows path survives being split up",
          parts[1] == r"C:\Tools\run.py", str(parts))
else:
    parts = store.split_command('python "my script.py" --at 09:30')
    check("a quoted name with a space survives being split up",
          parts[1] == "my script.py", str(parts))


# --- the firing minute --------------------------------------------------------
print()
print("=== the firing minute is worked out, not rolled ===")

entry = store.find(first["id"])
noon = datetime(2026, 8, 13, 12, 0)
answers = {clock.fire_time(entry, noon) for _ in range(20)}
check("asked twenty times, it gives one answer", len(answers) == 1,
      "a rolled number would give twenty and the entry would drift and re-fire")

span = entry["shift-minutes"]
offsets = [clock.shift_minutes(entry["id"], date(2026, 8, 1) + timedelta(days=n), span)
           for n in range(60)]
check("the move never leaves the range you set",
      all(-span <= o <= span for o in offsets), "range %d..%d" % (min(offsets), max(offsets)))
check("no two days running share a minute",
      all(offsets[n] != offsets[n + 1] for n in range(len(offsets) - 1)),
      "this is the whole reason the minute moves at all")
check("over a fortnight it uses the whole range",
      len(set(offsets[:2 * span + 1])) == 2 * span + 1,
      "%d of %d places used" % (len(set(offsets[:2 * span + 1])), 2 * span + 1))
check("two different entries do not move together",
      [clock.shift_minutes("one", date(2026, 8, 1) + timedelta(days=n), span) for n in range(9)]
      != [clock.shift_minutes("two", date(2026, 8, 1) + timedelta(days=n), span) for n in range(9)])

fired = clock.fire_time(entry, noon)
check("it lands within a few minutes of the time you asked for",
      abs((fired - noon.replace(hour=9, minute=30)).total_seconds()) <= span * 60,
      fired.strftime("%H:%M"))


# --- the late window ----------------------------------------------------------
print()
print("=== a missed entry still fires, up to two hours late ===")

wednesday = datetime(2026, 8, 12, 9, 30)                      # a Wednesday
weekly = dict(entry, days=["mon", "tue", "wed", "thu", "fri"], id="late-window")
moment = clock.fire_time(weekly, wednesday)

store.write_state({})
check("before its minute, it waits",
      clock.status_of(weekly, moment - timedelta(minutes=1))[0] == "waiting")
check("at its minute, it is due", clock.status_of(weekly, moment)[0] == "due now")
check("an hour late, it is still due - a laptop asleep at nine still runs it",
      clock.status_of(weekly, moment + timedelta(minutes=60))[0] == "due now")
check("at the edge of the late window, it is still due",
      clock.status_of(weekly, moment + timedelta(minutes=clock.LATE_WINDOW_MINUTES))[0]
      == "due now")
check("past the late window, it is missed rather than fired in the evening",
      clock.status_of(weekly, moment + timedelta(minutes=clock.LATE_WINDOW_MINUTES + 1))[0]
      == "missed")
check("on a day it was not asked to run, it does not",
      clock.status_of(weekly, datetime(2026, 8, 15, 9, 30))[0] == "not today")

off = dict(weekly, enabled=False)
check("switched off, it never becomes due", not clock.due(off, moment))


# --- nothing fires twice ------------------------------------------------------
print()
print("=== nothing fires twice ===")

store.write_state({})
check("with nothing written down, it is due", clock.due(weekly, moment))
store.mark_ran(weekly["id"], moment.date())
check("once it is written down, it is not due again", not clock.due(weekly, moment))
check("and it says so plainly", clock.status_of(weekly, moment)[0] == "done today")
check("tomorrow it is due again",
      clock.due(dict(weekly), moment + timedelta(days=1)) is True
      or clock.status_of(weekly, moment + timedelta(days=1))[0] in ("waiting", "due now"))

# The record is written BEFORE the command runs, so an interrupted run has still
# had its turn. This replaces the runner, so nothing is started here.
store.write_state({})
store.save([dict(weekly, enabled=True)])
seen = {}


def pretend_to_run(entry_, alive_signal=None, note=None, working_dir=None):
    seen["written_down_already"] = store.already_ran(entry_["id"], moment.date())
    seen["ran"] = entry_["id"]
    return {"id": entry_["id"], "started": True, "ended_after": None,
            "code": 0, "output": "", "why": ""}


real_run, real_sleep = runner.run, daemon.time.sleep
runner.run = pretend_to_run
daemon.time.sleep = lambda _s: None
try:
    started = daemon.one_cycle(moment, note=lambda m: None)
finally:
    runner.run = real_run
    daemon.time.sleep = real_sleep

check("one cycle starts the entry that is due", started == [weekly["id"]], str(started))
check("and it was written down BEFORE the command ran",
      seen.get("written_down_already") is True,
      "a run interrupted halfway must not get a second turn on the next wake-up")


# --- each entry gets its own time allowance -----------------------------------
print()
print("=== each entry says how long it may take ===")

plain = {"id": "plain", "command": "echo hi"}
check("an entry that says nothing gets the ordinary allowance",
      runner.allowed_seconds(plain) == store.DEFAULT_ALLOWED_MINUTES * 60,
      "%d seconds" % runner.allowed_seconds(plain))
long_one = {"id": "long", "command": "echo hi", "allowed-minutes": 180}
check("an entry that walks a long list gets the longer allowance it declared",
      runner.allowed_seconds(long_one) == 180 * 60,
      "one 45-minute limit over everything lost 26 actions on 2026-07-25 and ended "
      "a job at 15 of 40 on 2026-07-31")
check("a nonsense allowance falls back rather than ending a run at once",
      runner.allowed_seconds({"id": "odd", "allowed-minutes": "soon"})
      == store.DEFAULT_ALLOWED_MINUTES * 60)


# --- being alive is judged on progress ----------------------------------------
print()
print("=== being alive is judged on progress, not on elapsed time ===")


class PretendCommand(object):
    """A command that says a line every so often. It starts no program at all."""

    def __init__(self, lines, cycles, ends_itself=True):
        self.stdout = iter(lines)
        self.cycles = cycles
        self.ends_itself = ends_itself
        self.returncode = None
        self.killed = False
        self._looks = 0

    def poll(self):
        self._looks += 1
        if self.ends_itself and self._looks > self.cycles:
            self.returncode = 0
            return 0
        return None

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


ticks = [0.0]


def fake_clock():
    return ticks[0]


def fake_wait(seconds):
    ticks[0] += seconds


beats = []
ticks[0] = 0.0
talker = PretendCommand(["one\n", "two\n"], cycles=4)
said, ended = runner.watch(talker, budget_seconds=1000, alive_signal=lambda: beats.append(1),
                           quiet_seconds=60, clock=fake_clock, wait=fake_wait, look_every=1.0)
check("a command that finishes on its own is not ended by the timetable", ended is None)
check("and what it said is kept", "one" in said and "two" in said, said.replace("\n", " / "))
check("while it was talking, the sign of life kept being refreshed", len(beats) > 0,
      "%d refreshes" % len(beats))

ticks[0] = 0.0
beats = []
silent = PretendCommand([], cycles=10000, ends_itself=False)
time.sleep(0.05)                     # let the reader thread reach the end of no output
said, ended = runner.watch(silent, budget_seconds=1000, alive_signal=lambda: beats.append(1),
                           quiet_seconds=5, clock=fake_clock, wait=fake_wait, look_every=1.0)
check("a command that goes silent stops the sign of life being refreshed",
      len(beats) <= 6, "%d refreshes before it fell quiet" % len(beats))
check("a silent command is still ended when its own allowance runs out",
      ended is not None and silent.killed, "ended after %s" % ended)

ticks[0] = 0.0
overrun = PretendCommand([], cycles=10000, ends_itself=False)
said, ended = runner.watch(overrun, budget_seconds=30, quiet_seconds=1000,
                           clock=fake_clock, wait=fake_wait, look_every=1.0)
check("the allowance is what ends it, and it says how long it had",
      ended is not None and ended >= 30, "ended after %s seconds" % ended)


# --- the sign of life ---------------------------------------------------------
print()
print("=== the sign of life is written the instant it starts ===")

store.work_dir().mkdir(parents=True, exist_ok=True)
stale = (datetime.now() - timedelta(hours=2)).replace(microsecond=0)
safe_write.write_text(store.heartbeat_path(), stale.isoformat())
check("a stale sign of life reads as stale", daemon.beat_age_minutes() > 100,
      "%d minutes" % daemon.beat_age_minutes())

daemon.claim()
check("starting up replaces it at once, before any entry is started",
      daemon.beat_age_minutes() < 1,
      "on 2026-07-19 this was written at the BOTTOM of the loop instead, so a "
      "healthy program was reported hung for two days")
check("and the running program was written down too", store.running_path().exists())


# --- which running program is ours --------------------------------------------
print()
print("=== a reused process number cannot impersonate a dead run ===")

mine = os.getpid()
check("this test's own process number is found as ours",
      daemon.running_number() == mine, str(daemon.running_number()))

started_at = machine.born(mine)
if started_at is None:
    check("a disagreeing start moment is rejected (SKIPPED: this machine will not "
          "report when a program started)", True,
          "the layer keeps trusting the number, which is the safe direction")
else:
    check("a start moment that disagrees is rejected",
          not machine.same_program(mine, started_at - 9999),
          "on 2026-07-26 number 31192 passed from a dead job to a laptop utility, "
          "and the checker reported the dead job as running")
    check("a start moment that agrees is accepted",
          machine.same_program(mine, started_at))
check("no recorded start moment keeps the number trusted",
      machine.same_program(mine, None),
      "calling a live program dead would let a second copy start alongside it")
check("a number nobody is using is not ours", not machine.same_program(999999999, None))

daemon.release()
check("letting go removes the record", daemon.running_number() is None)


# --- the dry run starts nothing ------------------------------------------------
print()
print("=== the dry run starts nothing ===")

import io                                                     # noqa: E402
import contextlib                                             # noqa: E402
import timetable as cli                                       # noqa: E402


def must_not_be_called(*a, **k):
    raise AssertionError("the dry run started a command")


long_name = "a-rather-long-name-for-an-entry"
store.save(store.load() + [dict(weekly, id=long_name, enabled=True)])

real_run, real_loop = runner.run, daemon.loop
runner.run = must_not_be_called
daemon.loop = must_not_be_called
try:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = cli.cmd_run(["--dry-run"])
    shown = buffer.getvalue()
    check("run --dry-run returns without starting anything", code == 0)
    check("and it shows what today holds", "dry run" in shown.lower())
    check("an entry's name is printed in full, never shortened to fit",
          long_name in shown,
          "a name printed shorter than it is would be typed back exactly as "
          "printed and refused")
except AssertionError as err:
    check("run --dry-run starts nothing", False, str(err))
finally:
    runner.run = real_run
    daemon.loop = real_loop


# --- nothing is ever given a window --------------------------------------------
print()
print("=== nothing this layer starts is ever given a window ===")

if machine.IS_WINDOWS:
    flags = machine.no_window().get("creationflags", 0)
    check("on Windows, starting a command carries the no-window flag", flags != 0,
          "capturing output does NOT stop the window being created")
    check("the background program itself is started detached and with no window",
          machine.detached_no_window().get("creationflags", 0) != 0)
    check("Python commands are pointed at the copy with no console",
          Path(machine.quiet_python()).name.lower().startswith("pythonw")
          or not Path(sys.executable).with_name("pythonw.exe").exists(),
          machine.quiet_python())
    rewritten = machine.windowless_command(["python", "run.py"])
    check("a command that starts python is rewritten to the quiet one",
          Path(rewritten[0]).name.lower().startswith("pythonw")
          or not Path(sys.executable).with_name("pythonw.exe").exists(),
          str(rewritten))
else:
    check("on a Mac there is no console window to suppress, so no flags are needed",
          machine.no_window() == {})
    check("the background program is still detached from the window that started it",
          machine.detached_no_window().get("start_new_session") is True)

# Read every file in the layer and find every start of another program. Any one
# of them that does not carry the flag is the 2026-07-27 failure coming back.
POSIX_ONLY = ('["ps"', '["launchctl"', '["lsof"')
starts, unguarded = 0, []
for path in sorted(ENGINE.glob("*.py")):
    text = path.read_text(encoding="utf-8")
    for marker in ("subprocess.Popen(", "subprocess.run("):
        at = text.find(marker)
        while at != -1:
            starts += 1
            head = text[at + len(marker):at + len(marker) + 40].strip()
            window = text[at:at + 700]
            guarded = ("no_window" in window or "detached" in window
                       or head.startswith(POSIX_ONLY))
            if not guarded:
                unguarded.append("%s near character %d" % (path.name, at))
            at = text.find(marker, at + 1)
check("every start of another program was found", starts >= 4, "%d found" % starts)
check("and every one of them is either windowless or Mac-only",
      not unguarded, "; ".join(unguarded))

# A refusal has to come back AS a refusal. Nothing real is registered here: the
# machine is told it is neither Windows nor a Mac, and on Windows the call out to
# the task scheduler is replaced with one that refuses.
was_windows, was_mac = machine.IS_WINDOWS, machine.IS_MAC
machine.IS_WINDOWS = machine.IS_MAC = False
try:
    answer = machine.install_startup(ENGINE / "timetable.py", root, root / "x.log")
    check("starting at login always answers with whether it worked",
          isinstance(answer, tuple) and len(answer) == 2 and answer[0] is False,
          str(answer)[:90])
finally:
    machine.IS_WINDOWS, machine.IS_MAC = was_windows, was_mac

if machine.IS_WINDOWS:
    class RefusingScheduler(object):
        PIPE = DEVNULL = STDOUT = None

        class Done(object):
            returncode, stdout, stderr = 1, "", "ERROR: Access is denied."

        def run(self, *a, **k):
            return self.Done()

    real_subprocess = machine.subprocess
    machine.subprocess = RefusingScheduler()
    try:
        worked, message = machine.install_startup(ENGINE / "timetable.py", root,
                                                  root / "x.log")
    finally:
        machine.subprocess = real_subprocess
    check("a task scheduler that refuses is reported as a refusal, not a success",
          worked is False and "NOTHING is scheduled" in message, message[:90])
else:
    check("a refusal is reported as a refusal (SKIPPED on a Mac: the only way to "
          "exercise it here would be to write a real LaunchAgent)", True)

# The hidden launcher, for the Windows case where the quiet Python is missing.
shim = machine.write_hidden_shim(root / "_state" / "shim.vbs", 'C:\\x\\y.exe "a b"', str(root))
shim_text = shim.read_text(encoding="utf-8")
check("the hidden launcher asks for a hidden window and waits for the command",
      ", 0, True)" in shim_text,
      # The launcher's own line names a made-up Windows program; on a Mac it is not printed.
      shim_text.strip().splitlines()[-2] if machine.IS_WINDOWS else "")
check("and quote marks inside the command are doubled, as that launcher requires",
      '""a b""' in shim_text)


# --- writes can never damage the file already there ---------------------------
print()
print("=== no write empties a file it might fail to fill ===")

bad = []
for path in sorted(ENGINE.glob("*.py")):
    if path.name == "safe_write.py":
        continue                                              # this is the shared file itself
    text = path.read_text(encoding="utf-8")
    at = text.find("open(")
    while at != -1:
        call = text[at:at + 160]
        if '"w"' in call or "'w'" in call:
            if "tmp" not in call:
                bad.append("%s near character %d" % (path.name, at))
        at = text.find("open(", at + 1)
check("every write goes to a temporary file first and is then swapped in",
      not bad, "; ".join(bad))


# --- nothing here schedules anything for real ---------------------------------
print()
print("=== these tests scheduled nothing and started nothing ===")

check("no LaunchAgent was created or removed by these tests",
      AGENT_PATH.exists() == AGENT_EXISTED,
      "a test that registers a real job on your machine is not a test")

# The names below are built from pieces so that writing this check does not put
# the very words it looks for into the file it is reading.
own_source = Path(__file__).read_text(encoding="utf-8")
launches = ["daemon." + "start(", "cli.cmd_" + "start(", "runner." + "start_process("]
check("no background program and no real command was started",
      not any(name in own_source for name in launches),
      "a test that leaves a program running behind it is not a test either")
check("the background program is not running from these tests",
      daemon.running_number() is None)
check("the throwaway CRM is where every file went, not your real one",
      str(root) in str(store.state_path()) and str(root) in str(store.log_path()))

print()
try:
    shutil.rmtree(root, ignore_errors=True)
except OSError:
    pass

if FAILS:
    print("%d check(s) failed:" % len(FAILS))
    for name in FAILS:
        print("   - %s" % name)
    sys.exit(1)
print("all checks passed.")
sys.exit(0)
