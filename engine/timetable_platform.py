"""
timetable_platform.py - the two places Windows and a Mac genuinely differ.

Everything else in this layer is the same on both machines. Three matters are not,
and they are all gathered here so no other file has to know which machine it is on:

  1. STARTING A PROGRAM WITHOUT A WINDOW.  On Windows, starting a program from a
     program makes the operating system give the new program its own console
     window - a black box that appears on screen, on top of whatever you were
     doing. On a Mac there is no console window to appear, so this is a Windows
     matter only and every function below is a quiet no-op there.

  2. TELLING ONE RUNNING PROGRAM FROM ANOTHER.  Every running program has a
     number, called a process number. The operating system reuses those numbers
     after a program ends, so a number on its own is a label rather than a name.
     `born()` reads the moment a program started, and the pair (number, moment)
     is what actually identifies it.

  3. STARTING AT LOGIN.  Windows has a task scheduler; a Mac has launchd. Both
     are per-user and neither asks for an administrator password.

WHY THE NO-WINDOW RULE IS THE MOST IMPORTANT PART OF THIS FILE

  On 2026-07-27 a set of about forty scheduled jobs on one Windows machine were
  each opening a console window when they fired. The work they did was correct.
  The windows were the reason the whole set nearly got switched off, because a
  box appearing over your work several times an hour is intolerable however
  useful the work behind it is.

  Two corrections came out of that day and both are in this file:

    * A Python program started as `pythonw.exe` rather than `python.exe` has no
      console at all. That covers the background program this layer starts.
    * `pythonw` hides the PARENT only. When a program with no console starts
      another program, Windows gives THAT one a fresh console window. Capturing
      its output does not prevent this - capturing redirects where the output
      goes, it does not stop the window being created. Every start of another
      program therefore has to carry the CREATE_NO_WINDOW flag, which is what
      `no_window()` returns.

  Both are applied here, one over the other, deliberately.

Needs: Python 3.8 or newer. Nothing else. `psutil` is used if you happen to have
it and is not required.
"""

import os
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

TASK_NAME = "Outliers Timetable"
LAUNCH_AGENT_LABEL = "com.outliers.gather.timetable"

# How far apart two readings of the same program's start moment may be before we
# call them different programs. Readings come from the same source at different
# moments, so a second or two of disagreement is measurement, not identity. A
# reused process number is handed out hours or days later, never inside a few
# seconds, so this is generous without being loose.
SAME_PROGRAM_SECONDS = 5.0

try:
    import psutil                                             # noqa: F401
    HAVE_PSUTIL = True
except ImportError:
    HAVE_PSUTIL = False


# ------------------------------------------------ starting without a window

def no_window():
    """Extra arguments that stop a started program from being given a window.

    Pass these to every single start of another program from inside anything that
    runs unattended. See the 2026-07-27 note at the top: a parent with no console
    does not protect its children, and capturing output does not either.

    On a Mac this returns nothing at all, because there is no console window to
    suppress. A Mac member is not missing a feature here - the problem does not
    exist on that machine.
    """
    if IS_WINDOWS:
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def detached():
    """Extra arguments that let a started program outlive the window it was
    started from, so closing the terminal does not end it."""
    if IS_WINDOWS:
        return {"creationflags": (getattr(subprocess, "DETACHED_PROCESS", 0)
                                  | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))}
    return {"start_new_session": True}


def detached_no_window():
    """Both of the above, which is how the background program itself is started."""
    if IS_WINDOWS:
        return {"creationflags": (getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                  | getattr(subprocess, "DETACHED_PROCESS", 0)
                                  | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))}
    return {"start_new_session": True}


def quiet_python():
    """The Python to start Python programs with, so none of them gets a console.

    On Windows there are two copies of Python side by side: `python.exe`, which
    always has a console window, and `pythonw.exe`, which has none. They run the
    same code. On a Mac there is one, and it is the answer.
    """
    if not IS_WINDOWS:
        return sys.executable
    quiet = Path(sys.executable).with_name("pythonw.exe")
    return str(quiet) if quiet.exists() else sys.executable


PYTHON_NAMES = ("python", "python.exe", "python3", "python3.exe", "py", "py.exe")


def windowless_command(parts):
    """Rewrite a command so that, if it starts Python, it starts the quiet one.

    This is deliberately doubled up with `no_window()` rather than replacing it.
    The flag covers the moment this layer starts your command. The rewrite covers
    the case where the same command line is later read by a person, copied into
    the Windows task scheduler by hand, and fired from there with no flag in
    sight. Belt and braces, because the failure it prevents is the one that makes
    people switch a timetable off.

    On a Mac the rewrite has a different job. Started at login, the timetable gets
    launchd's short list of folders to look in, where a plain `python` does not
    exist and `python3` is Apple's own older copy, without the add-ons you
    installed. So a command that starts with a bare Python name is pointed at the
    Python running the timetable, which is the one you installed them into. A full
    path you typed yourself is left exactly as you wrote it.
    """
    if not parts:
        return list(parts)
    head = str(parts[0])
    if IS_MAC:
        if head in PYTHON_NAMES and "/" not in head:
            return [sys.executable] + [str(p) for p in parts[1:]]
        return list(parts)
    if not IS_WINDOWS:
        return list(parts)
    if Path(head).name.lower() not in PYTHON_NAMES:
        return list(parts)
    quiet = quiet_python()
    if Path(quiet).name.lower().startswith("pythonw"):
        return [quiet] + [str(p) for p in parts[1:]]
    return list(parts)


# ------------------------------------------------- which program is which

def alive(number):
    """Is there a running program with this process number, right now?"""
    if not number:
        return False
    number = int(number)
    if HAVE_PSUTIL:
        try:
            p = psutil.Process(number)
            return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
        except Exception:                                     # noqa: BLE001
            return False
    if IS_WINDOWS:
        return _windows_alive(number)
    try:
        os.kill(number, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True                # it exists; it is somebody else's
    except OSError:
        return False


def born(number):
    """The moment this program started, in seconds, or None if it cannot be read.

    None means UNKNOWN and must never be read as "different program". Anything
    calling this has to carry on trusting the process number when the answer is
    None, because wrongly declaring a live program dead is the worse of the two
    mistakes: it lets a second copy start alongside the first.
    """
    if not number:
        return None
    number = int(number)
    if HAVE_PSUTIL:
        try:
            return float(psutil.Process(number).create_time())
        except Exception:                                     # noqa: BLE001
            return None
    if IS_WINDOWS:
        return _windows_born(number)
    return _posix_born(number)


def same_program(number, recorded):
    """Is the program running under this number the one that wrote the record?

    On 2026-07-26 a background program was ended without tidying up, so the file
    naming its process number survived it. Hours later the operating system gave
    that same number - 31192 - to an unrelated laptop utility. The checker read
    the number, found a running program under it, and reported the dead job as
    running. It then refused to start the real one, because as far as it could
    see one was already going. Two days of no work, reported as healthy.

    A number that can be reused is a label, not an identity. The pair (number,
    moment it started) is the identity, so the record carries both.

    Only a POSITIVE disagreement demotes a number. Unknown keeps the number
    trusted - see `born()` for why that is the safe direction.
    """
    if not alive(number):
        return False
    started = born(number)
    if started is None:
        return True
    if recorded in (None, ""):
        return True
    try:
        return abs(started - float(recorded)) <= SAME_PROGRAM_SECONDS
    except (TypeError, ValueError):
        return True


def end(number):
    """End a running program and anything it started. Returns True if it tried."""
    if not number:
        return False
    number = int(number)
    if IS_WINDOWS:
        try:
            subprocess.run(["taskkill", "/PID", str(number), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           **no_window())
            return True
        except OSError:
            return False
    import signal
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(number), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(number, sig)
            except OSError:
                return True
        if not alive(number):
            return True
    return True


def _windows_alive(number):
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return True
    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x1000, False, number)        # QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True
        return code.value == 259                             # STILL_ACTIVE
    finally:
        kernel.CloseHandle(handle)


def _windows_born(number):
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None
    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x1000, False, number)
    if not handle:
        return None
    try:
        created, ended, in_kernel, in_user = (wintypes.FILETIME() for _ in range(4))
        ok = kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(ended),
                                    ctypes.byref(in_kernel), ctypes.byref(in_user))
        if not ok:
            return None
        raw = (created.dwHighDateTime << 32) | created.dwLowDateTime
        # Windows counts in ten-millionths of a second from the year 1601.
        return raw / 10000000.0 - 11644473600.0
    finally:
        kernel.CloseHandle(handle)


def _posix_born(number):
    """Read how long the program has been going, and subtract.

    `ps -o etime=` is asked for rather than the start date because elapsed time
    is the same everywhere, while a printed date changes with the language the
    machine is set to. Resolution is one second, which is why
    SAME_PROGRAM_SECONDS is not tighter than it is.
    """
    import time
    try:
        out = subprocess.run(["ps", "-p", str(number), "-o", "etime="],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not out:
        return None
    days = 0
    if "-" in out:
        head, out = out.split("-", 1)
        try:
            days = int(head)
        except ValueError:
            return None
    pieces = out.split(":")
    try:
        pieces = [int(p) for p in pieces]
    except ValueError:
        return None
    while len(pieces) < 3:
        pieces.insert(0, 0)
    hours, minutes, seconds = pieces[-3:]
    elapsed = days * 86400 + hours * 3600 + minutes * 60 + seconds
    return time.time() - elapsed


# --------------------------------------------------------- starting at login

SHIM = """Option Explicit
Dim sh, fso, rc, wd
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
wd = "%(workdir)s"
If wd <> "" Then
  If fso.FolderExists(wd) Then sh.CurrentDirectory = wd
End If
rc = sh.Run("%(command)s", 0, True)
WScript.Quit rc
"""


def write_hidden_shim(path, command, workdir=""):
    """Write the small Windows launcher that starts a command with no window.

    Windows only, and only for the case where the quiet Python is missing. The
    task scheduler is pointed at `wscript.exe`, which draws nothing, and this
    file tells it what to start with window style 0, which means hidden.

    The two arguments to Run are fixed and must not be changed. 0 is hidden.
    True means wait for the command to finish, which is what lets the task
    scheduler report a real duration, a real result, and refuse to start a second
    copy while the first is still going.

    `-WindowStyle Hidden` on PowerShell is not an alternative: the console is
    created first and flashes on screen before the setting takes effect.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = SHIM % {"workdir": str(workdir).replace('"', '""'),
                   "command": str(command).replace('"', '""')}
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(body)
    os.replace(tmp, path)
    return path


def install_startup(script, work_dir, log_path):
    """Ask this machine to start the background program every time you log in.

    Windows: a logon task, owned by you, no administrator password. It is pointed
    at the quiet Python so nothing appears on screen when you log in. If the quiet
    Python is missing, a hidden launcher is written first and the task is pointed
    at that instead.

    Mac: a LaunchAgent in your own Library folder, which starts it at login and
    starts it again if it ever ends. No administrator password either.

    Returns (worked, a sentence for a person to read). The first half is there
    because a refusal that prints alongside an explanation of how well it went
    reads as success, and a member would walk away believing a job is scheduled
    that is not.
    """
    if IS_MAC:
        return _install_launch_agent(script, work_dir, log_path)
    if IS_WINDOWS:
        return _install_logon_task(script, work_dir)
    return (False,
            "Starting at login is not set up automatically on this system. "
            "On Linux, add a systemd --user unit that runs: %s %s run"
            % (sys.executable, script))


def _install_logon_task(script, work_dir):
    quiet = quiet_python()
    if Path(quiet).name.lower().startswith("pythonw"):
        command = '"%s" "%s" run' % (quiet, script)
    else:
        shim = Path(work_dir) / "start-timetable.vbs"
        write_hidden_shim(shim, '""%s"" ""%s"" run' % (quiet, script), work_dir)
        command = 'C:\\Windows\\System32\\wscript.exe //B //Nologo "%s"' % shim
    try:
        done = subprocess.run(["schtasks", "/Create", "/F", "/TN", TASK_NAME,
                               "/SC", "ONLOGON", "/TR", command],
                              capture_output=True, text=True, **no_window())
    except OSError as err:
        return False, "Could not reach the Windows task scheduler: %s" % err
    if done.returncode == 0:
        return True, ("Installed. The task is called %r and starts the timetable "
                      "every time you log in, with no window." % TASK_NAME)
    return False, ("The Windows task scheduler refused, so NOTHING is scheduled: %s"
                   % ((done.stderr or done.stdout).strip()[:200] or "no reason given"))


def _install_launch_agent(script, work_dir, log_path):
    import plistlib
    agents = Path.home() / "Library" / "LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    target = agents / ("%s.plist" % LAUNCH_AGENT_LABEL)
    plan = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [sys.executable, str(script), "run"],
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(work_dir),
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(log_path),
    }
    try:
        tmp = target.with_name(target.name + ".tmp")
        with open(tmp, "wb") as fh:
            plistlib.dump(plan, fh)
        os.replace(tmp, target)
    except OSError as err:
        return False, "Could not write the LaunchAgent: %s" % err
    subprocess.run(["launchctl", "unload", str(target)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    done = subprocess.run(["launchctl", "load", "-w", str(target)],
                          capture_output=True, text=True)
    if done.returncode == 0:
        return True, ("Installed. %s starts the timetable by itself when you switch on your Mac "
                      "and sign in." % LAUNCH_AGENT_LABEL)
    return False, ("launchctl refused, so NOTHING is scheduled: %s"
                   % ((done.stderr or done.stdout).strip()[:200] or "no reason given"))


def remove_startup():
    """Undo `install_startup`. Returns (worked, a sentence for a person to read)."""
    if IS_MAC:
        target = Path.home() / "Library" / "LaunchAgents" / ("%s.plist" % LAUNCH_AGENT_LABEL)
        if not target.exists():
            return True, "There was no LaunchAgent to remove."
        subprocess.run(["launchctl", "unload", str(target)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        target.rename(target.with_suffix(".plist.removed"))
        return True, "Removed. It will no longer start by itself when you switch on your Mac and sign in."
    if IS_WINDOWS:
        done = subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK_NAME],
                              capture_output=True, text=True, **no_window())
        if done.returncode == 0:
            return True, "Removed. It will not start at login any more."
        return False, ("Nothing to remove, or the task scheduler refused: %s"
                       % (done.stderr or done.stdout).strip()[:200])
    return True, "Nothing was installed to remove on this system."
