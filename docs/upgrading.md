# Updating the checker

Run these commands from the directory containing your existing `docker-compose.yml`. Keep the same directory and Compose project name. If you use another filename or container name, substitute it below.

These commands target the checker. Do not run `docker compose down` on a shared project, or use `down -v`. Those commands affect other services and can delete named volumes.

## Back up first

This saves the configuration, history and current image before `latest` changes. The private backup folder sits outside the install directory. It works whether `/app/logs` uses a host folder or a named volume. Stopping the checker keeps the history consistent during the copy.

```bash
(
  set -e
  stamp=$(date -u +%Y%m%dT%H%M%SZ)
  backup="$(cd .. && pwd)/pickmypostcode-backup-${stamp}"
  mkdir -m 700 "$backup"
  rollback_tag="pickmypostcode-checker:rollback-${stamp}"
  docker image tag "$(docker inspect -f '{{.Image}}' pickmypostcode-checker)" "$rollback_tag"
  printf '%s\n' "$rollback_tag" > "$backup/rollback-tag"
  cp docker-compose.yml "$backup/"
  if [ -f .env ]; then cp .env "$backup/"; fi
  docker compose stop pickmypostcode-checker
  mkdir "$backup/history"
  docker cp pickmypostcode-checker:/app/logs/. "$backup/history/"
  printf 'Backup saved in %s\n' "$backup"
)
```

Keep the backup and local rollback image until the update is verified. If a step fails, stop and resolve it before updating. `docker compose start pickmypostcode-checker` resumes the existing container.

If the checker container is already gone, copy its history from the original host folder or named volume instead. You also need a saved image tag or immutable digest for rollback. `latest` alone cannot identify the previous version.

## Update a current installation

For an installation that already runs without Selenium, keep its Compose file and settings:

```bash
docker compose pull pickmypostcode-checker &&
docker compose up -d --no-deps pickmypostcode-checker &&
docker exec -t pickmypostcode-checker python run.py --test
```

Open your inbox and confirm the test email arrived. A successful SMTP send alone does not prove delivery. If you intentionally pinned an image version in your Compose file, change that tag to the version you want before pulling.

## Migrate an installation that uses Selenium

Back up first using the steps above.

If `docker-compose.yml` is the unmodified stock file and contains only this checker and its dedicated Selenium service, replace it with the current file. Download and validate it before replacing anything:

```bash
(
  set -e
  trap 'rm -f docker-compose.yml.new' EXIT
  curl -fsS -o docker-compose.yml.new https://raw.githubusercontent.com/JonathanLangton1/pickmypostcode-auto-win-checker/main/docker-compose.yml
  docker compose -f docker-compose.yml.new config --quiet
  mv docker-compose.yml.new docker-compose.yml
)
```

For a custom or shared Compose file, edit the existing file instead:

- Set the checker's image to `jonathanlangton1/pickmypostcode-auto-win-checker:latest`, or the desired commit tag.
- Remove `SELENIUM_URL` and only the `selenium-chrome` entry from the checker's `depends_on`.
- Keep its credentials, timezone, history mount and any other dependencies. Keep every other service.
- Use `restart: unless-stopped` if you want the checker to return after a host reboot.

Run the update and test commands from the previous section. Once the email arrives, remove the old Selenium container only if nothing else uses it. With the stock container name:

```bash
docker stop selenium-chrome &&
docker rm selenium-chrome
```

Remove its service definition from the Compose file if it is still there. Do not use `--remove-orphans` on a partial copy of a shared Compose file.

## Roll back

Use the backup made before the update. A Selenium-era image needs its old Compose file, browser dependency and old history. Restore all of them before restarting the checker.

First stop the checker and restore its configuration. Replace `TIMESTAMP` with your backup's timestamp:

```bash
(
  set -e
  backup="$(cd .. && pwd)/pickmypostcode-backup-TIMESTAMP"
  docker image inspect "$(cat "$backup/rollback-tag")" > /dev/null
  docker compose stop pickmypostcode-checker
  cp "$backup/docker-compose.yml" docker-compose.yml
  if [ -f "$backup/.env" ]; then cp "$backup/.env" .env; fi
  restored="$(cd .. && pwd)/pickmypostcode-history-restored-TIMESTAMP"
  mkdir -m 700 "$restored"
  cp -a "$backup/history/." "$restored/"
  printf 'Set the checker image to: %s\n' "$(cat "$backup/rollback-tag")"
  printf 'Set its history mount to: %s:/app/logs\n' "$restored"
)
```

Now edit **only the checker service** in the restored Compose file:

1. Set `image` to the saved rollback tag printed above. Do not leave it as `latest`.
2. Replace its `/app/logs` mount with the absolute restored folder printed above. This works for both bind mounts and named-volume installations and leaves the original history untouched.

Then validate and start it:

```bash
docker compose config --quiet &&
docker compose up -d pickmypostcode-checker
```

This starts dependencies from the restored file, including Selenium when the old checker needs it. Keep unrelated service definitions intact.

## Older history files

The checker reads older history and migrates it automatically. A version 1 file gets a timestamped `pastData.json.v1-backup-*` copy before migration. Version 2 is updated in place, so keep your own backup for rollback.

An old `lastBrowserLogin` becomes `lastAccountCheck`. A pre-noon receipt belongs to the previous credit period. Already-recorded win emails stay recorded. Version 1 did not track whether a win email was sent, so an unclaimed win that is still open may be emailed once after upgrading.
