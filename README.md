# Pick My Postcode Auto Win Checker

Automatically signs into [pickmypostcode.com](https://pickmypostcode.com/) every day at 2pm and emails you when your postcode wins.

## Requirements

- [Docker](https://docs.docker.com/get-docker/)
- A Gmail account with an [app password](https://knowledge.workspace.google.com/kb/how-to-create-app-passwords-000009237) (used to send notification emails)

## Quick start

1. Clone this repo and `cd` into it.
2. Copy the example env file and fill in your values:
   ```bash
   cp env.example .env
   ```
3. Start the checker:
   ```bash
   docker compose up -d --build
   ```
4. **Confirm it works** — fire off a test email:
   ```bash
   docker exec pickmypostcode-checker python run.py --test
   ```
   Within a few seconds you'll get a "Pick My Postcode auto checker is ready ✅" email at your `NOTIFICATION_EMAIL_ADDRESS`. If you don't, your Gmail SMTP credentials are wrong.

That's it. From now on, the bot runs daily at 14:00 and only emails you when you win (plus a summary every Sunday).

## Useful commands

```bash
# Trigger a real run right now (instead of waiting for 2pm)
docker exec pickmypostcode-checker python run.py

# Tail logs
docker logs -f pickmypostcode-checker

# Stop everything
docker compose down
```

## Dev mode (watch it run in a live browser)

Useful if the site's HTML changes and locators break:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm pickmypostcode-checker
```

Open <http://localhost:7900> (password: `secret`) to watch Chromium drive itself. Python sources are bind-mounted, so edits take effect on the next run without rebuilding.
