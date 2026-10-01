# Pick My Postcode Auto Win Checker

[![Build](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/actions/workflows/dockerpush.yml/badge.svg?branch=main)](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/actions/workflows/dockerpush.yml)
[![Last commit](https://img.shields.io/github/last-commit/JonathanLangton1/pickmypostcode-auto-win-checker?label=updated)](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/commits/main)
[![Docker image](https://img.shields.io/docker/v/jonathanlangton1/pickmypostcode-auto-win-checker/latest?label=docker%20image&logo=docker)](https://hub.docker.com/r/jonathanlangton1/pickmypostcode-auto-win-checker)

Automatically signs into [pickmypostcode.com](https://pickmypostcode.com/) every day at 2pm and emails you when your postcode wins any draw — including the 6pm £100 Mini Draw and both daily Stackpot draws.

Works on any Docker host - Linux server (x86 or ARM), Raspberry Pi, or Mac (Intel or Apple Silicon).

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- A Gmail account with an [app password](https://knowledge.workspace.google.com/kb/how-to-create-app-passwords-000009237) (used to send notification emails)

## Quick start

Drop two files in an empty folder on your server, fill in your `.env`, and go:

```bash
mkdir pickmypostcode && cd pickmypostcode

curl -O https://raw.githubusercontent.com/JonathanLangton1/pickmypostcode-auto-win-checker/main/docker-compose.yml
curl -o .env https://raw.githubusercontent.com/JonathanLangton1/pickmypostcode-auto-win-checker/main/env.example

# edit .env with your details
nano .env

docker compose up -d
```

**Confirm it works** — run the full health check:

```bash
docker exec -t pickmypostcode-checker python run.py --test
```

This runs the entire pipeline and prints a coloured health-check report:

- ✓ Selenium grid reachable
- ✓ Browser flow (sign-in + draw page visits)
- ✓ Results API fetch
- ✓ Summary email delivered

…then shows today's winning postcodes in a table and tells you whether your postcode won. A nicely formatted summary email also lands in your inbox. If anything is misconfigured, the failing check is highlighted in red and the command exits non-zero.

That's it. From now on, the bot only emails you when you win (plus a summary every Sunday evening).

## When it checks

Draw times are UK time, and so is the schedule, whatever timezone your server is in.

| UK time | Checks |
| ------- | ------ |
| 09:01 | 9am Stackpot |
| 14:00 | Main, Survey, Video and Bonus draws (drawn at noon), plus the daily sign-in for your bonus |
| 18:01 | £100 Mini Draw (claimable 6pm–2am) |
| 21:01 | 9pm Stackpot; on Sundays, the weekly summary follows |

Every check reads every draw, and the bot also checks once when it starts, so draws that are still open are caught up after a missed check or a restart. Results whose claim window has already closed can't be recovered. If a draw isn't published yet, it re-checks every minute for up to 15 minutes. If a winning email fails, or a still-open draw can't be fetched, it tries again every 5 minutes, and never sends a win after it can no longer be claimed.

You get one email per winning draw. Re-checks and restarts don't send repeats, but the 9am and 9pm Stackpots are separate draws, so a postcode listed in both gets an email for each. Delivery isn't guaranteed exactly once: if the bot is stopped just after an email is sent, it may send that email again. The Mini Draw and Stackpot go to the first registered person at the postcode to claim, so be quick. If something breaks, you get at most one error email a day.

History is kept in `pickmypostcode_logs/pastData.json` for one postcode. If you change `YOUR_POSTCODE`, the old file is renamed (for example `pastData.json.postcode-AB12CD-…`) and a new history starts. When upgrading from an older version, its history is converted automatically and the original is kept as `pastData.json.v1-backup-…`. The old 2pm run saw the previous evening's Mini Draw, so those Mini results are moved back a day. The old version didn't record whether its win emails were delivered, so a win that can still be claimed is emailed once after upgrading, even if you already had that email.

## Useful commands

```bash
# Pull the latest published image and restart
docker compose pull && docker compose up -d

# Run a real check right now, including the sign-in (emails any new wins)
docker exec pickmypostcode-checker python run.py

# Tail logs
docker logs -f pickmypostcode-checker

# Stop everything
docker compose down
```

## Dev mode (watch it run in a live browser)

For when the site's HTML changes and locators break. Clone the repo, then:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm --build pickmypostcode-checker
```

Open [http://localhost:7900](http://localhost:7900) (password: `secret`) to watch Chromium drive itself. Python sources are bind-mounted, so edits take effect on the next run without rebuilding.

Run the offline tests (no browser, network or email needed) with `pip install -r requirements.txt` and then `python -m unittest`.

Every push to `main` runs the tests, then triggers a multi-arch image rebuild via [GitHub Actions](.github/workflows/dockerpush.yml).
