# Local builds and tests

Run these from the repository directory. Offline tests use the Python sources on your machine. They do not use the network and they do not send email. The image and the GitHub workflow use Python 3.12.

```bash
pip install -r requirements.txt &&
python -m unittest
```

Copy [env.example](https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/blob/main/env.example) to `.env` and edit `.env` with your details. This builds a local image, reads those settings, writes history to `pickmypostcode_logs`, runs one real check and exits. A real check can email new wins.

```bash
docker compose -f docker-compose.dev.yml run --rm --build pickmypostcode-checker
```

The same command with `python run.py --test` runs the health check. That talks to the live account and results, and asks Gmail to accept a summary email. Open the inbox to confirm it arrived.

```bash
docker compose -f docker-compose.dev.yml run --rm --build pickmypostcode-checker python run.py --test
```

A push to `main` runs the tests, then publishes `linux/amd64` and `linux/arm64` to Docker Hub as `latest` and as the full commit SHA. A pull request runs the tests and does not publish.
