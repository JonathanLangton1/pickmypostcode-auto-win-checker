# Pick My Postcode auto win checker

Checks your [Pick My Postcode](https://pickmypostcode.com/) account and emails you when your postcode wins. **You claim prizes yourself on the website.**

It covers the Main, Survey, Video, Bonus and Mini draws, plus both daily Stackpots. It records daily account activity, collects the daily bonus and sends a weekly summary on Sunday evening.

The checker runs at startup and at **09:01, 14:00, 18:01 and 21:01 UK time**, regardless of your server's timezone. Every check reads all draws. The Mini Draw and Stackpots are first to claim, so act as soon as a winning email arrives.

## What you need

- A [Pick My Postcode account](https://pickmypostcode.com/).
- Python 3.9 or newer and [Docker with Compose](https://docs.docker.com/get-started/get-docker/) 2.24 or newer.
- A 64-bit Linux server, Raspberry Pi or Mac. Images support amd64 and arm64. For a Pi running a 64-bit OS, follow the [Docker installation guide for Debian](https://docs.docker.com/engine/install/debian/).
- A Gmail address and [app password](https://myaccount.google.com/apppasswords) to send notifications. Turn on 2-Step Verification first. See [Google's instructions](https://support.google.com/accounts/answer/185833) if the option is missing.

## Set it up

Run this in a terminal:

```bash
curl -fsSLo pmp-setup.py https://raw.githubusercontent.com/JonathanLangton1/pickmypostcode-auto-win-checker/main/setup.py &&
python3 pmp-setup.py
```

Setup asks for your account email, postcode, Gmail details and notification inbox. Your app password stays hidden while you type. It checks your account and the draw results, sends a test email, then starts the checker after you confirm the email arrived.

Settings and history go in `~/pickmypostcode`. Use `--directory /your/path` to choose another folder. From a clone of this repository, run `python3 setup.py` instead.

You can rerun setup for an installation it created. It preserves existing settings and history and refuses to overwrite custom or shared Compose files. For older installations, follow the [upgrade guide](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/blob/main/docs/upgrading.md).

Keep the machine online. On Linux, the checker restarts after reboot when Docker starts on boot. On a Mac, leave Docker running and prevent sleep.

## Everyday commands

Run these from the install directory. They target only the checker.

| Action | Command |
| --- | --- |
| Follow the logs | `docker logs -f pickmypostcode-checker` |
| Check now | `docker exec pickmypostcode-checker python run.py` |
| Send another test email | `docker exec -t pickmypostcode-checker python run.py --test` |
| Stop | `docker compose stop pickmypostcode-checker` |
| Start again | `docker compose start pickmypostcode-checker` |

A manual check can email new wins. Normally you receive mail for wins, the Sunday summary or a problem. Problem emails are limited to one a day.

## More detail

- [Updating, Selenium migration and rollback](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/blob/main/docs/upgrading.md)
- [Local builds and tests](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/blob/main/docs/development.md)
- [Manual configuration](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/blob/main/env.example)
- [Docker Hub image](https://hub.docker.com/r/jonathanlangton1/pickmypostcode-auto-win-checker)
