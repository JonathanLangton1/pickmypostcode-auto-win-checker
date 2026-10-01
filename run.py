from summariseWeeklyResults import summariseWeeklyResults
from draws import UK, fetchDraws, readDraws
from history import openHistory
from browserLogin import browserLogin
from datetime import datetime, time, timedelta, timezone
from sendEmail import sendEmail
from time import sleep
import argparse
import html
import io
import os
import random
import sys
import traceback
from contextlib import redirect_stdout


LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')

# UK times: a minute after each first-come draw (Stackpot 9am, Mini Draw 6pm, Stackpot 9pm),
# plus the original 2pm run that also signs in for the daily bonus.
CHECK_TIMES = (time(9, 1), time(14, 0), time(18, 1), time(21, 1))
CHECK_TIMES_TEXT = f"{', '.join(t.strftime('%H:%M') for t in CHECK_TIMES[:-1])} and {CHECK_TIMES[-1]:%H:%M} UK time"
SIGN_IN_FROM = time(14, 0)
PUBLISH_WAIT = timedelta(minutes=15)  # keep re-fetching a draw this long after it's due
REFETCH_SECONDS = 60
EMAIL_ATTEMPTS = 3
EMAIL_RETRY_SECONDS = 30

LOSING_DAY_QUIPS = [
    "No dice today. The bot's working perfectly, though. 🤖",
    "Statistically, today was unlikely. Better luck tomorrow!",
    "Not your day. The postcode gods are clearly biased.",
    "Close, but no cigar. (Actually, the cigar is at a completely different postcode.)",
    "Today's result: still no. Like literally every day, with crushing predictability. 📉",
    "Sorry, mate. Maybe tomorrow's the £800 day.",
    "No wins detected. That's just lottery economics, baby.",
]


def _utcNow():
    return datetime.now(timezone.utc)


def _drawnText(draw, day):
    return draw.drawnAt(day).strftime('%a %d %b %H:%M')


def _missingText(missing):
    return ', '.join(f"{draw.label} ({_drawnText(draw, day)})" for draw, day in missing)


def _status(result, now):
    """Short status for a result: 'WIN' only when it can still be claimed."""
    if result.canClaim(now):
        return 'WIN'
    if result.hasWon:
        return 'won · claimed' if result.claimed else 'won · closed'
    return ''


def _buildSummaryHtml(results, missing, postcode, now):
    rows = ""
    for result in results:
        status = _status(result, now)
        winning_str = result.winningText()
        if status == 'WIN':
            result_html = "<span style='color:#2e7d32;font-weight:700;'>🎉 WIN</span>"
            winning_cell = f"<strong style='color:#2e7d32;'>{winning_str}</strong>"
        else:
            result_html = f"<span style='color:#999;'>{status or '—'}</span>"
            winning_cell = winning_str
        rows += f"""
        <tr>
            <td style="padding:12px 14px;border-bottom:1px solid #eee;font-weight:600;">{result.draw.label}<br><span style="font-weight:400;color:#999;font-size:12px;">{_drawnText(result.draw, result.day)}</span></td>
            <td style="padding:12px 14px;border-bottom:1px solid #eee;color:#555;">{winning_cell}</td>
            <td style="padding:12px 14px;border-bottom:1px solid #eee;text-align:center;">{result_html}</td>
        </tr>"""
    for draw, day in missing:
        rows += f"""
        <tr>
            <td style="padding:12px 14px;border-bottom:1px solid #eee;font-weight:600;">{draw.label}<br><span style="font-weight:400;color:#999;font-size:12px;">{_drawnText(draw, day)}</span></td>
            <td style="padding:12px 14px;border-bottom:1px solid #eee;color:#999;">Unavailable</td>
            <td style="padding:12px 14px;border-bottom:1px solid #eee;text-align:center;color:#999;">?</td>
        </tr>"""

    won = [r.draw.label for r in results if r.canClaim(now)]
    if won:
        verdict = f"""
        <div style="background:#e8f5e9;border-left:4px solid #4CAF50;padding:16px 20px;margin:20px 0;border-radius:4px;">
            <p style="margin:0 0 8px 0;font-size:17px;color:#2e7d32;font-weight:600;">
                🎉 You won the {', '.join(won)}!
            </p>
            <p style="margin:0;">
                <a href="https://pickmypostcode.com/" style="color:#2e7d32;font-weight:600;text-decoration:none;">Claim now →</a>
            </p>
        </div>"""
    else:
        verdict = f"""
        <div style="background:#f5f5f5;border-left:4px solid #bbb;padding:16px 20px;margin:20px 0;border-radius:4px;color:#666;">
            <p style="margin:0;font-size:15px;">{_noWinText(missing)}</p>
        </div>"""

    uk_now = now.astimezone(UK)
    return f"""
    <html>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#333;background:#f4f4f4;padding:24px;margin:0;">
      <div style="max-width:640px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
        <div style="background:linear-gradient(135deg,#4CAF50,#2e7d32);color:#fff;padding:28px 24px;text-align:center;">
          <h1 style="margin:0;font-size:22px;font-weight:600;letter-spacing:0.2px;">Pick My Postcode — Daily Check</h1>
          <p style="margin:6px 0 0 0;opacity:0.92;font-size:14px;">{uk_now.strftime('%A, %d %B %Y')}</p>
        </div>
        <div style="padding:24px;">
          <p style="margin:0 0 18px 0;font-size:15px;">
            Hey 👋, here are the latest results for postcode <strong style="color:#1976d2;">{postcode}</strong>:
          </p>
          <table style="width:100%;border-collapse:collapse;font-size:14px;">
            <thead>
              <tr>
                <th style="padding:10px 14px;background:#fafafa;text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:0.6px;color:#777;border-bottom:2px solid #eee;">Draw</th>
                <th style="padding:10px 14px;background:#fafafa;text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:0.6px;color:#777;border-bottom:2px solid #eee;">Winning Postcode</th>
                <th style="padding:10px 14px;background:#fafafa;text-align:center;font-size:12px;text-transform:uppercase;letter-spacing:0.6px;color:#777;border-bottom:2px solid #eee;">Result</th>
              </tr>
            </thead>
            <tbody>{rows}
            </tbody>
          </table>
          {verdict}
          <p style="margin:20px 0 0 0;font-size:12px;color:#999;">
            This was a manual <code>--test</code> run. Normally the bot only emails you on wins (plus a weekly summary on Sunday evenings).
          </p>
        </div>
      </div>
    </body>
    </html>
    """


def _noWinText(missing):
    if missing:
        return f"No wins to claim in the results available, but these are unavailable: {_missingText(missing)}."
    return "No wins to claim right now. The bot is working perfectly — try again later!"


def _buildSummaryText(results, missing, postcode, now):
    lines = [
        "Pick My Postcode — Daily Check",
        now.astimezone(UK).strftime('%A, %d %B %Y'),
        "",
        f"Postcode: {postcode}",
        "",
        "Latest results:",
    ]
    for result in results:
        status = _status(result, now)
        marker = f"  ← {status}" if status else ""
        lines.append(f"  {result.draw.label:<14} {_drawnText(result.draw, result.day)}  {result.winningText()}{marker}")
    for draw, day in missing:
        lines.append(f"  {draw.label:<14} {_drawnText(draw, day)}  unavailable")
    lines.append("")
    won = [r.draw.label for r in results if r.canClaim(now)]
    if won:
        lines.append(f"🎉 You won the {', '.join(won)}!")
        lines.append("Claim at https://pickmypostcode.com/")
    else:
        lines.append(_noWinText(missing))
    return "\n".join(lines)


def runTestCheck():
    """Run the full pipeline once, surface every health check, and email a summary."""
    import requests
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console(force_terminal=True)
    your_postcode = os.environ.get("YOUR_POSTCODE", "")
    notification_email = os.environ.get("NOTIFICATION_EMAIL_ADDRESS", "")
    selenium_url = os.environ.get("SELENIUM_URL", "http://selenium-chrome:4444/wd/hub")
    now = _utcNow()

    console.print()
    console.print(Panel(
        f"[bold]Pick My Postcode — Health Check[/bold]\n"
        f"[dim]{now.astimezone(UK).strftime('%A, %d %B %Y')}[/dim]\n"
        f"Postcode: [bold cyan]{your_postcode or '<not set>'}[/bold cyan]",
        border_style="cyan",
        expand=False,
    ))
    console.print()
    console.print("[bold]System checks[/bold]")

    checks = {}
    results = None
    missing = []

    # 1) Selenium grid reachable
    try:
        status_url = selenium_url.rstrip('/') + '/status'
        with console.status("  Checking Selenium grid...", spinner="dots"):
            r = requests.get(status_url, timeout=5)
        ready = r.json().get('value', {}).get('ready', False)
        if not ready:
            raise RuntimeError(f"grid responded but not ready: {r.json()}")
        console.print("  [green]✓[/green] Selenium grid reachable")
        checks['selenium'] = True
    except Exception as e:
        console.print(f"  [red]✗[/red] Selenium grid — [red]{e}[/red]")
        checks['selenium'] = False

    # 2) Browser flow (login + draw page visits)
    browser_log = io.StringIO()
    try:
        with console.status("  Running browser flow...", spinner="dots"):
            with redirect_stdout(browser_log):
                browserLogin()
        console.print("  [green]✓[/green] Browser flow (sign-in + draw pages)")
        checks['browser'] = True
    except Exception as e:
        console.print(f"  [red]✗[/red] Browser flow — [red]{e}[/red]")
        if browser_log.getvalue():
            console.print(f"[dim]{browser_log.getvalue().strip()}[/dim]")
        checks['browser'] = False

    # 3) Results API fetch
    try:
        with console.status("  Fetching draw results...", spinner="dots"):
            results, missing = readDraws(fetchDraws(), your_postcode, now)
        if missing:
            console.print(f"  [red]✗[/red] Results API — [red]unavailable: {_missingText(missing)}[/red]")
        else:
            console.print("  [green]✓[/green] Results API fetch")
        checks['api'] = not missing
    except Exception as e:
        console.print(f"  [red]✗[/red] Results API — [red]{e}[/red]")
        checks['api'] = False

    # 4) Email delivery (only meaningful if we have results to send)
    if results:
        summary_html = _buildSummaryHtml(results, missing, your_postcode, now)
        text = _buildSummaryText(results, missing, your_postcode, now)
        with console.status(f"  Sending summary email to {notification_email}...", spinner="dots"):
            email_ok = sendEmail(
                notification_email,
                f"Pick My Postcode — {now.astimezone(UK).strftime('%a %d %b')} results",
                text,
                summary_html,
            )
        if email_ok:
            console.print(f"  [green]✓[/green] Summary email delivered to [bold]{notification_email}[/bold]")
            checks['email'] = True
        else:
            console.print("  [red]✗[/red] Email — check EMAIL_ADDRESS / EMAIL_PASSWORD in .env")
            checks['email'] = False
    else:
        console.print("  [yellow]–[/yellow] Email skipped (no results to send)")
        checks['email'] = None

    # Overall verdict
    console.print()
    all_passed = all(v is True for v in checks.values())
    if all_passed:
        console.print("[bold green]✅ All systems operational — full pipeline working[/bold green]")
    else:
        failed = [k for k, v in checks.items() if v is False]
        console.print(f"[bold red]❌ Failed checks: {', '.join(failed)}[/bold red]")
    console.print()

    # Latest results table
    if results:
        table = Table(box=box.ROUNDED, header_style="bold cyan", title="[bold]Latest Winners[/bold]", title_justify="left")
        table.add_column("Draw", style="bold")
        table.add_column("Drawn")
        table.add_column("Winning Postcode")
        table.add_column("Yours?", justify="center")
        for result in results:
            winning_str = result.winningText()
            if isinstance(result.winningPostcode, tuple) and len(result.winningPostcode) > 3:
                head = ', '.join(result.winningPostcode[:3])
                winning_str = f"{head} [dim](+{len(result.winningPostcode) - 3} more)[/dim]"
            status = _status(result, now)
            drawn = _drawnText(result.draw, result.day)
            if status == 'WIN':
                table.add_row(result.draw.label, drawn, f"[bold green]{winning_str}[/bold green]", "[bold green]🎉 WIN[/bold green]")
            else:
                table.add_row(result.draw.label, drawn, winning_str, f"[dim]{status or '–'}[/dim]")
        for draw, day in missing:
            table.add_row(draw.label, _drawnText(draw, day), "[yellow]unavailable[/yellow]", "[yellow]?[/yellow]")
        console.print(table)
        console.print()

        # Win / lose reveal
        won = [r.draw.label for r in results if r.canClaim(now)]
        if won:
            console.print(Panel(
                f"[bold green]🎉  JACKPOT! 🎉[/bold green]\n\n"
                f"You won the [bold]{', '.join(won)}[/bold]!\n"
                f"[link=https://pickmypostcode.com/]Claim at pickmypostcode.com →[/link]",
                border_style="green",
                expand=False,
            ))
        elif missing:
            console.print(Panel(
                "[yellow]These results are incomplete, so this isn't a confirmed no-win.[/yellow]",
                border_style="yellow",
                expand=False,
            ))
        else:
            console.print(Panel(
                f"[dim]{random.choice(LOSING_DAY_QUIPS)}[/dim]",
                border_style="grey50",
                expand=False,
            ))
        console.print()

    # What happens from here (only meaningful if setup is healthy)
    if all_passed:
        console.print(Panel(
            f"[bold]Sit back and relax[/bold] — the bot checks every draw daily at\n"
            f"[bold]{CHECK_TIMES_TEXT}[/bold].\n\n"
            "You'll automatically get:\n"
            "• A [bold green]winning email[/bold green] (with a claim link) every time your postcode hits,\n"
            "  including the 6pm Mini Draw and both Stackpot draws\n"
            "• A [bold]weekly summary[/bold] every Sunday evening",
            title="[bold]What happens next[/bold]",
            title_align="left",
            border_style="cyan",
            expand=False,
        ))
        console.print()
    else:
        sys.exit(1)


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
            errors.append(_logError(f"Unavailable from the results API: {_missingText(missing)}", trace=False))
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
            print(f"{result.draw.label} ({_drawnText(result.draw, result.day)}): {result.winningText()}"
                  f"{' — YOUR POSTCODE' if result.hasWon else ''}")
        history.save()
        _sendWins(history, now, sleep)

        current = now()
        if not any(current - draw.drawnAt(day) < PUBLISH_WAIT for draw, day in missing):
            return missing, fetched_at
        print(f"Waiting for {_missingText(missing)} to be published...")
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
    lines = [f"{w.draw.label} (drawn {_drawnText(w.draw, w.day)}) — claim before {w.draw.closesAt(w.day):%a %d %b %H:%M}"
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
        runTestCheck()
    else:
        main()
