"""Pick My Postcode draws: when each is drawn and claimable (UK time), and how to read the public results API."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from time import sleep
from zoneinfo import ZoneInfo
import requests

UK = ZoneInfo('Europe/London')
API_URL = 'https://pickmypostcode.com/api/index.php/entry/'
NOON = time(12)

# UK times the bot checks: a minute after each first-come draw (Stackpot 9am, Mini Draw 6pm,
# Stackpot 9pm), plus the original 2pm run that also signs in for the daily bonus.
CHECK_TIMES = (time(9, 1), time(14, 0), time(18, 1), time(21, 1))
CHECK_TIMES_TEXT = f"{', '.join(t.strftime('%H:%M') for t in CHECK_TIMES[:-1])} and {CHECK_TIMES[-1]:%H:%M} UK time"


@dataclass(frozen=True)
class Draw:
    """One scheduled daily draw. The Stackpot is drawn twice a day, so it appears twice."""
    key: str                 # history key
    label: str
    path: tuple[str, ...]    # location in the API's drawResults
    at: time                 # UK draw time
    closes: time             # claims close at the next occurrence of this UK time
    firstCome: bool = False  # only the first registered user at the postcode to claim wins

    def drawnAt(self, day):
        return datetime.combine(day, self.at, tzinfo=UK)

    def closesAt(self, day):
        closingDay = day if self.closes > self.at else day + timedelta(days=1)
        return datetime.combine(closingDay, self.closes, tzinfo=UK)

    def latestDay(self, now):
        """The day of this draw's most recent occurrence at or before `now`."""
        today = now.astimezone(UK).date()
        return today if self.drawnAt(today) <= now else today - timedelta(days=1)


DRAWS = (
    Draw('mainDraw', 'Main Draw', ('main',), NOON, NOON),
    Draw('surveyDraw', 'Survey Draw', ('survey',), NOON, NOON),
    Draw('videoDraw', 'Video Draw', ('video',), NOON, NOON),
    Draw('stackpotDraw', 'Stackpot 9am', ('stackpot',), time(9), time(21), firstCome=True),
    Draw('stackpotEveningDraw', 'Stackpot 9pm', ('stackpot',), time(21), time(9), firstCome=True),
    Draw('bonusDrawFive', 'Bonus £5', ('bonus', 'five'), NOON, NOON),
    Draw('bonusDrawTen', 'Bonus £10', ('bonus', 'ten'), NOON, NOON),
    Draw('bonusDrawTwenty', 'Bonus £20', ('bonus', 'twenty'), NOON, NOON),
    Draw('miniDraw', 'Mini Draw', ('mini',), time(18), time(2), firstCome=True),
)


@dataclass(frozen=True)
class DrawResult:
    draw: Draw
    day: date                # UK date the draw was made
    winningPostcode: str | tuple[str, ...]  # a tuple of postcodes for the Stackpot
    hasWon: bool
    claimed: bool = False    # a first-come prize at your postcode has already been taken

    def canClaim(self, now):
        return (self.hasWon and not self.claimed
                and self.draw.drawnAt(self.day) <= now < self.draw.closesAt(self.day))

    def winningText(self):
        if isinstance(self.winningPostcode, tuple):
            return ', '.join(self.winningPostcode) or '—'
        return self.winningPostcode


def drawnText(draw, day):
    return draw.drawnAt(day).strftime('%a %d %b %H:%M')


def missingText(missing):
    return ', '.join(f"{draw.label} ({drawnText(draw, day)})" for draw, day in missing)


def fetchDraws(attempts=3, sleep=sleep):
    """Return the API's drawResults, retrying briefly on network or format errors."""
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(API_URL, timeout=30)
            response.raise_for_status()
            drawResults = response.json()['data']['drawResults']
            if not isinstance(drawResults, dict):
                raise ValueError('drawResults is not an object')
            return drawResults
        except (requests.RequestException, ValueError, KeyError, TypeError) as error:
            if attempt == attempts:
                raise
            print(f'Results API failed ({error}); retrying...')
            sleep(10 * attempt)


def latestDraw(path, now):
    """The (draw, day) the API should be showing at `path` by `now`: that slot's most recent draw."""
    return max(((d, d.latestDay(now)) for d in DRAWS if d.path == path), key=lambda o: o[0].drawnAt(o[1]))


def readDraws(drawResults, postcode, now):
    """Read each API draw for `postcode` at `now`.
    Returns (results, missing): every readable past result, including older ones still shown, and the
    (draw, day) of each latest draw the API isn't showing (unreadable, not yet published, or future-dated)."""
    target = normalisePostcode(postcode)
    if not target:
        raise ValueError('YOUR_POSTCODE is not set')
    results, missing = [], []
    for path in dict.fromkeys(d.path for d in DRAWS):
        expected = latestDraw(path, now)
        try:
            node = drawResults
            for part in path:
                node = node[part]
            result = _readDraw(node, [d for d in DRAWS if d.path == path], target)
        except (KeyError, TypeError, ValueError, AttributeError):
            missing.append(expected)
            continue
        if result.draw.drawnAt(result.day) <= now:
            results.append(result)
        if (result.draw, result.day) != expected:
            missing.append(expected)
    return results, missing


def _readDraw(node, sessions, target):
    drawnAt = datetime.strptime(node['dateandtime'], '%Y-%m-%d %H:%M:%S')
    draw = next((d for d in sessions if (d.at.hour, d.at.minute) == (drawnAt.hour, drawnAt.minute)), None)
    if draw is None:
        raise ValueError(f'unexpected draw time {drawnAt}')
    winning = node['result']
    if isinstance(winning, list):
        if not isinstance(node['claimed'], list):
            raise ValueError('claimed is not a list')
        winning = tuple(_postcode(p) for p in winning)
        listed = {normalisePostcode(p) for p in winning}
        claimed = {normalisePostcode(_postcode(p)) for p in node['claimed']}
        isClaimed = target in claimed and target not in listed
        return DrawResult(draw, drawnAt.date(), winning, target in listed or isClaimed, isClaimed)
    winning = _postcode(winning)
    isClaimed = False
    if draw.firstCome:
        status, claims, maxClaims = node['status'], node['claims'], node['max_claims']
        if not (isinstance(status, str) and isinstance(claims, int) and isinstance(maxClaims, int)):
            raise ValueError('missing claim status')
        isClaimed = status != 'active' or claims >= maxClaims
    hasWon = normalisePostcode(winning) == target
    return DrawResult(draw, drawnAt.date(), winning, hasWon, hasWon and isClaimed)


def _postcode(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'invalid postcode {value!r}')
    return value.strip()


def normalisePostcode(postcode):
    return ''.join((postcode or '').split()).upper()
