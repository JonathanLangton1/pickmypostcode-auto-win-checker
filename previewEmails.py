"""Write every email with made-up results to email-previews/ for a browser to open.
Nothing is fetched or sent: `python previewEmails.py`."""
from datetime import date, datetime, timedelta
from draws import DRAWS, UK, DrawResult
from emails import errorEmail, healthEmail, weeklyEmail, winEmail
from emailTemplate import render
from history import History
import os

POSTCODE = 'ZZ99ZZ'
SUNDAY = date(2026, 10, 4)
NOW = datetime(2026, 10, 1, 18, 1, tzinfo=UK)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'email-previews')
DRAW = {d.key: d for d in DRAWS}


def _postcode(i):
    return f"{'ABCDEFGHKLMNPRS'[i % 15]}{'LNSWEM'[i % 6]}{1 + i % 9} {i % 10}{'ABDEFGHJ'[i % 8]}{'LNPQRSTU'[i % 8]}"


def _results(day, wins=()):
    out = []
    for i, draw in enumerate(DRAWS):
        won = draw.key in wins
        if draw.key.startswith('stackpot'):
            winning = tuple(_postcode(i * 7 + n) for n in range(6)) + (('ZZ9 9ZZ',) if won else ())
        else:
            winning = 'ZZ9 9ZZ' if won else _postcode(i + day.day)
        out.append(DrawResult(draw, day, winning, won))
    return out


def samples():
    wins = [DrawResult(DRAW['miniDraw'], NOW.date(), 'ZZ9 9ZZ', True), DrawResult(DRAW['mainDraw'], NOW.date(), 'ZZ9 9ZZ', True)]
    yield 'win', winEmail(wins, POSTCODE, NOW)

    latest = _results(NOW.date())
    yield 'daily-check', healthEmail(latest, [], POSTCODE, NOW, lambda r: '', "No wins to claim right now.")

    history = History('unused', {}, POSTCODE)
    for offset in range(7):
        day = SUNDAY - timedelta(days=offset)
        for result in _results(day, wins=('bonusDrawTen',) if offset == 3 else ()):
            if not (offset == 1 and result.draw.key in ('miniDraw', 'stackpotEveningDraw')):
                history.record(result)
    yield 'weekly', weeklyEmail(history, SUNDAY, "Congratulations, you had a win this week. 2 of 63 draws weren't "
                                                 "checked, so this week's results are incomplete.")

    yield 'error', errorEmail([
        "The account check failed:\nTraceback (most recent call last):\n  File \"/app/run.py\", line 66, in _check\n"
        "    result = dailyAccountCheck(now=lambda: checked_at)\naccountCheck.AccountCheckError: sign-in failed (HTTP 401)",
    ], NOW)


def main():
    written = []
    os.makedirs(OUT, exist_ok=True)
    for name, email in samples():
        path = os.path.join(OUT, f"{name}.html")
        with open(path, 'w') as file:
            file.write(render(email))
        written.append(path)
    print('\n'.join(written))


if __name__ == '__main__':
    main()
