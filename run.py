from summariseWeeklyResults import summariseWeeklyResults
from draws import CHECK_TIMES, CHECK_TIMES_TEXT, UK, drawnText, fetchDraws, missingText, readDraws
from history import openHistory
from browserLogin import browserLogin
from datetime import datetime, time, timedelta, timezone
from sendEmail import sendEmail
from time import sleep
import argparse
import html
import os
import traceback


LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

SIGN_IN_FROM = time(14, 0)
PUBLISH_WAIT = timedelta(minutes=15)  # keep re-fetching a draw this long after it's due
REFETCH_SECONDS = 60
EMAIL_ATTEMPTS = 3
EMAIL_RETRY_SECONDS = 30


def _utcNow():
    return datetime.now(timezone.utc)


def main(scheduled=False, retry=False, now=_utcNow, sleep=sleep):
    """Run one check: record every draw, email new wins, and do the daily sign-in and the Sunday
    summary when they're due. Manual runs always sign in; retries never do.
    Returns True if retrying soon could still help: a claimable win wasn't emailed, or a draw that's
    still open couldn't be fetched."""
    screenshot_path = os.path.join(LOGS_DIR, 'error_screenshot.png')
    try:
        with openHistory(os.path.join(LOGS_DIR, 'pastData.json'), os.environ.get("YOUR_POSTCODE", "")) as history:
            errors, retry_soon = _check(history, scheduled, retry, now, sleep)
            today = now().astimezone(UK).date()
            if errors and history.lastErrorEmail == today:
                print('An error email was already sent today; not sending another.')
            elif errors and _sendErrorEmail(errors, screenshot_path):
                history.lastErrorEmail = today
            return retry_soon
    except Exception:
        _sendErrorEmail([_logError('The check failed')], screenshot_path)
        return False
    finally:
        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)


def _check(history, scheduled, retry, now, sleep):
    errors, retry_soon, results_at = [], False, None
    try:
        missing, results_at = _checkDraws(history, now, sleep)
        if missing:
            errors.append(_logError(f"Unavailable from the results API: {missingText(missing)}", trace=False))
            retry_soon = any(now() < draw.closesAt(day) for draw, day in missing)
    except Exception:
        errors.append(_logError('Checking the draws failed'))
        _sendWins(history, now, sleep)  # still retry wins from earlier checks
        retry_soon = True

    uk_now = now().astimezone(UK)
    if not retry and (not scheduled or (history.lastBrowserLogin != uk_now.date() and uk_now.time() >= SIGN_IN_FROM)):
        try:
            browserLogin()
            history.lastBrowserLogin = uk_now.date()
        except Exception:
            errors.append(_logError('The browser sign-in failed'))

    if results_at:
        _sendWeeklySummaryIfDue(history, results_at)
    history.prune(now().astimezone(UK).date())
    return errors, retry_soon or bool(history.pendingWins(now()))


def _checkDraws(history, now, sleep):
    """Record every draw the API shows, re-fetching for a few minutes while a just-due draw is missing.
    Returns the (draw, day) of latest draws still unavailable, and when the last fetch began."""
    while True:
        fetched_at = now()
        drawResults = fetchDraws(sleep=sleep)
        current = now()
        results, missing = readDraws(drawResults, history.postcode, current)
        for result in results:
            history.record(result)
            print(f"{result.draw.label} ({drawnText(result.draw, result.day)}): {result.winningText()}"
                  f"{' — YOUR POSTCODE' if result.hasWon else ''}")
        history.save()
        _sendWins(history, now, sleep)

        current = now()
        if not any(current - draw.drawnAt(day) < PUBLISH_WAIT for draw, day in missing):
            return missing, fetched_at
        print(f"Waiting for {missingText(missing)} to be published...")
        sleep(REFETCH_SECONDS)


def _sendWins(history, now, sleep):
    for attempt in range(1, EMAIL_ATTEMPTS + 1):
        wins = history.pendingWins(now())  # re-checked before every attempt, so a closed prize is never sent
        if not wins:
            return
        win_text, win_html = _winEmail(wins)
        print('Sending winning email')
        if sendEmail(os.environ.get("NOTIFICATION_EMAIL_ADDRESS"), 'You have won the postcode lottery 🎉', win_text, win_html):
            history.markNotified(wins, now())
            history.save()
            return
        if attempt < EMAIL_ATTEMPTS:
            sleep(EMAIL_RETRY_SECONDS)
    print("Couldn't send the winning email; it will be retried while the prize can still be claimed.")


def _winEmail(wins):
    lines = [f"{w.draw.label} (drawn {drawnText(w.draw, w.day)}) — claim before {w.draw.closesAt(w.day):%a %d %b %H:%M}"
             for w in wins]
    first_come = any(w.draw.firstCome for w in wins)
    hurry = "The first person registered at your postcode to claim gets it, so be quick!\n" if first_come else ""
    win_text = (
        "Hey 👋,\n\nYou have won the following draw(s):\n" + "\n".join(f"• {line}" for line in lines) +
        f"\n\n{hurry}Claim it here: https://pickmypostcode.com/\n\nThanks,\nRobot"
    )
    win_html = (
        "<p>Hey 👋,</p><p>You have won the following draw(s):</p><ul>" +
        "".join(f"<li><strong>{html.escape(line)}</strong></li>" for line in lines) + "</ul>" +
        (f"<p>{html.escape(hurry)}</p>" if hurry else "") +
        "<p>Claim it here: <a href=\"https://pickmypostcode.com/\">pickmypostcode.com</a></p>"
        "<p>Thanks,<br>Robot</p>"
    )
    return win_text, win_html


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


def _logError(context, trace=True):
    message = f"{context}:\n{traceback.format_exc()}" if trace else f"{context}."
    print(message)
    return message


def _sendErrorEmail(errors, screenshot_path):
    error_message = "\n\n".join(errors)
    has_screenshot = os.path.exists(screenshot_path)
    return sendEmail(
        os.environ.get("NOTIFICATION_EMAIL_ADDRESS"),
        'Script Error Notification 🚨',
        f'Hey 👋,\n\nAn error occurred while running the script:\n\n{error_message}\n\nPlease check the logs for more details.\n\nThanks,\nRobot',
        f'<p>Hey 👋,<br><br>An error occurred while running the script:<br><pre>{html.escape(error_message)}</pre><br>'
        f'{"Please check the attached screenshot for more details." if has_screenshot else "Please check the logs for more details."}'
        f'<br><br>Thanks,<br>Robot</p>',
        attachment_path=screenshot_path if has_screenshot else None,
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description=f"Check every Pick My Postcode draw once and email any wins. "
                    f"The scheduler (scheduler.py) runs this at {CHECK_TIMES_TEXT}."
    )
    parser.add_argument('--test', action='store_true',
                        help='health check: Selenium, browser sign-in, results API and a summary email')
    if parser.parse_args().test:
        from healthCheck import runTestCheck
        runTestCheck()
    else:
        main()
