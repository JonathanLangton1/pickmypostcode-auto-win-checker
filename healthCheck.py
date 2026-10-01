"""`run.py --test`: run the whole pipeline once, report every health check and email a summary."""
from browserLogin import browserLogin
from draws import CHECK_TIMES_TEXT, UK, drawnText, fetchDraws, missingText, readDraws
from datetime import datetime, timezone
from sendEmail import sendEmail
import io
import os
import random
import sys
from contextlib import redirect_stdout


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
            <td style="padding:12px 14px;border-bottom:1px solid #eee;font-weight:600;">{result.draw.label}<br><span style="font-weight:400;color:#999;font-size:12px;">{drawnText(result.draw, result.day)}</span></td>
            <td style="padding:12px 14px;border-bottom:1px solid #eee;color:#555;">{winning_cell}</td>
            <td style="padding:12px 14px;border-bottom:1px solid #eee;text-align:center;">{result_html}</td>
        </tr>"""
    for draw, day in missing:
        rows += f"""
        <tr>
            <td style="padding:12px 14px;border-bottom:1px solid #eee;font-weight:600;">{draw.label}<br><span style="font-weight:400;color:#999;font-size:12px;">{drawnText(draw, day)}</span></td>
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
        return f"No wins to claim in the results available, but these are unavailable: {missingText(missing)}."
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
        lines.append(f"  {result.draw.label:<14} {drawnText(result.draw, result.day)}  {result.winningText()}{marker}")
    for draw, day in missing:
        lines.append(f"  {draw.label:<14} {drawnText(draw, day)}  unavailable")
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
            drawResults = fetchDraws()
            results, missing = readDraws(drawResults, your_postcode, _utcNow())  # the browser may have taken minutes
        if missing:
            console.print(f"  [red]✗[/red] Results API — [red]unavailable: {missingText(missing)}[/red]")
        else:
            console.print("  [green]✓[/green] Results API fetch")
        checks['api'] = not missing
    except Exception as e:
        console.print(f"  [red]✗[/red] Results API — [red]{e}[/red]")
        checks['api'] = False

    # 4) Email delivery (only meaningful if we have results to send)
    if results:
        now = _utcNow()  # whether a win can still be claimed is as of now
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
        now = _utcNow()
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
            drawn = drawnText(result.draw, result.day)
            if status == 'WIN':
                table.add_row(result.draw.label, drawn, f"[bold green]{winning_str}[/bold green]", "[bold green]🎉 WIN[/bold green]")
            else:
                table.add_row(result.draw.label, drawn, winning_str, f"[dim]{status or '–'}[/dim]")
        for draw, day in missing:
            table.add_row(draw.label, drawnText(draw, day), "[yellow]unavailable[/yellow]", "[yellow]?[/yellow]")
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
