from summariseWeeklyResults import summariseWeeklyResults
from checkResults import checkResults
from browserLogin import browserLogin
from datetime import datetime, date
from sendEmail import sendEmail
import io
import json
import os
import random
import sys
import traceback
from contextlib import redirect_stdout


DRAW_LABELS = {
    'mainDraw':        'Main Draw',
    'surveyDraw':      'Survey Draw',
    'videoDraw':       'Video Draw',
    'stackpotDraw':    'Stackpot',
    'bonusDrawFive':   'Bonus £5',
    'bonusDrawTen':    'Bonus £10',
    'bonusDrawTwenty': 'Bonus £20',
    'miniDraw':        'Mini Draw',
}

LOSING_DAY_QUIPS = [
    "No dice today. The bot's working perfectly, though. 🤖",
    "Statistically, today was unlikely. Better luck tomorrow!",
    "Not your day. The postcode gods are clearly biased.",
    "Close, but no cigar. (Actually, the cigar is at a completely different postcode.)",
    "Today's result: still no. Like literally every day, with crushing predictability. 📉",
    "Sorry, mate. Maybe tomorrow's the £800 day.",
    "No wins detected. That's just lottery economics, baby.",
]


def _winningPostcodeText(winning):
    """Format a draw's winning postcode (string or list) into a single readable string."""
    if isinstance(winning, list):
        return ', '.join(winning) if winning else '—'
    return winning or '—'


def _buildSummaryHtml(results, postcode, today):
    rows = ""
    for key, label in DRAW_LABELS.items():
        data = results['drawResults'][key]
        winning_str = _winningPostcodeText(data['winningPostcode'])
        if data['hasWon']:
            result_html = "<span style='color:#2e7d32;font-weight:700;'>🎉 WIN</span>"
            winning_cell = f"<strong style='color:#2e7d32;'>{winning_str}</strong>"
        else:
            result_html = "<span style='color:#999;'>—</span>"
            winning_cell = winning_str
        rows += f"""
        <tr>
            <td style="padding:12px 14px;border-bottom:1px solid #eee;font-weight:600;">{label}</td>
            <td style="padding:12px 14px;border-bottom:1px solid #eee;color:#555;">{winning_cell}</td>
            <td style="padding:12px 14px;border-bottom:1px solid #eee;text-align:center;">{result_html}</td>
        </tr>"""

    if results['hasWon']:
        won = [DRAW_LABELS[k] for k, v in results['drawResults'].items() if v['hasWon']]
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
        verdict = """
        <div style="background:#f5f5f5;border-left:4px solid #bbb;padding:16px 20px;margin:20px 0;border-radius:4px;color:#666;">
            <p style="margin:0;font-size:15px;">No wins today. The bot is working perfectly — try again tomorrow!</p>
        </div>"""

    return f"""
    <html>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;color:#333;background:#f4f4f4;padding:24px;margin:0;">
      <div style="max-width:640px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
        <div style="background:linear-gradient(135deg,#4CAF50,#2e7d32);color:#fff;padding:28px 24px;text-align:center;">
          <h1 style="margin:0;font-size:22px;font-weight:600;letter-spacing:0.2px;">Pick My Postcode — Daily Check</h1>
          <p style="margin:6px 0 0 0;opacity:0.92;font-size:14px;">{today.strftime('%A, %d %B %Y')}</p>
        </div>
        <div style="padding:24px;">
          <p style="margin:0 0 18px 0;font-size:15px;">
            Hey 👋, here are today's results for postcode <strong style="color:#1976d2;">{postcode}</strong>:
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
            This was a manual <code>--test</code> run. Normally the bot only emails you on wins (or weekly summaries on Sundays).
          </p>
        </div>
      </div>
    </body>
    </html>
    """


def _buildSummaryText(results, postcode, today):
    lines = [
        "Pick My Postcode — Daily Check",
        today.strftime('%A, %d %B %Y'),
        "",
        f"Postcode: {postcode}",
        "",
        "Today's results:",
    ]
    for key, label in DRAW_LABELS.items():
        data = results['drawResults'][key]
        winning_str = _winningPostcodeText(data['winningPostcode'])
        marker = "  ← WIN" if data['hasWon'] else ""
        lines.append(f"  {label:<14} {winning_str}{marker}")
    lines.append("")
    if results['hasWon']:
        won = [DRAW_LABELS[k] for k, v in results['drawResults'].items() if v['hasWon']]
        lines.append(f"🎉 You won the {', '.join(won)}!")
        lines.append("Claim at https://pickmypostcode.com/")
    else:
        lines.append("No wins today. The bot is working — try again tomorrow!")
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
    today = date.today()

    console.print()
    console.print(Panel(
        f"[bold]Pick My Postcode — Health Check[/bold]\n"
        f"[dim]{today.strftime('%A, %d %B %Y')}[/dim]\n"
        f"Postcode: [bold cyan]{your_postcode or '<not set>'}[/bold cyan]",
        border_style="cyan",
        expand=False,
    ))
    console.print()
    console.print("[bold]System checks[/bold]")

    checks = {}
    results = None

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
            results = checkResults(your_postcode)
        console.print("  [green]✓[/green] Results API fetch")
        checks['api'] = True
    except Exception as e:
        console.print(f"  [red]✗[/red] Results API — [red]{e}[/red]")
        checks['api'] = False

    # 4) Email delivery (only meaningful if we have results to send)
    if results:
        html = _buildSummaryHtml(results, your_postcode, today)
        text = _buildSummaryText(results, your_postcode, today)
        with console.status(f"  Sending summary email to {notification_email}...", spinner="dots"):
            email_ok = sendEmail(
                notification_email,
                f"Pick My Postcode — {today.strftime('%a %d %b')} results",
                text,
                html,
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

    # Today's results table
    if results:
        table = Table(box=box.ROUNDED, header_style="bold cyan", title="[bold]Today's Winners[/bold]", title_justify="left")
        table.add_column("Draw", style="bold")
        table.add_column("Winning Postcode")
        table.add_column("Yours?", justify="center")
        for key, label in DRAW_LABELS.items():
            data = results['drawResults'][key]
            winning_str = _winningPostcodeText(data['winningPostcode'])
            if isinstance(data['winningPostcode'], list) and len(data['winningPostcode']) > 3:
                head = ', '.join(data['winningPostcode'][:3])
                winning_str = f"{head} [dim](+{len(data['winningPostcode']) - 3} more)[/dim]"
            if data['hasWon']:
                table.add_row(label, f"[bold green]{winning_str}[/bold green]", "[bold green]🎉 WIN[/bold green]")
            else:
                table.add_row(label, winning_str, "[dim]–[/dim]")
        console.print(table)
        console.print()

        # Win / lose reveal
        if results['hasWon']:
            won = [DRAW_LABELS[k] for k, v in results['drawResults'].items() if v['hasWon']]
            console.print(Panel(
                f"[bold green]🎉  JACKPOT! 🎉[/bold green]\n\n"
                f"You won the [bold]{', '.join(won)}[/bold]!\n"
                f"[link=https://pickmypostcode.com/]Claim at pickmypostcode.com →[/link]",
                border_style="green",
                expand=False,
            ))
        else:
            console.print(Panel(
                f"[dim]{random.choice(LOSING_DAY_QUIPS)}[/dim]",
                border_style="grey50",
                expand=False,
            ))
        console.print()

    if not all_passed:
        sys.exit(1)


def main():
    try:
        # This is needed if executing file from outside of project root directory
        script_dir = os.path.dirname(__file__)

        # If database file doesn't exist, create one
        if not os.path.isfile(f'{script_dir}/logs/pastData.json'):
            with open(f'{script_dir}/logs/pastData.json', 'w') as f:
                f.write("{}")

        # Sign in using Selenium
        browserLogin()

        # Get results
        results = checkResults(os.environ.get("YOUR_POSTCODE"))

        # If won, send email containing which draw you have won & a link to claim
        if results['hasWon']:
            winningDraws = [name for name, data in results['drawResults'].items() if data['hasWon']]
            print('Sending winning email')
            win_text = (
                f"Hey 👋,\n\nYou have won the following draw(s): {', '.join(winningDraws)}.\n"
                "Claim it here: https://pickmypostcode.com/\n\nThanks,\nRobot"
            )
            win_html = (
                f"<p>Hey 👋,</p><p>You have won the following draw(s): "
                f"<strong>{', '.join(winningDraws)}</strong>.</p>"
                f"<p>Claim it here: <a href=\"https://pickmypostcode.com/\">pickmypostcode.com</a></p>"
                f"<p>Thanks,<br>Robot</p>"
            )
            sendEmail(
                os.environ.get("NOTIFICATION_EMAIL_ADDRESS"),
                'You have won the postcode lottery 🎉',
                win_text,
                win_html,
            )

        # If day is Sunday, send report of weekly data & also delete logs
        if date.today().weekday() == 6:
            summary = summariseWeeklyResults(os.environ.get("YOUR_POSTCODE"))
            print('Sending data summary')
            with open(f'{script_dir}/logs/pastData.json') as f:
                weeklyData = json.load(f)

            sendEmail(
                os.environ.get("NOTIFICATION_EMAIL_ADDRESS"),
                'Weekly postcode lottery data summary 📊',
                f'Hey 👋,\n\n {weeklyData} \n\nThanks,\nRobot',
                summary
            )

    except Exception as e:
        # Capture the traceback to include in the error email
        error_message = traceback.format_exc()
        print("An error occurred: ", error_message)

        # Attempt to send an error notification email
        try:
            screenshot_path = f'{script_dir}/logs/error_screenshot.png'
            sendEmail(
                os.environ.get("NOTIFICATION_EMAIL_ADDRESS"),
                'Script Error Notification 🚨',
                f'Hey 👋,\n\nAn error occurred while running the script:\n\n{error_message}\n\nPlease check the logs for more details.\n\nThanks,\nRobot',
                f'<p>Hey 👋,<br><br>An error occurred while running the script:<br><pre>{error_message}</pre><br>Please check the attached screenshot for more details.<br><br>Thanks,<br>Robot</p>',
                attachment_path=screenshot_path if os.path.exists(screenshot_path) else None
            )

            # Delete the screenshot after sending the email
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)
                print("Deleted screenshot after sending the email.")

        except Exception as email_error:
            # If sending the email fails, log the email error
            print("Failed to send error notification email: ", email_error)


if __name__ == '__main__':
    if "--test" in sys.argv:
        runTestCheck()
    else:
        main()
