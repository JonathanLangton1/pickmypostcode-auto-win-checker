"""logs/pastData.json: for one postcode, every draw result seen, which wins were emailed, and other
once-a-day receipts. Changing YOUR_POSTCODE sets the old file aside and starts a new history."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import fcntl
import json
import os
import shutil
import tempfile
from draws import DRAWS, DrawResult, normalisePostcode

VERSION = 2
RETENTION_DAYS = 10
DRAWS_BY_KEY = {d.key: d for d in DRAWS}


@contextmanager
def openHistory(path, postcode):
    """Hold the history for one whole check, so a manual run and the scheduler never interleave."""
    postcode = normalisePostcode(postcode)
    if not postcode:
        raise ValueError('YOUR_POSTCODE is not set')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(f'{path}.lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another check is running; waiting for it to finish...')
            fcntl.flock(lock, fcntl.LOCK_EX)
        history = History(path, _load(path, postcode), postcode)
        yield history
        history.save()


class History:
    def __init__(self, path, data, postcode):
        self.path = path
        self.postcode = postcode  # normalised; every result and receipt here is for this postcode
        self.draws = data.get('draws', {})  # {'YYYY-MM-DD' draw day: {draw key: entry}}
        self.lastBrowserLogin = _date(data.get('lastBrowserLogin'))
        self.lastWeeklySummary = _date(data.get('lastWeeklySummary'))  # the Sunday it covered
        self.lastErrorEmail = _date(data.get('lastErrorEmail'))

    def result(self, day, draw):
        entry = self.draws.get(day.isoformat(), {}).get(draw.key)
        return _toResult(day, draw, entry) if entry else None

    def record(self, result):
        """Store the latest reading of a draw, keeping whether its win was already emailed."""
        entries = self.draws.setdefault(result.day.isoformat(), {})
        existing = entries.get(result.draw.key)
        winning = result.winningPostcode
        entries[result.draw.key] = {
            'winningPostcode': list(winning) if isinstance(winning, tuple) else winning,
            'hasWon': result.hasWon,
            'claimed': result.claimed,
            'notified': existing['notified'] if existing else None,
        }

    def pendingWins(self, now):
        """Wins not yet emailed that can still be claimed."""
        pending = []
        for day, entries in sorted(self.draws.items()):
            for draw in DRAWS:
                entry = entries.get(draw.key)
                if entry and not entry['notified']:
                    result = _toResult(date.fromisoformat(day), draw, entry)
                    if result.canClaim(now):
                        pending.append(result)
        return pending

    def markNotified(self, results, at):
        for result in results:
            self.draws[result.day.isoformat()][result.draw.key]['notified'] = at.isoformat()

    def prune(self, today):
        for day in [d for d in self.draws if (today - date.fromisoformat(d)).days >= RETENTION_DAYS]:
            del self.draws[day]

    def save(self):
        data = {
            'version': VERSION,
            'postcode': self.postcode,
            'lastBrowserLogin': _iso(self.lastBrowserLogin),
            'lastWeeklySummary': _iso(self.lastWeeklySummary),
            'lastErrorEmail': _iso(self.lastErrorEmail),
            'draws': dict(sorted(self.draws.items())),
        }
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path), prefix='.pastData-', suffix='.tmp')
        try:
            os.fchmod(fd, 0o644)
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise


def _load(path, postcode):
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print(f'History was unreadable; moved it to {_setAside(path, "corrupt")} and started afresh.')
        return {}
    if data.get('version') == VERSION:
        if data.get('postcode') == postcode:
            return data
        aside = _setAside(path, f'postcode-{data.get("postcode")}')
        print(f'YOUR_POSTCODE changed; moved the previous postcode\'s history to {aside} and started afresh.')
        return {}
    if 'version' in data:
        raise ValueError(f'{path} has unsupported version {data["version"]}')
    print(f'Upgrading history; the original is kept at {_setAside(path, "v1-backup", move=False)}.')
    return _fromVersion1(data)


def _setAside(path, label, move=True):
    aside = f'{path}.{label}-{datetime.now():%Y%m%d%H%M%S}'
    if move:
        os.replace(path, aside)
    else:
        shutil.copy2(path, aside)
    return aside


def _fromVersion1(legacy):
    """Version 1 had no postcode, so it's assumed to be YOUR_POSTCODE's. It kept one snapshot per check
    date, normally from the 2pm run, which still showed the previous evening's Mini Draw. It never recorded
    whether its win email was delivered, so its wins count as not notified: a still-open one is emailed
    (perhaps again) rather than risk losing it."""
    draws = {}
    for checked, snapshot in legacy.items():
        try:
            checkedDay = date.fromisoformat(checked)
            for key, old in snapshot['drawResults'].items():
                if key not in DRAWS_BY_KEY:
                    continue
                day = checkedDay - timedelta(days=1) if key == 'miniDraw' else checkedDay
                draws.setdefault(day.isoformat(), {})[key] = {
                    'winningPostcode': old['winningPostcode'],
                    'hasWon': bool(old['hasWon']),
                    'claimed': False,
                    'notified': None,
                }
        except (ValueError, KeyError, TypeError, AttributeError):
            if checked != 'lastBrowserLogin':
                print(f'Skipping unreadable history entry {checked!r}')
    return {'lastBrowserLogin': legacy.get('lastBrowserLogin'), 'draws': draws}


def _toResult(day, draw, entry):
    winning = entry['winningPostcode']
    return DrawResult(draw, day, tuple(winning) if isinstance(winning, list) else winning,
                      entry['hasWon'], entry.get('claimed', False))


def _date(value):
    return date.fromisoformat(value) if value else None


def _iso(value):
    return value.isoformat() if value else None
