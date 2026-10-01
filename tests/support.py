"""Shared fakes: a controllable clock and synthetic API payloads (no real postcodes or user IDs)."""
from datetime import datetime, timedelta, timezone
from draws import UK, latestDraw

POSTCODE = 'ZZ9 9ZZ'


def uk(*args):
    return datetime(*args, tzinfo=UK)


class FakeClock:
    def __init__(self, start):
        self.current = start.astimezone(timezone.utc)  # UTC, so sleeping across a clock change is real elapsed time
        self.slept = 0

    def now(self):
        return self.current

    def sleep(self, seconds):
        self.slept += seconds
        self.current += timedelta(seconds=seconds)


def _single(result, at, claims=0, status='active'):
    return {'draw_id': 1, 'type': 'default', 'status': status, 'result': result, 'claims': claims,
            'max_claims': 1, 'dateandtime': at, 'updated': at}


def drawResults(midday='2026-10-01 12:00:00', main='MA1 1AA',
                stackpot=('SA1 1AA', 'SB1 1BB'), stackpotAt='2026-10-01 09:00:00', stackpotClaimed=(),
                mini='MI1 1AA', miniAt='2026-09-30 18:00:00', miniClaims=0, miniStatus='active'):
    return {
        'main': _single(main, midday),
        'survey': _single('SU1 1AA', midday),
        'video': _single('VI1 1AA', midday),
        'stackpot': {'draw_id': 2, 'result': list(stackpot), 'winningresult': stackpot[0] if stackpot else '',
                     'dateandtime': stackpotAt, 'claims': 0, 'pot': 10, 'claimed': list(stackpotClaimed)},
        'bonus': {
            'five': _single('BF1 1AA', midday),
            'ten': _single('BT1 1AA', midday),
            'twenty': _single('BW1 1AA', midday),
        },
        'mini': _single(mini, miniAt, miniClaims, miniStatus),
        'flash': {'winners': 0},
    }


def latestResults(now, **overrides):
    """A payload showing each draw the API should be showing at `now`."""
    def stamp(path):
        draw, day = latestDraw(path, now)
        return draw.drawnAt(day).strftime('%Y-%m-%d %H:%M:%S')
    times = {'midday': stamp(('main',)), 'stackpotAt': stamp(('stackpot',)), 'miniAt': stamp(('mini',))}
    return drawResults(**{**times, **overrides})
