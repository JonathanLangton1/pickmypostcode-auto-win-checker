from summariseWeeklyResults import summariseWeeklyResults
from accountCheck import creditDay, dailyAccountCheck
from draws import CHECK_TIMES, CHECK_TIMES_TEXT, UK, drawnText, fetchDraws, missingText, readDraws
from emails import errorEmail, winEmail
from emailTemplate import render
from history import openHistory
from datetime import datetime, time, timedelta, timezone
from sendEmail import sendEmail
from time import sleep
import argparse
import os
import traceback


LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

SIGN_IN_FROM = time(14, 0)  # first scheduled account check; the receipt itself is the noon credit day
PUBLISH_WAIT = timedelta(minutes=15)  # keep re-fetching a draw this long after it's due
REFETCH_SECONDS = 60
EMAIL_ATTEMPTS = 3
EMAIL_RETRY_SECONDS = 30
# UK date of an error email this process has already had accepted. Used when the history
# file cannot be read or saved. A restart forgets it; the file is the mark that survives.
_errorSentFor = None


def _utcNow():
    return datetime.now(timezone.utc)


def main(scheduled=False, retry=False, now=_utcNow, sleep=sleep):
    """Run one check: record every draw, email new wins, and do the daily account check and the
    Sunday summary when they're due. Manual runs always check the account; retries never do.
    Returns True if retrying soon could still help: a claimable win wasn't emailed, or a draw that's
    still open couldn't be fetched."""
    history = None
    try:
        with openHistory(os.path.join(LOGS_DIR, 'pastData.json'), os.environ.get("YOUR_POSTCODE", "")) as history:
            errors, retry_soon = _check(history, scheduled, retry, now, sleep)
            _reportErrors(history, errors, now)
            return retry_soon
    except Exception:
        # Opening or saving history failed. history is set once the file was loaded; a
        # failure before that leaves it None and the process-local mark is all we have.
        _reportErrors(history, [_logError('The check failed')], now)
        return False


def _check(history, scheduled, retry, now, sleep):
    errors, retry_soon, results_at = [], False, None
    try:
        missing, results_at = _checkDraws(history, now, sleep)
        if missing:
            errors.append(_logError(f"Unavailable from the results API: {missingText(missing)}", trace=False))
            retry_soon = any(now() < draw.closesAt(day) for draw, day in missing)
    except Exception:
        errors.append(_logError('Checking the draws failed'))
        _sendWins(history, now, sleep)  # still retry wins from earlier checks that can't have been taken
        retry_soon = True

    checked_at = now()
    uk_now = checked_at.astimezone(UK)
    # The receipt is the noon that opened this credit period, so a manual run before noon
    # does not satisfy the 14:00 check. Nothing is stored unless every draw visit verified.
    if not retry and (not scheduled or (history.lastAccountCheck != creditDay(uk_now) and uk_now.time() >= SIGN_IN_FROM)):
        try:
            result = dailyAccountCheck(now=lambda: checked_at)
            history.lastAccountCheck = result.verified_day
            print(f"Account verified for {result.verified_day} "
                  f"({result.new_credits} new credits, bonus {result.total_bonus}p).")
        except Exception:
            errors.append(_logError('The account check failed'))

    if results_at:
        _sendWeeklySummaryIfDue(history, results_at)
    history.prune(now().astimezone(UK).date())
    return errors, retry_soon or bool(history.pendingWins(now()))


def _checkDraws(history, now, sleep):
    """Record every draw the API shows, re-fetching for a few minutes while a just-due draw is missing.
    Returns the (draw, day) of latest draws still unavailable, and when the last fetch began."""
    while True:
        fetched_at = now()
        missing, observed = _observe(history, now, sleep)
        _sendWins(history, now, sleep, observed)

        current = now()
        if not any(current - draw.drawnAt(day) < PUBLISH_WAIT for draw, day in missing):
            return missing, fetched_at
        print(f"Waiting for {missingText(missing)} to be published...")
        sleep(REFETCH_SECONDS)


def _observe(history, now, sleep):
    """Fetch and record every draw. Returns the (draw, day) of latest draws the API isn't showing,
    and the (draw key, day) of every result it just showed."""
    results, missing = readDraws(fetchDraws(sleep=sleep), history.postcode, now())
    for result in results:
        history.record(result)
        print(f"{result.draw.label} ({drawnText(result.draw, result.day)}): {result.winningText()}"
              f"{' (YOUR POSTCODE)' if result.hasWon else ''}")
    history.save()
    return missing, {(r.draw.key, r.day) for r in results}


def _sendWins(history, now, sleep, observed=frozenset()):
    """Email every win not yet emailed that can still be claimed, together, retrying a failed send.
    Someone else at the postcode can take a first-come prize at any moment, so its win is only sent
    straight after the API showed it unclaimed (it's in `observed`, re-fetched before each retry);
    otherwise it waits for a later check."""
    for attempt in range(1, EMAIL_ATTEMPTS + 1):
        pending = history.pendingWins(now())  # re-checked before every attempt, so a closed prize is never sent
        wins = [w for w in pending if not w.draw.firstCome or (w.draw.key, w.day) in observed]
        if len(wins) < len(pending):
            print("Not sending a first-come win until the results API shows it's still unclaimed.")
        if not wins:
            return
        win_text, win_html = _winEmail(wins, history.postcode, now())
        print('Sending winning email')
        if sendEmail(os.environ.get("NOTIFICATION_EMAIL_ADDRESS"), 'You have won the postcode lottery 🎉', win_text, win_html):
            history.markNotified(wins, now())
            history.save()
            return
        if attempt < EMAIL_ATTEMPTS:
            sleep(EMAIL_RETRY_SECONDS)
            if any(w.draw.firstCome for w in wins):
                observed = _reobserve(history, now, sleep)
    print("Couldn't send the winning email; it will be retried while the prize can still be claimed.")


def _reobserve(history, now, sleep):
    try:
        return _observe(history, now, sleep)[1]
    except Exception as error:
        print(f"Couldn't re-check the results ({error}).")
        return frozenset()


def _winEmail(wins, postcode, now):
    lines = [f"{w.draw.label} (drawn {drawnText(w.draw, w.day)}), claim before {w.draw.closesAt(w.day):%a %d %b %H:%M}"
             for w in wins]
    first_come = any(w.draw.firstCome for w in wins)
    hurry = "The first person registered at your postcode to claim gets it, so be quick!\n" if first_come else ""
    win_text = (
        "Hey 👋,\n\nYou have won the following draw(s):\n" + "\n".join(f"• {line}" for line in lines) +
        f"\n\n{hurry}Claim it here: https://pickmypostcode.com/\n\nThanks,\nRobot"
    )
    return win_text, render(winEmail(wins, postcode, now))


def _sendWeeklySummaryIfDue(history, results_at):
    """Once a week, from results fetched at or after the final Sunday check time (or on Monday if
    that was missed or failed)."""
    uk_now = results_at.astimezone(UK)
    sunday = uk_now.date() - timedelta(days=(uk_now.weekday() + 1) % 7)
    if uk_now < datetime.combine(sunday, CHECK_TIMES[-1], tzinfo=UK) or history.lastWeeklySummary == sunday:
        return
    if uk_now.date() > sunday + timedelta(days=1):
        return
    text, summary_html = summariseWeeklyResults(history, sunday)
    print('Sending data summary')
    if sendEmail(os.environ.get("NOTIFICATION_EMAIL_ADDRESS"), 'Weekly postcode lottery data summary 📊', text, summary_html):
        history.lastWeeklySummary = sunday
        history.save()
    else:
        print("Couldn't send the weekly summary; it will be retried at the next check.")


def _reportErrors(history, errors, now):
    """Send at most one error email per UK day, and only record a send the server accepted.

    The history receipt is used when it is loaded. If this process already had an acceptance
    that could not be saved, that also counts until the process exits.
    """
    global _errorSentFor
    if not errors:
        return
    today = now().astimezone(UK).date()
    if _errorSentFor == today or (history is not None and history.lastErrorEmail == today):
        print('An error email was already sent today; not sending another.')
        return
    if not _sendErrorEmail(errors, now()):
        return
    _errorSentFor = today
    if history is not None:
        history.lastErrorEmail = today


def _logError(context, trace=True):
    message = f"{context}:\n{traceback.format_exc()}" if trace else f"{context}."
    print(message)
    return message


def _sendErrorEmail(errors, now):
    error_message = "\n\n".join(errors)
    return sendEmail(
        os.environ.get("NOTIFICATION_EMAIL_ADDRESS"),
        'Script Error Notification 🚨',
        f'Hey 👋,\n\nAn error occurred while running the script:\n\n{error_message}\n\nPlease check the logs for more details.\n\nThanks,\nRobot',
        render(errorEmail(errors, now)),
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=f"Check every Pick My Postcode draw once and email any wins. "
                    f"The scheduler (scheduler.py) runs this at {CHECK_TIMES_TEXT}."
    )
    parser.add_argument('--test', action='store_true',
                        help='health check: account activity, results API and a summary email')
    if parser.parse_args().test:
        from healthCheck import runTestCheck
        runTestCheck()
    else:
        main()
