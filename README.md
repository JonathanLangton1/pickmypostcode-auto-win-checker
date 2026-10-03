# Pick My Postcode auto win checker

Get an email the moment your postcode wins on [Pick My Postcode](https://pickmypostcode.com/). One command to set up, then it runs by itself.

| When you win | Every Sunday |
| :---: | :---: |
| ![Win email: "You won 2 draws" with a claim button and each prize's deadline](https://raw.githubusercontent.com/JonathanLangton1/pickmypostcode-auto-win-checker/main/docs/images/email-win.png) | ![Weekly summary email: wins, draws checked and a grid of every draw for the week](https://raw.githubusercontent.com/JonathanLangton1/pickmypostcode-auto-win-checker/main/docs/images/email-weekly.png) |

- **Every draw, four times a day.** Main, Survey, Video, Bonus and Mini draws, plus both Stackpots, at 09:01, 14:00, 18:01 and 21:01 UK time.
- **Collects your daily bonus** and records your account activity.
- **Quiet unless it matters.** You get mail for a win, the Sunday summary, or a problem (at most one problem email a day).

**You still claim prizes yourself on the website.** The Mini Draw and Stackpots go to whoever claims first, so act as soon as a win email arrives.

## Set it up

You need three things:

1. A [Pick My Postcode account](https://pickmypostcode.com/).
2. A machine that stays on, with Python 3.9+ and [Docker](https://docs.docker.com/get-started/get-docker/) (Compose 2.24+). A 64-bit Linux server, Raspberry Pi or Mac all work.
3. A Gmail address with an [app password](https://myaccount.google.com/apppasswords) to send the emails. This needs 2-Step Verification turned on. [Google's instructions](https://support.google.com/accounts/answer/185833) help if the option is missing.

Then run:

```bash
curl -fsSLo pmp-setup.py https://raw.githubusercontent.com/JonathanLangton1/pickmypostcode-auto-win-checker/main/setup.py &&
python3 pmp-setup.py
```

Setup asks a few questions, checks your account, sends a test email and starts the checker once you confirm the email arrived. That's it.

<details>
<summary>Setup details</summary>

- Settings and history go in `~/pickmypostcode`. Pass `--directory /your/path` to use another folder.
- Your app password stays hidden while you type.
- From a clone of this repository, run `python3 setup.py` instead.
- Rerunning setup is safe. It keeps existing settings and history, and refuses to overwrite custom or shared Compose files.
- On Linux, the checker restarts after a reboot when Docker starts on boot. On a Mac, leave Docker running and prevent sleep.
- Images support amd64 and arm64. On a Pi running a 64-bit OS, follow the [Docker installation guide for Debian](https://docs.docker.com/engine/install/debian/).
- Upgrading an older installation? Follow the [upgrade guide](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/blob/main/docs/upgrading.md).

</details>

## Everyday commands

Run these from the install directory.

| Action | Command |
| --- | --- |
| Follow the logs | `docker logs -f pickmypostcode-checker` |
| Check now | `docker exec pickmypostcode-checker python run.py` |
| Send a test email | `docker exec -t pickmypostcode-checker python run.py --test` |
| Stop | `docker compose stop pickmypostcode-checker` |
| Start again | `docker compose start pickmypostcode-checker` |

A manual check emails you about any new wins it finds.

## More

- [Updating, Selenium migration and rollback](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/blob/main/docs/upgrading.md)
- [Local builds and tests](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/blob/main/docs/development.md)
- [Manual configuration](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/blob/main/env.example)
- [Docker Hub image](https://hub.docker.com/r/jonathanlangton1/pickmypostcode-auto-win-checker)
