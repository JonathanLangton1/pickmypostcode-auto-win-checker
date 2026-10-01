"""Runs a check at startup, then at each of run.CHECK_TIMES in UK time, whatever the host's TZ.
A check that asks for a retry (an unsent win, or a still-open draw it couldn't fetch) is
followed by a lighter retry check RETRY_AFTER later, unless a normal check is due sooner."""
from datetime import datetime, timedelta, timezone
from time import sleep
import traceback
from draws import UK
from run import CHECK_TIMES, CHECK_TIMES_TEXT, main

RETRY_AFTER = timedelta(minutes=5)


def nextCheck(now):
    """The first check time strictly after `now`."""
    today = now.astimezone(UK).date()
    for day in (today, today + timedelta(days=1)):
        for at in CHECK_TIMES:
            due = datetime.combine(day, at, tzinfo=UK)
            if due > now:
                return due


def runForever(check, now=lambda: datetime.now(timezone.utc), sleep=sleep):
    """Calls check(retry) immediately (catching up on anything still open), then on schedule.
    check returns True to ask for a retry."""
    retry = False
    while True:
        scheduled = nextCheck(now())  # taken before the check, so a long check can't skip past it
        try:
            wants_retry = check(retry)
        except Exception:
            traceback.print_exc()
            wants_retry = False
        current = now()
        due = max(scheduled, current)
        retry = scheduled > current and bool(wants_retry) and current + RETRY_AFTER < scheduled
        if retry:
            due = current + RETRY_AFTER
        print(f"{'Retrying' if retry else 'Next check'} at {due.astimezone(UK):%a %d %b %H:%M %Z}.", flush=True)
        while (wait := (due - now()).total_seconds()) > 0:
            sleep(min(wait, 60))


if __name__ == '__main__':
    print(f"Scheduler started — checking now, then daily at {CHECK_TIMES_TEXT}.", flush=True)
    runForever(lambda retry: main(scheduled=True, retry=retry))
