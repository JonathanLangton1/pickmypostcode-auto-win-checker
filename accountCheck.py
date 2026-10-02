"""Credit the daily Main, Video and Survey pennies through the site's own API.

The public results feed does not record this activity. A logged-in GET of three stable
WordPress pages does: main/27079, video/23645 and survey/21851. Those numbers are page
ids, not draw ids. The old browser also opened Stackpot (21674) and Bonus (1266); those
views do not grant the daily penny and are not called.

A run before noon belongs to the period that opened at yesterday's noon. The caller stores
that date, so the receipt does not count as today's afternoon credit.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import os
from time import monotonic

import requests

from draws import UK, normalisePostcode

API_BASE = 'https://pickmypostcode.com/api/index.php/'
# Fixed page ids. There is no discovery step: a wrong id fails the check.
PAGES = (('main', 27079), ('video', 23645), ('survey', 21851))
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 15
ATTEMPTS = 2
# Do not start another account request after this. A request already started still runs
# until its own connect/read timeout; the read timeout is inactivity, not a wall-clock cancel.
OVERALL_SECONDS = 60
SKEW = timedelta(minutes=2)
_STAMP = '%Y-%m-%d %H:%M:%S'


class AccountCheckError(Exception):
    """Safe to log and email: no credentials, cookies, tokens or response bodies."""


@dataclass(frozen=True)
class AccountCheckResult:
    total_bonus: int       # pence currently on the account
    new_credits: int        # pennies added by this run; 0 when today was already credited
    verified_day: date      # the noon that opened the credited period


@dataclass(frozen=True)
class _Account:
    bonus: int
    counters: dict
    stamps: dict
    penny_added: bool | None


def creditDay(moment):
    """The date of the noon that opened the current credit period."""
    return _periodStart(moment).date()


def dailyAccountCheck(now=None):
    """Sign in, visit Main, Video and Survey, and confirm the current period was saved.

    Already credited is success. A partial or unverified visit raises, and the caller
    must not store the daily receipt. The session is closed on every path.
    """
    moment = (now or _utcNow)()
    email, postcode = _credentials()
    started = monotonic()
    session = requests.Session()
    try:
        session.max_redirects = 0
        token = _token(session, started)
        _login(session, email, postcode, token, started)
        # Login can carry a cached older timestamp. The neutral read is the baseline.
        current = _read(session, email, postcode, started, 'user/current/', 'neutral')
        new_credits = 0
        for slug, page_id in PAGES:
            expect_new = not _inPeriod(current.stamps.get(slug), moment)
            seen = _read(session, email, postcode, started, f'user/current/{slug}/{page_id}', 'draw', slug)
            _checkVisit(current, seen, slug, moment, expect_new)
            current = seen
            new_credits += expect_new
        confirmed = _read(session, email, postcode, started, 'user/current/', 'neutral')
        if not _same(confirmed, current):
            raise AccountCheckError('draw activity was not saved')
        for slug, _page_id in PAGES:
            if not _inPeriod(confirmed.stamps.get(slug), moment):
                raise AccountCheckError('draw timestamp is missing or stale')
        return AccountCheckResult(confirmed.bonus, new_credits, creditDay(moment))
    finally:
        session.close()


def _utcNow():
    return datetime.now(UK)


def _credentials():
    email = (os.environ.get('PMP_EMAIL') or '').strip()
    postcode = (os.environ.get('YOUR_POSTCODE') or '').strip()
    if not email or not normalisePostcode(postcode):
        raise AccountCheckError('account credentials are not set')
    return email, postcode


def _periodStart(moment):
    local = moment.astimezone(UK)
    start = datetime.combine(local.date(), time(12), tzinfo=UK)
    if local < start:
        start -= timedelta(days=1)
    return start


def _inPeriod(stamp, moment):
    if stamp is None:
        return False
    start = _periodStart(moment)
    return start <= stamp <= moment.astimezone(UK) + SKEW


def _token(session, started):
    data = _request(session, 'POST', 'token/put/user', started, require_success=False)
    token = data.get('token')
    if token in (None, ''):
        return None  # the site returns this until a session exists; login still works
    if not isinstance(token, str):
        raise AccountCheckError('account API response was not usable')
    return token


def _login(session, email, postcode, token, started):
    payload = {'email': email, 'postcode': postcode}
    if token:
        payload['token'] = token
    data = _request(session, 'POST', 'login/', started, payload, failure='sign-in failed')
    _account(data, email, postcode, 'login')


def _read(session, email, postcode, started, path, mode, slug=None):
    return _account(_request(session, 'GET', path, started), email, postcode, mode, slug)


def _request(session, method, path, started, payload=None, require_success=True,
             failure='account API response was not usable'):
    """One call, retried once on a timeout or a gateway error. Redirects are not followed:
    the login body must not be sent to another host. The 60s budget is checked before a
    call is started, not while it is in flight."""
    last_error = None
    for _attempt in range(ATTEMPTS):
        if monotonic() - started > OVERALL_SECONDS:
            raise AccountCheckError('account request budget is used')
        try:
            response = session.request(method, API_BASE + path, json=payload, allow_redirects=False,
                                       timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        except requests.Timeout:
            last_error = AccountCheckError('account API timed out')
            continue
        except requests.RequestException:
            last_error = AccountCheckError('account API request failed')
            continue
        if response.is_redirect or 300 <= response.status_code < 400:
            raise AccountCheckError('account API redirect refused')
        if response.status_code in (502, 503, 504):
            last_error = AccountCheckError(f'account API returned HTTP {response.status_code}')
            continue
        if response.status_code != 200:
            raise AccountCheckError(f'account API returned HTTP {response.status_code}')
        return _data(response, require_success, failure)
    raise last_error


def _data(response, require_success, failure):
    try:
        body = response.json()
    except ValueError:
        raise AccountCheckError('account API response was not usable') from None
    if not isinstance(body, dict) or not isinstance(body.get('data'), dict):
        raise AccountCheckError('account API response was not usable')
    if require_success and body.get('status') != 'success':
        raise AccountCheckError(failure)
    return body['data']


def _account(data, email, postcode, mode, slug=None):
    if mode == 'login':
        if data.get('error') != '':
            raise AccountCheckError('sign-in failed')
    elif data.get('error') not in (None, ''):
        raise AccountCheckError('account API response was not usable')
    wrapper = data.get('user')
    raw = wrapper.get('data') if isinstance(wrapper, dict) else None
    cached = wrapper.get('cached') if isinstance(wrapper, dict) else None
    if not isinstance(raw, dict) or type(cached) is not bool:
        raise AccountCheckError('account API response was not usable')
    if raw.get('loggedIn') is not True:
        raise AccountCheckError('sign-in failed')
    found_email, found_postcode = raw.get('email'), raw.get('postcode')
    same_email = isinstance(found_email, str) and found_email.casefold() == email.casefold()
    same_postcode = isinstance(found_postcode, str) and normalisePostcode(found_postcode) == normalisePostcode(postcode)
    if not same_email or not same_postcode:
        raise AccountCheckError('signed-in account does not match')
    if raw.get('status') != 'active':
        raise AccountCheckError('account is not active')
    holiday = raw.get('holiday')
    if type(holiday) is not int:
        raise AccountCheckError('account API response was not usable')
    if holiday != 0:
        raise AccountCheckError('account is on holiday')
    # Absent on some older accounts. Present and non-empty means the account is not activated.
    if 'activationkey' in raw and raw.get('activationkey') != '':
        raise AccountCheckError('account is not activated')
    bonus = raw.get('totalBonus')
    if type(bonus) is not int:
        raise AccountCheckError('account API response was not usable')
    counters, stamps = {}, {}
    for name, _page_id in PAGES:
        count = raw.get(f'{name}draw')
        if type(count) is not int:
            raise AccountCheckError('account API response was not usable')
        counters[name] = count
        stamps[name] = _stamp(raw.get(f'{name}updated'))
    return _Account(bonus, counters, stamps, _penny(data, mode, slug))


def _stamp(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, _STAMP).replace(tzinfo=UK)
    except ValueError:
        return None


def _penny(data, mode, slug):
    penny = data.get('penny')
    if mode == 'login' and penny == []:
        return None
    page = penny.get('page') if isinstance(penny, dict) else None
    valid = (isinstance(penny, dict) and set(penny) == {'added', 'page'} and type(penny.get('added')) is bool
             and (page is None or isinstance(page, str)))
    if not valid:
        raise AccountCheckError('account API response was not usable')
    if mode == 'neutral' and (penny['added'] is not False or page is not None):
        raise AccountCheckError('account API response was not usable')
    if mode == 'draw' and page != slug:
        raise AccountCheckError('draw activity was not verified')
    return penny['added']


def _checkVisit(previous, seen, slug, moment, expect_new):
    """Accept a penny that is in the current period.

    The same GET is retried after a timeout. The server may have saved it on the first
    attempt, so the retry can report penny.added false while the counter, balance and
    timestamp already show the credit. That still counts. A missing or stale timestamp,
    or a counter that does not match the balance, does not.
    """
    if not _inPeriod(seen.stamps.get(slug), moment):
        raise AccountCheckError('draw timestamp is missing or stale')
    others = [name for name, _page_id in PAGES if name != slug]
    others_same = all(seen.counters[name] == previous.counters[name] and seen.stamps[name] == previous.stamps[name]
                      for name in others)
    gained = (seen.counters[slug] == previous.counters[slug] + 1 and seen.bonus == previous.bonus + 1
              and seen.stamps[slug] != previous.stamps.get(slug))
    unchanged = (seen.penny_added is False and seen.bonus == previous.bonus
                 and seen.counters == previous.counters and seen.stamps == previous.stamps)
    if others_same and ((expect_new and gained) or (not expect_new and unchanged)):
        return
    raise AccountCheckError('draw activity was not verified')


def _same(left, right):
    return left.bonus == right.bonus and left.counters == right.counters and left.stamps == right.stamps
