"""What each email says, as plain content. emailTemplate.render turns it into HTML."""
from datetime import timedelta
from draws import CHECK_TIMES_TEXT, DRAWS, UK, drawnText, normalisePostcode
from emailTemplate import Code, Email, Grid, Note, Row, Rows, Stats

CLAIM_URL = 'https://pickmypostcode.com/'
FOOTER = f"Sent by your Pick My Postcode bot. It checks every draw at {CHECK_TIMES_TEXT}."


def formatPostcode(postcode):
    """'ZZ99ZZ' -> 'ZZ9 9ZZ': the inward code is always the last three characters."""
    compact = normalisePostcode(postcode)
    return f"{compact[:-3]} {compact[-3:]}" if len(compact) > 3 else compact


def _closes(result):
    return f"{result.draw.closesAt(result.day):%a %d %b, %H:%M}"


def _winningValue(result, postcode):
    """The winning postcode, or for the Stackpot's list, yours when you're on it, else the first and a count."""
    winning = result.winningPostcode
    if not isinstance(winning, tuple):
        return winning
    if not winning:
        return '-'
    if result.hasWon and postcode:
        return formatPostcode(postcode)
    return winning[0] if len(winning) == 1 else f"{winning[0]} +{len(winning) - 1}"


def _drawList(labels):
    return labels[0] if len(labels) == 1 else f"{', '.join(labels[:-1])} and {labels[-1]}"


def winEmail(wins, postcode, now):
    labels = [w.draw.label for w in wins]
    soonest = min(wins, key=lambda w: w.draw.closesAt(w.day))
    first_come = [w.draw.label for w in wins if w.draw.firstCome]
    blocks = [Rows('Your prize' if len(wins) == 1 else 'Your prizes', [
        Row(w.draw.label, f"Drawn {drawnText(w.draw, w.day)}", f"Claim by {w.draw.closesAt(w.day):%a %H:%M}", tone='win', mono=False)
        for w in wins])]
    if first_come:
        blocks.append(Note(f"The {_drawList(first_come)} {'is' if len(first_come) == 1 else 'are'} first come, first served: "
                           "the first person registered at your postcode to claim it wins, so claim it now.", 'warn'))
    return Email(
        tone='win',
        title=f"You won the {labels[0]}" if len(wins) == 1 else f"You won {len(wins)} draws",
        intro=(f"Your postcode came up in the {_drawList(labels)}. Claim before {_closes(soonest)} "
               "or the prize is gone."),
        preheader=f"Claim before {_closes(soonest)} at pickmypostcode.com",
        dateline=f"{now.astimezone(UK):%a %d %b}", postcode=formatPostcode(postcode),
        cta=('Claim your prize', CLAIM_URL), blocks=blocks, footer=FOOTER,
    )


def healthEmail(results, missing, postcode, now, status, verdict):
    """`status(result)` is 'WIN', 'won · claimed', 'won · closed' or ''; `verdict` explains a no-win."""
    won = [r.draw.label for r in results if status(r) == 'WIN']
    rows = []
    for result in results:
        state = status(result)
        tone = 'win' if state == 'WIN' else ('muted' if state else 'neutral')
        rows.append(Row(result.draw.label, drawnText(result.draw, result.day), _winningValue(result, postcode),
                        'Win' if state == 'WIN' else state.capitalize(), tone))
    rows += [Row(draw.label, drawnText(draw, day), 'Unavailable', '', 'warn', mono=False) for draw, day in missing]
    blocks = [Rows('Latest results', rows),
              Note("This came from a manual --test run. Normally you'll only hear from the bot when you win, "
                   "plus a weekly summary on Sunday evenings.")]
    if won:
        tone, title = 'win', f"You won the {_drawList(won)}"
        intro = "Your postcode is a winner in the latest results. Claim it before it closes."
    elif missing:
        tone, title, intro = 'warn', 'Some results are missing', verdict
    else:
        tone, title, intro = 'neutral', 'No win this time', verdict
    return Email(
        tone=tone, title=title, intro=intro,
        preheader=f"{len(results)} draws checked for {formatPostcode(postcode)}. {intro}",
        dateline=f"{now.astimezone(UK):%a %d %b}", postcode=formatPostcode(postcode),
        cta=('Claim your prize', CLAIM_URL) if won else None, blocks=blocks, footer=FOOTER,
    )


def weeklyEmail(history, sunday, verdict):
    days = [sunday - timedelta(days=offset) for offset in range(6, -1, -1)]
    readings = [(day, [(draw, history.result(day, draw)) for draw in DRAWS]) for day in days]
    wins = sum(1 for _, row in readings for _, r in row if r and r.hasWon)
    checked = sum(1 for _, row in readings for _, r in row if r)
    total = len(days) * len(DRAWS)

    tone = lambda r: 'none' if r is None else 'win' if r.hasWon else 'ok'
    grid = [(draw.label, [tone(dict(row)[draw]) for _, row in readings]) for draw in DRAWS]
    won = [Row(r.draw.label, f"{day:%A %d %b}, {r.draw.at:%H:%M}", _winningValue(r, history.postcode),
               'Claimed' if r.claimed else 'Won', 'win')
           for day, row in readings for _, r in row if r and r.hasWon]

    if wins:
        tone, title = 'win', 'You won this week' if wins == 1 else f"You won {wins} times this week"
    elif checked < total:
        tone, title = 'warn', 'No wins recorded'
    else:
        tone, title = 'neutral', 'No wins this week'
    return Email(
        tone=tone, title=title, intro=verdict,
        preheader=f"{wins} {'win' if wins == 1 else 'wins'} from {checked} of {total} draws checked.",
        dateline=f"{days[0]:%d %b} to {sunday:%d %b}", postcode=formatPostcode(history.postcode),
        blocks=[Stats([(str(wins), 'Win' if wins == 1 else 'Wins'), (f"{checked}/{total}", 'Checked'), (str(total - checked), 'Missed')]),
                *([Rows('Your wins', won)] if won else []),
                Grid([(f"{day:%a}", f"{day.day}") for day in days], grid)],
        footer=FOOTER,
    )


def errorEmail(errors, now):
    blocks = []
    for error in errors:
        heading, _, detail = error.partition('\n')
        blocks.append(Code(heading.rstrip(':.'), detail.strip()))
    blocks.append(Note("You'll get at most one error email a day. The full output is in the container logs."))
    return Email(
        tone='error',
        title='The check hit a problem' if len(errors) == 1 else f"The check hit {len(errors)} problems",
        intro="The bot is still scheduled and will try again at the next check. Here's what went wrong.",
        preheader=errors[0].partition('\n')[0].rstrip(':.'),
        dateline=f"{now.astimezone(UK):%a %d %b, %H:%M}", blocks=blocks, footer=FOOTER,
    )
