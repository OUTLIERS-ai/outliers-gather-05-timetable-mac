# What I stole

Nothing in this layer is original, and none of it cost anything. Naming where each idea came from
is the practice, not a courtesy — you should be able to do the same on your next build, and knowing
what already exists is most of the work.

This layer is unusual in the set, because almost all of it was stolen from **one working system
that had already been wrong in public**. Every behaviour below was paid for by a failure with a
date on it.

---

## The whole shape of the loop — from a working scheduler, generalised

The engine underneath this is a daily automation loop that has been running unattended on one
machine since early 2026. It ran jobs by name from a fixed list of four. This layer keeps the loop
and throws away the list: it runs any command line at all.

That is the only change worth making to a piece of software that already works. It is also the
change that makes it reusable, because a timetable that knows what a job IS can only ever schedule
the jobs somebody thought of first.

**What was taken unchanged**, because each of these was earned:

| Behaviour | What it cost to learn |
|---|---|
| The record of what has run, written **before** the command starts | A run interrupted halfway would otherwise get a second turn on the next wake-up. |
| The two-hour late window | A laptop asleep at nine otherwise never runs the nine o'clock job, and nothing says why. |
| The firing minute worked out rather than rolled | Covered below. |
| The sign of life written the instant it starts | 2026-07-19. Two days of a healthy program reported as hung. |
| The process number recorded with the moment it started | 2026-07-26. A dead job's number 31192 handed to a laptop utility. |
| A time allowance per entry, not one over everything | 2026-07-25, 26 actions lost. 2026-07-31, a run ended at 15 of 40. |
| Being alive judged on observed progress | Elapsed time cannot tell a slow job from a stuck one. |

**What was deliberately NOT taken.** That system's scheduler also knows about working hours, daily
limits, weekly limits and a shared counter. None of it is here. This layer answers "when" and
nothing else, because the moment a timetable starts having opinions about whether a job should run,
there are two places holding that rule and they will disagree. The layer underneath owns it.

---

## The worked-out firing time — from a survey of automation vendors, inverted

Every outreach tool sold as a service adds a random delay to its schedule, and most of them say so
in their marketing. The reason is sound: a job firing at exactly 09:30:00 every day is a pattern no
person produces.

**The implementation is taken; the randomness is not.** A rolled number is re-rolled every time it
is asked for, and the loop asks dozens of times an hour. That turns "fires around half nine" into
"drifts through the morning, fires early, and fires again after a restart". Working the shift out
from the entry's name and the date gives the identical scatter with none of the drift, because the
same question always gets the same answer.

**And the honest caveat those vendors do not print.** A hash of the name and the date will
occasionally hand you yesterday's minute again — with a four-minute range, roughly one day in nine.
"Occasionally identical" is exactly the pattern being avoided, so the step from one day to the next
is chosen to make a repeat impossible. The cost is that one entry's minutes walk the range in a
repeating order rather than scattering freely. That trade is stated here rather than hidden,
because you might make it the other way.

---

## The hidden launcher — from a standing rule on one Windows machine, July 2026

The pattern for starting a scheduled job on Windows with no window at all — point the task at
`wscript.exe`, which draws nothing, and let a four-line script start the real command with window
style 0 — is lifted from a rule written after around forty scheduled jobs were found each popping a
console window when they fired.

Three details of that rule are copied exactly and should not be changed:

- **`pythonw.exe`, never `python.exe`**, for anything Python.
- **The hidden launcher waits for its command.** That is what lets the Windows task scheduler
  report a real duration, a real result, and refuse to start a second copy while the first is
  going.
- **`-WindowStyle Hidden` on PowerShell is not an alternative.** The console is created first and
  flashes on screen before the setting takes effect.

**What was deliberately NOT taken.** The same rule mentions moving a job to run whether or not you
are logged on. That looks like a tidier fix and it is a trap: it moves the job to a different
session, where anything driving a browser or raising a notification stops working. Stay in your own
session and hide the window.

---

## Telling one running program from another — from the standard process library

Reading the moment a program started is a solved problem: on Windows the operating system will tell
you directly, on a Mac and on Linux `ps` will. A widely used Python library called `psutil` wraps
all three, and this layer uses it **if you happen to have it** and asks the operating system
directly if you do not.

Taking the idea and not the dependency is deliberate. A timetable that will not run until you have
installed something is a timetable that does not run.

---

## What nothing here does

No paid service. No account with anybody. No key, token or subscription. Nothing leaves your
machine at all — this layer starts commands and reads what they print, and whether any of them go
anywhere is their business, not its.
