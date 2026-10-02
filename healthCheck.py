"""`run.py --test`: run the whole pipeline once, report every health check and email a summary."""
from accountCheck import dailyAccountCheck
from draws import CHECK_TIMES_TEXT, UK, drawnText, fetchDraws, missingText, readDraws
from datetime import datetime, timezone
from emails import healthEmail
from emailTemplate import render
from sendEmail import sendEmail
import os
import random
import sys


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


def _buildSummaryHtml(results, missing, postcode, now, account_ok=True):
    return render(healthEmail(results, missing, postcode, now, lambda r: _status(r, now), _noWinText(missing, account_ok)))


def _noWinText(missing, account_ok=True):
    if missing:
        return f"No wins to claim in the results available, but these are unavailable: {missingText(missing)}."
    if not account_ok:
        return "No wins to claim in these results. The account check did not pass."
    return "No wins to claim right now."


def _buildSummaryText(results, missing, postcode, now, account_ok=True):
    lines = [
        "Pick My Postcode daily check",
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
        lines.append(_noWinText(missing, account_ok))
    return "\n".join(lines)


def runTestCheck():
    """Run the full pipeline once, surface every health check, and email a summary."""
    from rich import box
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    console = Console(force_terminal=True)
    your_postcode = os.environ.get("YOUR_POSTCODE", "")
    notification_email = os.environ.get("NOTIFICATION_EMAIL_ADDRESS", "")
    now = _utcNow()

    console.print()
    console.print(Panel(
        f"[bold]Pick My Postcode health check[/bold]\n"
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

    # 1) Account API: sign in and confirm today's Main, Video and Survey pennies.
    try:
        with console.status("  Checking account activity...", spinner="dots"):
            account = dailyAccountCheck(now=_utcNow)
        console.print(f"  [green]✓[/green] Account activity verified for {account.verified_day} "
                      f"({account.new_credits} new, bonus {account.total_bonus}p)")
        checks['account'] = True
    except Exception as e:
        console.print(f"  [red]✗[/red] Account activity: [red]{e}[/red]")
        checks['account'] = False

    # 2) Results API fetch. Read it after the account check: a slow check can cross a draw boundary.
    try:
        with console.status("  Fetching draw results...", spinner="dots"):
            drawResults = fetchDraws()
            results, missing = readDraws(drawResults, your_postcode, _utcNow())
        if missing:
            console.print(f"  [red]✗[/red] Results API: [red]unavailable: {missingText(missing)}[/red]")
        else:
            console.print("  [green]✓[/green] Results API fetch")
        checks['api'] = not missing
    except Exception as e:
        console.print(f"  [red]✗[/red] Results API: [red]{e}[/red]")
        checks['api'] = False

    # 3) Email. SMTP acceptance is not proof the mailbox stored it.
    if results:
        now = _utcNow()  # whether a win can still be claimed is as of now
        account_ok = checks.get('account') is True
        summary_html = _buildSummaryHtml(results, missing, your_postcode, now, account_ok)
        text = _buildSummaryText(results, missing, your_postcode, now, account_ok)
        with console.status(f"  Sending summary email to {notification_email}...", spinner="dots"):
            email_ok = sendEmail(
                notification_email,
                f"Pick My Postcode: {now.astimezone(UK).strftime('%a %d %b')} results",
                text,
                summary_html,
            )
        if email_ok:
            # SMTP accepted the message. That is not proof the recipient's mailbox stored it.
            console.print(f"  [green]✓[/green] Mail server accepted the summary email for [bold]{notification_email}[/bold]")
            checks['email'] = True
        else:
            console.print("  [red]✗[/red] Email: check EMAIL_ADDRESS / EMAIL_PASSWORD in .env")
            checks['email'] = False
    else:
        console.print("  [yellow]-[/yellow] Email skipped (no results to send)")
        checks['email'] = None

    # Overall verdict
    console.print()
    all_passed = all(v is True for v in checks.values())
    if all_passed:
        console.print("[bold green]✅ All systems operational, full pipeline working[/bold green]")
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
                table.add_row(result.draw.label, drawn, winning_str, f"[dim]{status or '-'}[/dim]")
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
        elif checks.get('account') is not True:
            console.print(Panel(
                "[yellow]No win in these results. The account check did not pass.[/yellow]",
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
            f"[bold]Sit back and relax.[/bold] The bot checks every draw daily at\n"
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
