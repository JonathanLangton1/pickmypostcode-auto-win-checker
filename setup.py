#!/usr/bin/env python3
"""Set up the Pick My Postcode checker. Python 3.9+ standard library only.

From a checkout:
    python3 setup.py
    python3 setup.py --directory ~/pickmypostcode

Downloaded on its own (the Compose file is fetched from GitHub, then checked):
    curl -fsSLo pmp-setup.py https://raw.githubusercontent.com/JonathanLangton1/pickmypostcode-auto-win-checker/main/setup.py
    python3 pmp-setup.py

Docker and Compose v2 must already be installed. This does not install packages,
and it must not be run with sudo.
"""

import argparse
import getpass
import json
import os
import platform
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import warnings
from pathlib import Path


CONTAINER_NAME = "pickmypostcode-checker"
SERVICE_NAME = "pickmypostcode-checker"
MARKER_NAME = ".pmp-setup.json"
MARKER_OWNER = "pmp-setup"
LOG_DIR_NAME = "pickmypostcode_logs"
COMPOSE_NAME = "docker-compose.yml"
ENV_NAME = ".env"
ENV_KEYS = (
    "NOTIFICATION_EMAIL_ADDRESS",
    "YOUR_POSTCODE",
    "PMP_EMAIL",
    "EMAIL_ADDRESS",
    "EMAIL_PASSWORD",
)
MANAGED_NAMES = {COMPOSE_NAME, ENV_NAME, MARKER_NAME, LOG_DIR_NAME}
IGNORED_NAMES = {".DS_Store"}

COMPOSE_URL = (
    "https://raw.githubusercontent.com/JonathanLangton1/"
    "pickmypostcode-auto-win-checker/main/docker-compose.yml"
)
UPGRADE_URL = (
    "https://github.com/JonathanLangton1/pickmypostcode-auto-win-checker/"
    "blob/main/docs/upgrading.md"
)
MAC_DOCKER_URL = "https://docs.docker.com/desktop/setup/install/mac-install/"
DEBIAN_DOCKER_URL = "https://docs.docker.com/engine/install/debian/"
LINUX_DOCKER_URL = "https://docs.docker.com/engine/install/"
COMPOSE_INSTALL_URL = "https://docs.docker.com/compose/install/"
DOCKER_POSTINSTALL_URL = "https://docs.docker.com/engine/install/linux-postinstall/"
GMAIL_2SV_URL = "https://support.google.com/accounts/answer/185833"
GMAIL_APP_PASSWORD_URL = "https://myaccount.google.com/apppasswords"

MAX_COMPOSE_BYTES = 8192
POLL_ATTEMPTS = 20
POLL_SECONDS = 0.25
# `docker compose run --name` is what keeps the health check off the checker's
# container name. That behavior is relied on from Compose 2.24 onward.
MIN_COMPOSE_VERSION = (2, 24, 0)
HEALTH_PROJECT_PREFIX = "pmp-health-"
SHA_IMAGE_RE = re.compile(r"sha256:[a-fA-F0-9]{64}")
WORKDIR_TEMPLATE = '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}'
_progress = {"phase": "prepare", "directory": None, "managed": False}

# The published file, and nothing else. Kept as the lines we accept so a download
# cannot smuggle another service. The bytes we install are still the file's own.
STOCK_COMPOSE_LINES = (
    "services:",
    "pickmypostcode-checker:",
    "image: jonathanlangton1/pickmypostcode-auto-win-checker:latest",
    "container_name: pickmypostcode-checker",
    "env_file: .env",
    "environment:",
    "- TZ=Europe/London",
    "volumes:",
    "- ./pickmypostcode_logs:/app/logs",
    "working_dir: /app",
    "restart: unless-stopped",
)

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
POSTCODE_RE = re.compile(r"^([A-Z]{1,2}\d[A-Z\d]?)(\d[A-Z]{2})$")
APP_PASSWORD_GROUPS = re.compile(r"^[A-Za-z0-9]{4}(?: [A-Za-z0-9]{4}){3}$")


class SetupError(Exception):
    """A problem the user can act on. The message is the whole report."""


class Cancelled(Exception):
    """EOF or an explicit stop. Staging must already be discarded."""


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        directory = resolve_directory(args.directory)
        require_project_name(directory)
        _progress.update(phase="prepare", directory=directory, managed=False)
        explain(directory)
        ensure_python()
        ensure_not_root()
        ensure_architecture(platform.machine())
        require_terminal()
        ensure_docker()
        kind = classify_destination(directory)
        ensure_container_available(directory, kind)
        ensure_project_available(directory)
        if kind == "new":
            return install_new(directory)
        _progress["managed"] = True
        return reuse_managed(directory)
    except Cancelled:
        print(interrupt_message(), file=sys.stderr)
        return 1
    except SetupError as error:
        print(error, file=sys.stderr)
        return 1
    except OSError as error:
        print("Setup stopped because of a file error: {}.".format(error.strerror or error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(interrupt_message(), file=sys.stderr)
        return 1


def interrupt_message():
    """Neutral status after Ctrl-C. Never stops a container from here."""
    phase = _progress.get("phase")
    directory = _progress.get("directory")
    if phase in {"starting", "polling"} and directory is not None:
        return (
            "Setup was interrupted while starting or checking the checker.\n"
            "This did not stop the container. It may be running.\n"
            f"Directory: {directory}\n"
            f"Status: docker ps -a --filter name={CONTAINER_NAME}\n"
            f"Stop: docker stop {CONTAINER_NAME}"
        )
    if _progress.get("managed"):
        return "Setup cancelled. The existing checker was not stopped or rewritten."
    return "Setup cancelled. No service was started."


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Set up the Pick My Postcode checker under Docker."
    )
    parser.add_argument(
        "--directory",
        default="~/pickmypostcode",
        help="install directory (default: ~/pickmypostcode)",
    )
    return parser.parse_args(argv)


def resolve_directory(raw):
    """Real parent, original leaf. A leaf symlink is refused; /tmp -> /private/tmp is not."""
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = Path(os.path.abspath(path))
    if path.is_symlink():
        raise SetupError(
            f"{path} is a symlink. Choose a real directory with --directory. Nothing was changed."
        )
    parent = Path(os.path.realpath(path.parent))
    return parent / path.name


def require_project_name(directory):
    name = compose_project_name(directory)
    if not name:
        raise SetupError(
            f"The folder name {directory.name!r} cannot be a Docker Compose project name. "
            "Choose a --directory whose name contains ASCII letters or digits. "
            "Underscores and dashes are kept. "
            "Compose uses that folder name when you run docker compose in the directory, "
            "so this setup will not invent a different project name."
        )
    return name


def explain(directory):
    print(
        "Pick My Postcode checker setup\n"
        "\n"
        "Files for this checker will live in:\n"
        f"  {directory}\n"
        "\n"
        "What this command does:\n"
        "- save your details in a private file in that directory\n"
        "- install the stock Docker Compose file after checking it\n"
        "- pull the published image and run one health check\n"
        "  (sign in, read the draws, and send a test email)\n"
        "- ask you to confirm that the test email is in the inbox\n"
        "- start the checker only after that\n"
        "\n"
        "The service is set to restart unless you stop it, including after a reboot.\n"
        "Docker and Docker Compose v2 are required, and so is Python 3.9 or newer.\n"
        "This setup does not install Docker and does not change system packages.\n"
        "Run it as your own user, not with sudo.\n"
        "It asks for a Gmail app password, never your Pick My Postcode password.\n"
        "That app password is stored only in the private file. It is not printed.\n",
        flush=True,
    )


def ensure_python():
    if sys.version_info < (3, 9):
        raise SetupError("Python 3.9 or newer is required. This is Python {}.".format(
            platform.python_version()
        ))


def ensure_not_root():
    euid = os.geteuid() if hasattr(os, "geteuid") else 0
    if euid == 0:
        raise SetupError(
            "Do not run this setup with sudo. Run it as the user who should own the files.\n"
            "If Docker said permission denied, add that user to the docker group and log in again:\n"
            f"  {DOCKER_POSTINSTALL_URL}"
        )


def ensure_architecture(machine):
    normalized = machine.lower()
    if normalized in {"x86_64", "amd64", "aarch64", "arm64"}:
        return
    if normalized.startswith("arm") or normalized in {"armv6l", "armv7l", "armv8l"}:
        raise SetupError(
            f"This machine reports {machine}, which is 32-bit ARM. "
            "The checker runs on 64-bit amd64 and arm64 only.\n"
            "Install 64-bit Raspberry Pi OS, then install Docker with the Debian steps:\n"
            f"  {DEBIAN_DOCKER_URL}"
        )
    raise SetupError(
        f"This machine reports {machine}. The checker runs on amd64 and arm64 only."
    )


def require_terminal():
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SetupError(
            "Run this setup in an interactive terminal. "
            "Input and output are redirected, so it stopped before asking for a password.\n"
            "The Gmail app password is read with echo turned off and is never accepted from a pipe."
        )


def host_kind():
    if sys.platform == "darwin":
        return "mac"
    for candidate in ("/proc/device-tree/model", "/sys/firmware/devicetree/base/model"):
        try:
            raw = Path(candidate).read_bytes()
        except OSError:
            continue
        model = raw.decode("utf-8", "ignore").replace("\x00", "")
        if "raspberry pi" in model.lower():
            return "raspberry-pi"
    return "linux"


def install_advice():
    kind = host_kind()
    if kind == "mac":
        return f"Install Docker Desktop for Mac, then run this setup again:\n  {MAC_DOCKER_URL}"
    if kind == "raspberry-pi":
        return (
            "Install Docker Engine on 64-bit Raspberry Pi OS with the Debian steps, "
            "then run this setup again:\n"
            f"  {DEBIAN_DOCKER_URL}\n"
            f"Compose plugin, if it was not included:\n  {COMPOSE_INSTALL_URL}"
        )
    return (
        "Install Docker Engine, then run this setup again:\n"
        f"  {LINUX_DOCKER_URL}\n"
        f"Install the Compose plugin:\n  {COMPOSE_INSTALL_URL}\n"
        "64-bit Raspberry Pi OS uses the Debian steps:\n"
        f"  {DEBIAN_DOCKER_URL}"
    )


def ensure_docker():
    if shutil.which("docker") is None:
        raise SetupError("Docker was not found on PATH.\n" + install_advice())
    info = run_capture(["docker", "info"])
    if info.returncode != 0:
        detail = (info.stderr or info.stdout or "").strip()
        low = detail.lower()
        if "permission denied" in low:
            raise SetupError(
                "Docker is installed, but this user cannot access the Docker daemon.\n"
                "Do not run this setup with sudo.\n"
                "On Linux, add your user to the docker group and log in again:\n"
                f"  {DOCKER_POSTINSTALL_URL}\n"
                "On a Mac, open Docker Desktop and wait until it says it is running.\n"
                + detail
            )
        if any(token in low for token in ("cannot connect", "is the docker daemon running", "connection refused", "error during connect")):
            if host_kind() == "mac":
                action = (
                    "Open Docker Desktop and wait until it says it is running.\n"
                    "Do not run the setup itself with sudo."
                )
            else:
                action = (
                    "Start Docker, then run this setup again. "
                    "For example: sudo systemctl start docker\n"
                    "Do not run the setup itself with sudo."
                )
            raise SetupError("Docker is installed, but the daemon is not running.\n" + action + "\n" + detail)
        raise SetupError("`docker info` failed.\n" + detail)
    version = run_capture(["docker", "compose", "version"])
    if version.returncode != 0:
        detail = (version.stderr or version.stdout or "").strip()
        raise SetupError(
            "Docker is running, but `docker compose` is not available.\n"
            f"Install the Compose v2 plugin:\n  {COMPOSE_INSTALL_URL}\n"
            + detail
        )
    reported = parse_compose_version((version.stdout or "") + "\n" + (version.stderr or ""))
    if reported is None or reported < MIN_COMPOSE_VERSION:
        found = (version.stdout or version.stderr or "").strip() or "an unknown version"
        raise SetupError(
            "Docker Compose 2.24 or newer is required "
            f"(found {found}).\n"
            "The health check uses `docker compose run --name` so it cannot take over "
            f"the {CONTAINER_NAME} container.\n"
            f"Upgrade the Compose plugin:\n  {COMPOSE_INSTALL_URL}"
        )


def parse_compose_version(text):
    match = re.search(r"\bv?(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def classify_destination(directory):
    if directory.is_symlink():
        raise SetupError(
            f"{directory} is a symlink. Choose a real directory with --directory. Nothing was changed."
        )
    if not directory.exists():
        parent = directory.parent
        if not parent.is_dir():
            raise SetupError(f"The parent directory does not exist: {parent}")
        return "new"
    if not directory.is_dir():
        raise SetupError(f"{directory} is not a directory.")
    entries = list(directory.iterdir())
    for entry in entries:
        if entry.name in MANAGED_NAMES and entry.is_symlink():
            raise SetupError(
                f"{entry} is a symlink. Refusing to follow or replace it. Nothing was changed."
            )
    names = {entry.name for entry in entries if entry.name not in IGNORED_NAMES}
    if not names:
        return "new"
    if MARKER_NAME not in names:
        raise SetupError(unmanaged_message(directory))
    extra = names - MANAGED_NAMES
    if extra:
        raise SetupError(
            f"{directory} has files this wizard does not manage ({', '.join(sorted(extra))}). "
            "Nothing was changed.\n" + upgrade_hint()
        )
    try:
        marker = json.loads((directory / MARKER_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SetupError(
            f"{directory} has a setup marker that cannot be read. Nothing was changed.\n" + upgrade_hint()
        ) from error
    if marker != {"managed_by": MARKER_OWNER, "version": 1}:
        raise SetupError(
            f"{directory} has a setup marker this version does not recognize. Nothing was changed.\n"
            + upgrade_hint()
        )
    compose_path = directory / COMPOSE_NAME
    env_path = directory / ENV_NAME
    logs = directory / LOG_DIR_NAME
    if not compose_path.is_file() or not env_path.is_file() or not logs.is_dir():
        raise SetupError(
            f"{directory} is an incomplete setup (Compose, private settings, and "
            f"{LOG_DIR_NAME} are all required). Nothing was changed.\n" + upgrade_hint()
        )
    try:
        validate_compose_text(compose_path.read_text(encoding="utf-8"))
        parse_env(env_path.read_text(encoding="utf-8"))
    except (SetupError, ValueError, UnicodeError) as error:
        raise SetupError(
            f"{directory} was created by this setup, but its Compose file or settings were changed. "
            "Nothing was replaced and no image was pulled, so this cannot overwrite custom settings "
            "or downgrade an image.\n"
            + upgrade_hint()
        ) from error
    return "managed"


def unmanaged_message(directory):
    return (
        f"{directory} already has an install this wizard does not manage. Nothing was changed.\n"
        "Shared or hand-edited Compose files are left alone.\n"
        + upgrade_hint()
    )


def upgrade_hint():
    return f"Upgrade steps: {UPGRADE_URL}"


def ensure_container_available(directory, kind):
    code, workdir, detail = inspect_working_dir()
    if code != 0:
        if "no such object" in detail.lower() or "no such container" in detail.lower():
            return
        raise SetupError("Could not check for an existing checker container.\n" + detail)
    if kind == "managed" and same_directory(workdir, directory):
        return
    where = workdir or "a container this Compose project does not own"
    raise SetupError(
        f"A container named {CONTAINER_NAME} already exists ({where}). "
        "This setup will not take it over or replace it. Nothing was changed.\n"
        + upgrade_hint()
    )


def ensure_project_available(directory):
    """Refuse a Compose project name that already belongs to another directory."""
    project = compose_project_name(directory)
    completed = run_capture([
        "docker", "ps", "-aq",
        "--filter", "label=com.docker.compose.project=" + project,
    ])
    if completed.returncode != 0:
        raise SetupError(
            f"Could not check whether Compose project {project} is already in use. Nothing was changed."
        )
    for container_id in completed.stdout.split():
        code, workdir, _detail = inspect_format(container_id, WORKDIR_TEMPLATE)
        if code != 0 or not same_directory(workdir, directory):
            where = workdir or "another directory"
            raise SetupError(
                f"Compose project {project} already belongs to {where}. "
                "Choose a --directory with a different folder name, or rerun setup in the directory "
                "that already owns that project. Nothing was changed.\n"
                + upgrade_hint()
            )


def same_directory(left, right):
    """Compare install directories after resolving ancestor symlinks, not the leaf."""
    if not left or not right:
        return False

    def physical(value):
        path = os.path.abspath(str(value))
        parent = os.path.realpath(os.path.dirname(path))
        return os.path.normpath(os.path.join(parent, os.path.basename(path)))

    return physical(left) == physical(right)


def install_new(directory):
    compose_text = load_compose_text()
    answers = prompt_answers(None)
    return verify(directory, compose_text, answers, managed=False)


def reuse_managed(directory):
    current = parse_env((directory / ENV_NAME).read_text(encoding="utf-8"))
    compose_text = (directory / COMPOSE_NAME).read_text(encoding="utf-8")
    image_id = running_image_id()
    print("This directory is already a setup created by this wizard.", flush=True)
    print(f"Account email: {current['PMP_EMAIL']}", flush=True)
    print(f"Postcode: {current['YOUR_POSTCODE']}", flush=True)
    print(f"Sending Gmail: {current['EMAIL_ADDRESS']}", flush=True)
    print(f"Notifications: {current['NOTIFICATION_EMAIL_ADDRESS']}", flush=True)
    print("The Gmail app password stays in the private file and is not shown.", flush=True)
    if image_id is None:
        print(
            "No checker container exists, so setup will pull the current published image "
            "and test that exact image. Saved history is left as it is.",
            flush=True,
        )
    if not ask_yes("Run the health check with these settings?", default_yes=True):
        current = prompt_answers(current, keep_password=True)
    return verify(directory, compose_text, current, managed=True, image_id=image_id)


def verify(directory, compose_text, answers, managed, image_id=None):
    """Health-check, confirm the inbox, then commit and start. Nothing live changes before confirmation."""
    if managed:
        untouched = "The current install was not changed and was not restarted."
        failed = "Health check failed. The current install was not changed and was not restarted."
        declined = "The inbox was not confirmed, so the checker was not updated and was not restarted."
    else:
        untouched = "Nothing was installed and no scheduler was started."
        failed = "Health check failed. Nothing was installed and no scheduler was started."
        declined = (
            "The inbox was not confirmed. The mail server accepting a message is not "
            "the same as it arriving, so nothing was installed and no scheduler was started."
        )
    staging = None
    try:
        while True:
            _progress["phase"] = "health"
            discard_staging(staging)
            # An id is the container's current image. Absence means pull the published tag.
            if image_id:
                staging = make_staging(compose_text, answers, image_id)
            else:
                staging = make_staging(compose_text, answers, None)
                if not pull_image(staging, directory):
                    discard_staging(staging)
                    staging = None
                    action = ask_health_retry(untouched)
                    if action == "quit":
                        raise SetupError("The image pull failed. " + failed)
                    if action == "edit":
                        answers = prompt_answers(answers, keep_password=True)
                    continue
                image_id = published_image_id()
                discard_staging(staging)
                staging = make_staging(compose_text, answers, image_id)
            try:
                healthy = run_health(staging, directory)
            except SetupError:
                discard_staging(staging)
                staging = None
                raise
            if not healthy:
                discard_staging(staging)
                staging = None
                action = ask_health_retry(untouched)
                if action == "quit":
                    raise SetupError(failed)
                if action == "edit":
                    answers = prompt_answers(answers, keep_password=True)
                continue
            if not confirm_inbox(answers["NOTIFICATION_EMAIL_ADDRESS"]):
                discard_staging(staging)
                staging = None
                raise SetupError(declined)
            _progress["phase"] = "committing"
            if managed:
                commit_rerun(directory, answers)
            else:
                promote_new(directory, staging, compose_text)
            discard_staging(staging)
            staging = None
            return start_and_report(directory, image_id)
    finally:
        discard_staging(staging)


def ask_health_retry(untouched):
    print(f"The health check failed. {untouched}", flush=True)
    if ask_yes("Retry the health check with the same answers?", default_yes=False):
        return "retry"
    if ask_yes("Edit the details and retry?", default_yes=False):
        return "edit"
    return "quit"


def running_image_id():
    """Image id of this install's container, or None when that container is absent."""
    code, _workdir, detail = inspect_working_dir()
    if code != 0:
        if "no such object" in detail.lower() or "no such container" in detail.lower():
            return None
        raise SetupError(
            "Could not inspect the running checker, so it was not tested or recreated. Nothing was changed."
        )
    code, image, _detail = inspect_format(CONTAINER_NAME, "{{.Image}}")
    if code != 0 or not SHA_IMAGE_RE.fullmatch(image):
        raise SetupError(
            "Could not read the image id of the running checker, so it was not tested against a different image. "
            "Nothing was changed."
        )
    return image


def confirm_inbox(recipient):
    print(
        "\nThe mail server accepting the message does not mean it reached the inbox.\n"
        f"Look in {recipient}, including spam, for the test email.\n",
        flush=True,
    )
    return ask_yes("Is the test email in the inbox?", default_yes=False)


def prompt_answers(defaults, keep_password=False):
    account = ask(
        "Pick My Postcode account email",
        parse_email,
        default=defaults["PMP_EMAIL"] if defaults else None,
    )
    postcode = ask(
        "UK postcode",
        parse_postcode,
        default=defaults["YOUR_POSTCODE"] if defaults else None,
    )
    gmail_default = None
    if defaults and defaults["EMAIL_ADDRESS"].lower().endswith(("@gmail.com", "@googlemail.com")):
        gmail_default = defaults["EMAIL_ADDRESS"]
    elif account.lower().endswith(("@gmail.com", "@googlemail.com")):
        gmail_default = account
    sender = ask("Gmail address that will send mail", parse_gmail, default=gmail_default)
    saved_password = defaults.get("EMAIL_PASSWORD") if defaults else None
    if keep_password and saved_password:
        password = prompt_password(saved_password)
    else:
        password = prompt_password()
    recipient_default = defaults["NOTIFICATION_EMAIL_ADDRESS"] if defaults else account
    recipient = ask(
        "Address that should receive win emails",
        parse_email,
        default=recipient_default,
    )
    return {
        "PMP_EMAIL": account,
        "YOUR_POSTCODE": postcode,
        "EMAIL_ADDRESS": sender,
        "EMAIL_PASSWORD": password,
        "NOTIFICATION_EMAIL_ADDRESS": recipient,
    }


def ask(label, parse, default=None):
    while True:
        shown = f"{label} [{default}]" if default else label
        try:
            raw = input(f"{shown}: ")
        except EOFError as error:
            raise Cancelled() from error
        text = raw.strip()
        if text == "" and default is not None:
            text = default
        try:
            return parse(text)
        except ValueError as error:
            print(error, flush=True)


def ask_yes(label, default_yes):
    suffix = "[Y/n]" if default_yes else "[y/N]"
    while True:
        try:
            raw = input(f"{label} {suffix} ").strip().lower()
        except EOFError as error:
            raise Cancelled() from error
        if raw == "":
            return default_yes
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Answer y or n.", flush=True)


def prompt_password(saved=None):
    print("Gmail will not accept your normal Gmail password.", flush=True)
    print(f"Turn on 2-Step Verification: {GMAIL_2SV_URL}", flush=True)
    print(f"Create an app password and paste it here: {GMAIL_APP_PASSWORD_URL}", flush=True)
    print("The app password is 16 letters or digits, often in groups of four. Spaces are fine.", flush=True)
    if saved:
        print("Press Enter to keep the saved app password.", flush=True)
    if not sys.stdin.isatty():
        raise SetupError(
            "Refusing to read the Gmail app password because this is not an interactive terminal."
        )
    while True:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                raw = getpass.getpass("Gmail app password: ")
        except EOFError as error:
            raise Cancelled() from error
        except getpass.GetPassWarning as error:
            raise SetupError(
                "Refusing to read the Gmail app password because the terminal would echo it."
            ) from error
        if saved is not None and raw == "":
            return saved
        try:
            return normalize_password(raw)
        except ValueError as error:
            print(error, flush=True)


def require_single_line(value, label):
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{label} cannot contain newlines or control characters.")


def parse_email(value):
    require_single_line(value, "Email")
    value = value.strip()
    if not EMAIL_RE.fullmatch(value) or len(value) > 254:
        raise ValueError("Enter one email address, such as name@example.com.")
    return value


def parse_gmail(value):
    value = parse_email(value)
    if not value.lower().endswith(("@gmail.com", "@googlemail.com")):
        raise ValueError("The sending address must be @gmail.com or @googlemail.com.")
    return value


def parse_postcode(value):
    require_single_line(value, "Postcode")
    compact = re.sub(r"\s+", "", value).upper()
    match = POSTCODE_RE.fullmatch(compact)
    if not match:
        raise ValueError("Enter a UK postcode, such as SW1A 1AA.")
    return f"{match.group(1)} {match.group(2)}"


def normalize_password(raw):
    if any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise ValueError("The app password cannot contain newlines or control characters.")
    stripped = raw.strip()
    if APP_PASSWORD_GROUPS.fullmatch(stripped):
        return stripped.replace(" ", "")
    if re.fullmatch(r"[A-Za-z0-9]{16}", raw):
        return raw
    if raw == stripped and " " not in raw and 8 <= len(raw) <= 128:
        return raw
    raise ValueError(
        "Paste the 16-character app password (spaces between the groups are fine)."
    )


def encode_env_value(value):
    """Compose-literal encoding: JSON string with `$` doubled so Compose keeps it literal."""
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise SetupError("Refusing to store a credential that contains control characters.")
    return json.dumps(value.replace("$", "$$"), ensure_ascii=False)


def render_env(values):
    lines = []
    for key in ENV_KEYS:
        if key not in values or values[key] == "":
            raise SetupError(f"Missing {key}.")
        lines.append(f"{key}={encode_env_value(values[key])}")
    return "\n".join(lines) + "\n"


def decode_env_value(raw):
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError("settings value is not a JSON string") from None
    if not isinstance(loaded, str) or loaded == "":
        raise ValueError("settings value is not a JSON string")
    value = loaded.replace("$$", "$")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("settings value contains control characters")
    return value


def parse_env(text):
    found = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line != line.strip() or "=" not in line:
            raise ValueError(f"unsupported settings line {line_number}")
        key, raw = line.split("=", 1)
        if key not in ENV_KEYS or key in found:
            raise ValueError(f"unexpected setting on line {line_number}")
        try:
            found[key] = decode_env_value(raw)
        except ValueError:
            raise ValueError(f"unsupported settings line {line_number}") from None
    if set(found) != set(ENV_KEYS) or any(value == "" for value in found.values()):
        raise ValueError("settings file does not match the setup this wizard writes")
    return found


def validate_compose_text(text):
    if not text or len(text.encode("utf-8")) > MAX_COMPOSE_BYTES:
        raise SetupError("Refusing that Compose file: it is empty or larger than the stock file.")
    if "\x00" in text or "\r" in text or "${" in text or "`" in text:
        raise SetupError("Refusing that Compose file: it is not the stock one-service template.")
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if tuple(lines) != STOCK_COMPOSE_LINES:
        raise SetupError(
            "Refusing that Compose file: it is not the stock one-service template "
            f"for {CONTAINER_NAME}."
        )
    return text


def load_compose_text():
    sibling = Path(__file__).resolve().parent / COMPOSE_NAME
    if sibling.is_symlink():
        raise SetupError(
            f"{sibling} is a symlink. Not using it, and not downloading a replacement over it."
        )
    if sibling.is_file():
        try:
            text = sibling.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise SetupError(f"Could not read {sibling}.") from error
        try:
            validate_compose_text(text)
        except SetupError as error:
            raise SetupError(
                f"The Compose file next to this script is not the stock template, so it was not installed.\n{error}"
            ) from error
        return text
    return download_compose_text()


def download_compose_text():
    request = urllib.request.Request(COMPOSE_URL, headers={"User-Agent": "pickmypostcode-setup"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            final = response.geturl()
            parsed = urllib.parse.urlparse(final)
            if parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com":
                raise SetupError(
                    "Refusing to install a Compose file that was redirected away from "
                    "raw.githubusercontent.com."
                )
            payload = response.read(MAX_COMPOSE_BYTES + 1)
    except SetupError:
        raise
    except Exception as error:
        raise SetupError(
            "Could not download the stock Compose file. Check the network and try again.\n"
            f"URL: {COMPOSE_URL}\n{error.__class__.__name__}: {error}"
        ) from error
    if len(payload) > MAX_COMPOSE_BYTES:
        raise SetupError("Downloaded Compose file is larger than expected. Not installing it.")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SetupError("Downloaded Compose file is not UTF-8. Not installing it.") from error
    validate_compose_text(text)
    return text


def make_staging(compose_text, answers, image_id):
    staging = Path(tempfile.mkdtemp(prefix="pmp-setup-"))
    try:
        os.chmod(staging, 0o700)
        logs = staging / LOG_DIR_NAME
        logs.mkdir(mode=0o700)
        os.chmod(logs, 0o700)
        text = compose_text
        if image_id:
            # Health and startup only. The file installed later stays the stock :latest template.
            old = "image: jonathanlangton1/pickmypostcode-auto-win-checker:latest"
            if text.count(old) != 1 or not SHA_IMAGE_RE.fullmatch(image_id):
                raise SetupError("Could not pin the check to the verified image. Nothing was changed.")
            text = text.replace(old, "image: " + image_id, 1)
        write_private(staging, COMPOSE_NAME, text.encode("utf-8"), 0o644)
        write_private(staging, ENV_NAME, render_env(answers).encode("utf-8"), 0o600)
        return staging
    except BaseException:
        discard_staging(staging)
        raise


def discard_staging(staging):
    if staging is None:
        return
    shutil.rmtree(staging, ignore_errors=True)


def write_private(directory, name, data, mode):
    destination = directory / name
    temporary = directory / f".{name}.tmp"
    if destination.is_symlink() or temporary.is_symlink():
        raise SetupError(f"Refusing to write through a symlink at {directory / name}.")
    descriptor = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        os.write(descriptor, data)
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(temporary, destination)
    except BaseException:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError:
                pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def marker_bytes():
    payload = {"managed_by": MARKER_OWNER, "version": 1}
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def promote_new(directory, staging, compose_text):
    """Install a complete new config, or leave the destination as it was."""
    if directory.is_symlink():
        raise SetupError(f"{directory} is a symlink. Nothing was installed.")
    compose_bytes = compose_text.encode("utf-8")
    env_bytes = (staging / ENV_NAME).read_bytes()
    if directory.exists():
        promote_into_existing(directory, compose_bytes, env_bytes)
        return
    parent = directory.parent
    bundle = Path(tempfile.mkdtemp(dir=str(parent), prefix=".pmp-new-"))
    renamed = False
    try:
        os.chmod(bundle, 0o700)
        fill_install(bundle, compose_bytes, env_bytes)
        os.rename(bundle, directory)
        renamed = True
    except OSError as error:
        raise SetupError(
            f"Could not write the install in {directory}: {error.strerror or error}."
        ) from error
    finally:
        if not renamed:
            shutil.rmtree(bundle, ignore_errors=True)


def promote_into_existing(directory, compose_bytes, env_bytes):
    if not directory.is_dir():
        raise SetupError(f"{directory} is not a directory. Nothing was installed.")
    names = {entry.name for entry in directory.iterdir() if entry.name not in IGNORED_NAMES}
    if names:
        raise SetupError(f"{directory} gained files during setup. Nothing further was written.")
    if (directory / LOG_DIR_NAME).exists() or (directory / LOG_DIR_NAME).is_symlink():
        raise SetupError(f"{directory / LOG_DIR_NAME} already exists. Refusing to replace history.")
    previous_mode = os.stat(directory).st_mode & 0o777
    created = []
    finished = False
    try:
        os.chmod(directory, 0o700)
        fill_install(directory, compose_bytes, env_bytes, created)
        finished = True
    except OSError as error:
        raise SetupError(
            f"Could not write the install in {directory}: {error.strerror or error}."
        ) from error
    finally:
        if not finished:
            remove_created(created)
            try:
                os.chmod(directory, previous_mode)
            except OSError:
                pass


def fill_install(directory, compose_bytes, env_bytes, created=None):
    logs = directory / LOG_DIR_NAME
    logs.mkdir(mode=0o700)
    if created is not None:
        created.append(logs)
    os.chmod(logs, 0o700)
    for name, data, mode in (
        (COMPOSE_NAME, compose_bytes, 0o644),
        (ENV_NAME, env_bytes, 0o600),
        (MARKER_NAME, marker_bytes(), 0o600),
    ):
        write_private(directory, name, data, mode)
        if created is not None:
            created.append(directory / name)


def remove_created(created):
    for path in reversed(created):
        try:
            if path.is_symlink():
                path.unlink()
            elif path.is_dir():
                os.rmdir(path)
            elif path.exists():
                path.unlink()
        except OSError:
            continue


def commit_rerun(directory, answers):
    rendered = render_env(answers).encode("utf-8")
    current = directory / ENV_NAME
    if current.is_symlink():
        raise SetupError(f"{current} is a symlink. The saved settings were not replaced.")
    if current.read_bytes() != rendered:
        write_private(directory, ENV_NAME, rendered, 0o600)
    os.chmod(directory, 0o700)
    os.chmod(current, 0o600)
    os.chmod(directory / MARKER_NAME, 0o600)


def health_project(staging, final_directory):
    final_project = compose_project_name(final_directory)
    project = HEALTH_PROJECT_PREFIX + secrets.token_hex(4)
    if project == final_project:
        project += "-tmp"
    return compose_command(staging, project)


def pull_image(staging, final_directory):
    base = health_project(staging, final_directory)
    config = run_capture(base + ["config", "--quiet"], cwd=staging)
    if config.returncode != 0:
        raise SetupError(
            "Docker Compose rejected the stock file. Nothing was started. "
            "The Compose output was not printed because it can include settings."
        )
    print("Pulling the checker image...", flush=True)
    return run_live(base + ["pull", SERVICE_NAME], cwd=staging) == 0


def published_image_id():
    """Image id of the tag just pulled. Later retags of :latest must not change this check."""
    reference = "jonathanlangton1/pickmypostcode-auto-win-checker:latest"
    code, image, _detail = inspect_format(reference, "{{.Id}}", kind="image")
    if code != 0 or not SHA_IMAGE_RE.fullmatch(image):
        raise SetupError(
            "The image was pulled, but its id could not be read, so it was not tested. "
            "Nothing was installed."
        )
    return image


def run_health(staging, final_directory):
    base = health_project(staging, final_directory)
    health_name = "pmp-health-" + secrets.token_hex(4)
    try:
        config = run_capture(base + ["config", "--quiet"], cwd=staging)
        if config.returncode != 0:
            raise SetupError(
                "Docker Compose rejected the stock file. Nothing was started. "
                "The Compose output was not printed because it can include settings."
            )
        print("Running the health check (sign-in, draws, and a test email)...", flush=True)
        code = run_live(
            base + [
                "run", "-T", "--rm", "--no-deps", "--name", health_name,
                SERVICE_NAME, "python", "run.py", "--test",
            ],
            cwd=staging,
        )
        return code == 0
    finally:
        # Remove the one-off project only. The name is not the install's project name.
        run_capture(base + ["down"], cwd=staging)


def start_and_report(directory, image_id):
    if not image_id or not SHA_IMAGE_RE.fullmatch(image_id):
        raise SetupError("No verified image id, so the checker was not started.")
    project = compose_project_name(directory)
    pin_handle, pin_name = tempfile.mkstemp(prefix="pmp-pin-", suffix=".yml")
    os.close(pin_handle)
    pin_path = Path(pin_name)
    try:
        pin_path.write_text(
            "services:\n  pickmypostcode-checker:\n    image: {}\n".format(image_id),
            encoding="utf-8",
        )
        os.chmod(pin_path, 0o600)
        command = [
            "docker", "compose",
            "--env-file", str(directory / ENV_NAME),
            "-f", str(directory / COMPOSE_NAME),
            "-f", str(pin_path),
            "--project-directory", str(directory),
            "-p", project,
            "up", "-d", "--no-deps", "--pull", "never", SERVICE_NAME,
        ]
        _progress["phase"] = "starting"
        code = run_live(command, cwd=directory)
    finally:
        try:
            pin_path.unlink()
        except OSError:
            pass
    if code != 0:
        print(
            "Not ready. Startup was not verified. "
            "The previous checker may still be running, or a new container may have started.\n"
            f"Directory: {directory}\n"
            f"Status: docker ps -a --filter name={CONTAINER_NAME}\n"
            f"Logs: docker logs {CONTAINER_NAME}\n"
            f"Stop: docker stop {CONTAINER_NAME}",
            file=sys.stderr,
        )
        return 1
    _progress["phase"] = "polling"
    status, logs = watch_scheduler()
    started, upcoming = scheduler_lines(logs)
    if status != "running" or not (started or upcoming):
        print("Not ready. The container is not running the scheduler.", file=sys.stderr)
        print(f"Container status: {status or 'missing'}", file=sys.stderr)
        if logs.strip():
            print(logs.rstrip(), file=sys.stderr)
        print(f"Directory: {directory}", file=sys.stderr)
        print(
            "The private settings are in that directory, but setup is not complete. "
            "Run this command again once Docker is healthy. A rerun does not pull or recreate "
            "the service before you confirm the health check.",
            file=sys.stderr,
        )
        return 1
    print("Ready.", flush=True)
    print(f"Directory: {directory}", flush=True)
    print(f"Logs: {directory / LOG_DIR_NAME}", flush=True)
    print(f"Container: {CONTAINER_NAME} is {status}.", flush=True)
    if started:
        print(started[-1], flush=True)
    if upcoming:
        print(upcoming[-1], flush=True)
    print(f"Test: docker exec -t {CONTAINER_NAME} python run.py --test", flush=True)
    print(f"Logs: docker logs {CONTAINER_NAME}", flush=True)
    print(f"Stop: docker stop {CONTAINER_NAME}", flush=True)
    print(f"Update: {UPGRADE_URL}", flush=True)
    return 0


def watch_scheduler():
    status = ""
    logs = ""
    for _ in range(POLL_ATTEMPTS):
        status = inspect_status()
        logs = container_logs()
        if status != "running":
            return status, logs
        started, upcoming = scheduler_lines(logs)
        if started or upcoming:
            return status, logs
        time.sleep(POLL_SECONDS)
    return status, logs


def scheduler_lines(logs):
    started = [line for line in logs.splitlines() if "Scheduler started" in line]
    upcoming = [
        line for line in logs.splitlines()
        if line.startswith("Next check at") or line.startswith("Retrying at")
    ]
    return started, upcoming


def compose_project_name(directory):
    """Match Compose's directory project name: ASCII lower, keep `_` and `-`, drop the rest."""
    cleaned = []
    for char in directory.name.lower():
        if ("a" <= char <= "z") or ("0" <= char <= "9") or char in "_-":
            cleaned.append(char)
    name = "".join(cleaned).lstrip("_-")
    if not name or not (("a" <= name[0] <= "z") or ("0" <= name[0] <= "9")):
        return ""
    return name


def compose_command(directory, project):
    return [
        "docker", "compose",
        "--env-file", str(directory / ENV_NAME),
        "-f", str(directory / COMPOSE_NAME),
        "--project-directory", str(directory),
        "-p", project,
    ]


def docker_env():
    """Drop every inherited COMPOSE_* setting and the app credentials."""
    env = {}
    for key, value in os.environ.items():
        if key.startswith("COMPOSE_") or key in ENV_KEYS:
            continue
        env[key] = value
    return env


def run_capture(args, cwd=None):
    try:
        return subprocess.run(
            args,
            cwd=cwd,
            env=docker_env(),
            stdin=subprocess.DEVNULL,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as error:
        raise SetupError("Docker was not found on PATH.\n" + install_advice()) from error


def run_live(args, cwd=None):
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            env=docker_env(),
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError as error:
        raise SetupError("Docker was not found on PATH.\n" + install_advice()) from error
    return completed.returncode


def inspect_working_dir():
    return inspect_format(CONTAINER_NAME, WORKDIR_TEMPLATE)


def inspect_format(container, template, kind="container"):
    command = ["docker", "inspect", "-f", template, container]
    if kind == "image":
        command = ["docker", "image", "inspect", "-f", template, container]
    completed = run_capture(command)
    detail = (completed.stderr or completed.stdout or "").strip()
    return completed.returncode, completed.stdout.strip(), detail


def inspect_status():
    completed = run_capture(["docker", "inspect", "-f", "{{.State.Status}}", CONTAINER_NAME])
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def container_logs():
    completed = run_capture(["docker", "logs", CONTAINER_NAME])
    if completed.returncode != 0:
        return completed.stdout or ""
    return completed.stdout or ""


if __name__ == "__main__":
    sys.exit(main())
