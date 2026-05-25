# Pick My Postcode Auto Win Checker

[![Build](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/actions/workflows/dockerpush.yml/badge.svg?branch=main)](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/actions/workflows/dockerpush.yml)
[![Last commit](https://img.shields.io/github/last-commit/JonathanLangton1/pickmypostcode-auto-win-checker?label=updated)](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/commits/main)
[![Docker image](https://img.shields.io/docker/v/jonathanlangton1/pickmypostcode-auto-win-checker/latest?label=docker%20image&logo=docker)](https://hub.docker.com/r/jonathanlangton1/pickmypostcode-auto-win-checker)

Automatically signs into [pickmypostcode.com](https://pickmypostcode.com/) every day at 2pm and emails you when your postcode wins.

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

That's it. From now on, the bot runs daily at 14:00 UK time and only emails you when you win (plus a summary every Sunday).

## Useful commands

```bash
# Pull the latest published image and restart
docker compose pull && docker compose up -d

# Trigger a real run right now (instead of waiting for 2pm)
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

Every push to `main` triggers a multi-arch image rebuild via [GitHub Actions](.github/workflows/dockerpush.yml).
