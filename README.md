# Pick My Postcode Auto Win Checker

[![Build](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/actions/workflows/dockerpush.yml/badge.svg?branch=main)](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/actions/workflows/dockerpush.yml)
[![Last commit](https://img.shields.io/github/last-commit/JonathanLangton1/pickmypostcode-auto-win-checker?label=updated)](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/commits/main)
[![Docker image](https://img.shields.io/docker/v/jonathanlangton1/pickmypostcode-auto-win-checker/latest?label=docker%20image&logo=docker)](https://hub.docker.com/r/jonathanlangton1/pickmypostcode-auto-win-checker)

Checks [pickmypostcode.com](https://pickmypostcode.com/) through its API and emails you when your postcode wins a draw — including the 6pm £100 Mini Draw and both daily Stackpot draws. Once a day, from 2pm UK time, it also records the daily bonus: one penny each for Main, Video and Survey. That credit runs noon to noon, UK time.

Works on Docker hosts running amd64 or 64-bit ARM: a Linux server, a 64-bit Raspberry Pi, or a Mac (Intel or Apple Silicon). There is no 32-bit image.

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- A Gmail account with an [app password](https://knowledge.workspace.google.com/kb/how-to-create-app-passwords-000009237) (used to send notification emails)
- Your Pick My Postcode email and postcode, in `.env`

There is no browser and no Selenium container.

## Fresh install

Put two files in an empty folder, fill in `.env`, and start:

```bash
mkdir pickmypostcode && cd pickmypostcode

curl -fsS -o docker-compose.yml https://raw.githubusercontent.com/JonathanLangton1/pickmypostcode-auto-win-checker/main/docker-compose.yml
curl -fsS -o .env https://raw.githubusercontent.com/JonathanLangton1/pickmypostcode-auto-win-checker/main/env.example

# edit .env with your details
nano .env

docker compose up -d
```

**Confirm it works** — run the health check:

```bash
docker exec -t pickmypostcode-checker python run.py --test
```

This runs the live account check, fetches the public draw results, and asks your mail server to accept a summary email. It prints a coloured report:

- ✓ Account activity verified (the noon-to-noon day, how many new pennies, bonus balance)
- ✓ Results API fetch
- ✓ Mail server accepted the summary email

The SMTP line means the mail server accepted the message. It does not prove the message landed in the inbox; check the inbox for that. The report then shows the latest winning postcodes and whether yours won. If a check fails, it is printed in red and the command exits non-zero.

From then on the bot only emails you for a win, for a problem (at most once a day), and for the Sunday evening summary.

## Upgrade an existing install

History is whatever directory the checker mounts (often `./pickmypostcode_logs`, sometimes a path such as `/opt/appdata/pickmypostcode`). It is not a Docker volume. Do not run `docker compose down -v`.

An old compose file starts Selenium as well as the checker. Pulling the image does not stop that. Back up beside the checkout, not inside it, so the credential copy is not left where git or an image build can see it, and a later backup does not overwrite an earlier one. Use the stock block only when your compose file is still the unmodified one from this project. Any edit belongs on the shared path.

### Stock install

Use this only when `docker-compose.yml` is still the unmodified file shipped for this checker. A file that lists only the checker and mounts `./pickmypostcode_logs` can still have local settings (image, environment, restart policy, extra volumes). Those are custom. Do not replace that file; use the shared steps.

Run this from the project directory. The subshell stops at the first error and does not change your shell's options. The download is checked before it replaces the file you are running. Pull and recreate run only after that replacement.

```bash
(
  set -e
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  backup="../pickmypostcode-backup-${stamp}"
  mkdir -m 700 "$backup"
  cp "docker-compose.yml" "$backup/"
  cp ".env" "$backup/"
  cp -a "pickmypostcode_logs" "$backup/"
  curl -fsS -o "docker-compose.yml.new" https://raw.githubusercontent.com/JonathanLangton1/pickmypostcode-auto-win-checker/main/docker-compose.yml
  docker compose -f "docker-compose.yml.new" config --quiet
  mv "docker-compose.yml.new" "docker-compose.yml"
  docker compose pull
  docker compose up -d --remove-orphans
)
```

`--remove-orphans` is safe here because the new file is the whole unmodified project. The container it drops is the old `selenium-chrome` service.

### Shared or customised compose file

Use this when the file also runs other services, the history mount is not `./pickmypostcode_logs`, or you have changed the stock file. Do not replace that file with the one-service file from GitHub, and do not run `--remove-orphans` against that download. Compose would treat every service missing from the downloaded file as an orphan.

Back up beside the checkout and stop if a copy fails. Put the directory the checker actually mounts in the last copy:

```bash
(
  set -e
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  backup="../pickmypostcode-backup-${stamp}"
  mkdir -m 700 "$backup"
  cp "docker-compose.yml" "$backup/"
  cp ".env" "$backup/"
  cp -a "/path/to/history" "$backup/history"
)
```

Edit the existing file only:

- Keep every other service, the project name, and the checker's `env_file`, timezone, and volume mount.
- On `pickmypostcode-checker`, remove `SELENIUM_URL`. In `depends_on`, remove only `selenium-chrome` and keep any other dependencies.
- Leave the `selenium-chrome` service in the file until the new checker has passed its health check, so the commands below still match a service Compose knows.

```bash
docker compose pull pickmypostcode-checker &&
docker compose up -d --no-deps pickmypostcode-checker &&
docker exec -t pickmypostcode-checker python run.py --test
```

`--no-deps` recreates the checker without starting Selenium or the other services. When the health check passes, remove that dedicated browser only if no other service uses it, then delete its service from the file:

```bash
docker compose stop selenium-chrome &&
docker compose rm -f selenium-chrome
```

If you delete the `selenium-chrome` service from the file first, Compose will no longer recognise those commands. The old file names that container `selenium-chrome`, so remove that container directly, still only when nothing else uses it:

```bash
docker stop selenium-chrome &&
docker rm selenium-chrome
```

Do not follow either of those with `docker compose up -d --remove-orphans` unless the file on disk is still the full project and the only service you mean to drop is Selenium.

### Rollback

`latest` and the full commit SHA are the same API-era image. Point `image:` at `jonathanlangton1/pickmypostcode-auto-win-checker:<sha>` and recreate the checker to roll back inside this series. Use the compose file from this series with it.

A Selenium-era image does not run from the new one-service file, and it does not read a history file this version has rewritten (`lastBrowserLogin` is saved as `lastAccountCheck`). The first run keeps a version 1 file as `pastData.json.v1-backup-…`. A version 2 file is updated in place, so the copy you took before upgrading is the copy to restore, along with the compose file from before the API change.

### What the history file keeps

An older file is still read. A `lastBrowserLogin` day is kept and then saved as `lastAccountCheck`. Win emails already recorded stay recorded. A check before noon belongs to the previous noon-to-noon period, so it does not skip the 2pm credit.

## When it checks

Draw times are UK time, and so is the schedule, whatever timezone the host is in.

| UK time | Checks |
| ------- | ------ |
| 09:01 | 9am Stackpot |
| 14:00 | Main, Survey, Video and Bonus draws (drawn at noon), plus the daily account check |
| 18:01 | £100 Mini Draw (claimable 6pm–2am) |
| 21:01 | 9pm Stackpot; on Sundays, the weekly summary follows |

Every check reads every draw, and the bot also checks once when it starts, so draws that are still open are caught up after a missed check or a restart. Results whose claim window has already closed can't be recovered. If a draw isn't published yet, it re-checks every minute for up to 15 minutes. If a winning email fails, or a still-open draw can't be fetched, it tries again every 5 minutes, and never sends a win after it can no longer be claimed.

The daily account check runs on scheduled checks from 14:00, once per noon-to-noon period. A manual run (`docker exec … python run.py`) always does it. A retry does not. Each account request uses a 5 second connect timeout and a 15 second read timeout, and is tried once more after a timeout or a gateway error. The read timeout is inactivity on that request. A 60 second budget stops the checker from starting another account request; a request already started still runs until its own timeout. The receipt is saved only when Main, Video and Survey are all verified for the current period. Already credited is a success. A failed, partial, or unverified check is not saved, and the next scheduled check tries again. Finding the bonus already collected is not an error.

Each winning draw is emailed once; wins found at the same time share one email. Re-checks and restarts don't send repeats, but the 9am and 9pm Stackpots are separate draws, so a postcode listed in both is notified for each. Delivery isn't guaranteed exactly once: if the bot is stopped just after an email is sent, it may send that email again. The Mini Draw and Stackpot go to the first registered person at the postcode to claim, so be quick. For the same reason, their wins are only emailed straight after the results show them unclaimed; if the results can't be read, the email waits for a check that can confirm it. If something breaks, you get at most one accepted error email a day. That mark is stored in the history file. If the file cannot be written, the running process remembers the acceptance until it exits, and a restart can send the day's error email again.

History is kept in `pickmypostcode_logs/pastData.json` for one postcode. If you change `YOUR_POSTCODE`, the old file is renamed (for example `pastData.json.postcode-AB12CD-…`) and a new history starts. An unreadable file is renamed to `pastData.json.corrupt-…` and a new history starts. When upgrading from an older version, its history is converted automatically and the original is kept as `pastData.json.v1-backup-…`. The old 2pm run saw the previous evening's Mini Draw, so those Mini results are moved back a day. The old version didn't record whether its win emails were delivered, so a win that can still be claimed is emailed once after upgrading, even if you already had that email.

## Useful commands

```bash
# Stock install only: pull the image and drop the old Selenium service.
# A shared compose file should use the upgrade steps above, not this.
docker compose pull && docker compose up -d --remove-orphans

# Run a real check right now, including the account check (emails any new wins)
docker exec pickmypostcode-checker python run.py

# Tail logs
docker logs -f pickmypostcode-checker

# Stop the checker. This does not delete pickmypostcode_logs/ or .env.
docker compose down
```

## Local build

Offline tests, with no network and no email:

```bash
pip install -r requirements.txt
python -m unittest
```

A local image, using `.env` and `pickmypostcode_logs/` in this directory, one check and then exit:

```bash
docker compose -f docker-compose.dev.yml run --rm --build pickmypostcode-checker
```

Add `python run.py --test` to that command for the health check. That talks to the live API and sends a real summary email.

Every push to `main` runs the tests, then publishes linux/amd64 and linux/arm64 (64-bit ARM) to Docker Hub as `latest` and as the full commit sha. Pull requests run the tests and do not publish.
