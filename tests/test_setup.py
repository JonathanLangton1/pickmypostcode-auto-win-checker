"""Public behavior of setup.py, with a fake docker binary and synthetic secrets."""

import json
import os
import pty
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

import setup


REPO = Path(__file__).resolve().parents[1]
SETUP = REPO / "setup.py"
SECRET = "pa's$w\"ord"
SPACED_APP_PASSWORD = "abcd efgh ijkl mnop"
COMPACT_APP_PASSWORD = "abcdefghijklmnop"
INHERITED_PASSWORD = "inherited-secret"
SCHEDULER_LOG = (
    "Scheduler started. Checking now, then daily at 09:01, 14:00, 18:01 and 21:01 UK time.\n"
    "Next check at Sat 03 Oct 21:01 BST.\n"
)

FAKE_DOCKER = r'''
import json, os, sys

LOG = os.environ["PMP_FAKE_DOCKER_LOG"]
STATE = os.environ["PMP_FAKE_STATE"]
WATCH = [
    "COMPOSE_FILE", "COMPOSE_PROJECT_NAME", "COMPOSE_PATH_SEPARATOR",
    "COMPOSE_PROFILES", "COMPOSE_ENV_FILES", "COMPOSE_PROJECT_DIRECTORY",
    "COMPOSE_REMOVE_ORPHANS",
    "EMAIL_PASSWORD", "PMP_EMAIL", "YOUR_POSTCODE", "EMAIL_ADDRESS",
    "NOTIFICATION_EMAIL_ADDRESS",
]
TAKES_VALUE = {"-f", "--project-directory", "-p", "--name", "--pull", "--env-file"}
KNOWN = {"version", "config", "pull", "run", "up", "down"}

def flag(args, name):
    if name in args:
        index = args.index(name)
        if index + 1 < len(args):
            return args[index + 1]
    return ""

def subcommand(args):
    if not args:
        return ""
    if args[0] != "compose":
        return args[0]
    index = 1
    while index < len(args):
        token = args[index]
        if token in TAKES_VALUE:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        if token in KNOWN:
            return token
        index += 1
    return ""

args = sys.argv[1:]
cmd = subcommand(args)
compose_files = []
index = 0
while index < len(args):
    if args[index] == "-f" and index + 1 < len(args):
        compose_files.append(args[index + 1])
        index += 2
        continue
    index += 1
container_line = ""
image_lines = []
for compose_path in compose_files:
    if os.path.isfile(compose_path):
        for line in open(compose_path, encoding="utf-8"):
            stripped = line.strip()
            if stripped.startswith("container_name:"):
                container_line = stripped
            if stripped.startswith("image:"):
                image_lines.append(stripped)
record = {
    "argv": args,
    "cmd": cmd,
    "cwd": os.getcwd(),
    "project": flag(args, "-p"),
    "project_directory": flag(args, "--project-directory"),
    "env_file": flag(args, "--env-file"),
    "name": flag(args, "--name"),
    "container_line": container_line,
    "image_line": " | ".join(image_lines),
    "env": {key: os.environ[key] for key in WATCH if key in os.environ},
}
with open(LOG, "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record) + "\n")

def fail(message, code=1):
    print(message, file=sys.stderr)
    raise SystemExit(code)

def read_state():
    if os.path.exists(STATE):
        return open(STATE, encoding="utf-8").read().strip()
    return ""

def write_state(value):
    with open(STATE, "w", encoding="utf-8") as handle:
        handle.write(value)

mode = os.environ.get("PMP_FAKE_MODE", "ok")
if cmd == "info":
    if mode == "denied":
        fail("permission denied while trying to connect to the Docker daemon socket")
    if mode == "down":
        fail("Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?")
    if mode == "broken":
        fail("docker info exploded")
    print("Server:\n Containers: 0")
    raise SystemExit(0)
if cmd == "version":
    if mode == "missing-compose":
        fail("docker: 'compose' is not a docker command")
    print("Docker Compose version " + os.environ.get("PMP_FAKE_COMPOSE_VERSION", "v2.32.4"))
    raise SystemExit(0)
if cmd == "ps":
    if os.environ.get("PMP_FAKE_PROJECT_DIR"):
        print("abc123project")
    raise SystemExit(0)
if cmd == "inspect":
    target = args[-1]
    fmt = flag(args, "-f")
    project_dir = os.environ.get("PMP_FAKE_PROJECT_DIR", "")
    if target != "pickmypostcode-checker":
        if not project_dir:
            fail("Error: No such object: " + target)
        if "working_dir" in fmt:
            print(project_dir)
        elif ".Image" in fmt:
            print(os.environ.get("PMP_FAKE_IMAGE", "sha256:" + ("b" * 64)))
        else:
            print("running")
        raise SystemExit(0)
    initial = os.environ.get("PMP_FAKE_CONTAINER", "absent")
    state = read_state()
    exists = initial == "present" or state in {"running", "exited", "restarting"}
    if not exists:
        fail("Error: No such object: " + target)
    workdir = os.environ.get("PMP_FAKE_WORKDIR", "")
    status = state or os.environ.get("PMP_FAKE_STATUS", "running")
    if "working_dir" in fmt:
        print(workdir)
    elif ".Image" in fmt:
        print(os.environ.get("PMP_FAKE_IMAGE", "sha256:" + ("a" * 64)))
    else:
        print(status)
    raise SystemExit(0)
if cmd == "image":
    seen = 0
    if os.path.exists(LOG):
        seen = open(LOG, encoding="utf-8").read().count('"cmd": "image"')
    if os.environ.get("PMP_FAKE_LATEST_MOVES") == "1" and seen > 1:
        print("sha256:" + ("d" * 64))
    else:
        print(os.environ.get("PMP_FAKE_PULL_ID", "sha256:" + ("c" * 64)))
    raise SystemExit(0)
if cmd == "logs":
    initial = os.environ.get("PMP_FAKE_CONTAINER", "absent")
    state = read_state()
    exists = initial == "present" or state in {"running", "exited", "restarting"}
    if not exists:
        fail("Error: No such container: " + args[-1])
    sys.stdout.write(os.environ.get("PMP_FAKE_LOGS", ""))
    raise SystemExit(0)
if cmd == "config":
    if os.environ.get("PMP_FAKE_CONFIG") == "fail":
        fail("EMAIL_PASSWORD=super-secret-line")
    raise SystemExit(0)
if cmd == "pull":
    if os.environ.get("PMP_FAKE_PULL") == "fail":
        fail("pull failed")
    print("Pulled checker image")
    raise SystemExit(0)
if cmd == "run":
    runs = 0
    if os.path.exists(LOG):
        runs = open(LOG, encoding="utf-8").read().count('"cmd": "run"')
    health = os.environ.get("PMP_FAKE_HEALTH", "ok")
    if health == "fail" or (health == "fail-once" and runs == 1):
        fail("Failed checks: email")
    print("All systems operational")
    raise SystemExit(0)
if cmd == "up":
    if os.environ.get("PMP_FAKE_UP") == "fail":
        fail("compose up failed")
    write_state(os.environ.get("PMP_FAKE_AFTER_UP", "running"))
    print("started")
    raise SystemExit(0)
if cmd == "down":
    raise SystemExit(0)
fail("unexpected docker argv: " + " ".join(args))
'''


def _events(log_path):
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _cmds(log_path):
    return [event["cmd"] for event in _events(log_path)]


class WizardResult:
    def __init__(self, code, transcript):
        self.code = code
        self.transcript = transcript


def run_wizard(args, env, replies, timeout=25):
    """Drive setup.py on a new controlling terminal. `replies` is (prompt, text or None for EOF)."""
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.execvpe(args[0], args, env)
        except Exception:
            os._exit(127)
    transcript = bytearray()
    position = 0
    deadline = time.monotonic() + timeout
    status = None
    try:
        for prompt, reply in replies:
            found = False
            while time.monotonic() < deadline:
                if prompt.encode() in transcript[position:]:
                    position = transcript.find(prompt.encode(), position) + len(prompt.encode())
                    found = True
                    break
                if not _pump(fd, transcript, 0.1):
                    waited, status = os.waitpid(pid, os.WNOHANG)
                    if waited:
                        _pump(fd, transcript, 0)
                        break
            if not found:
                raise AssertionError(
                    "missing prompt {!r}\n{}".format(prompt, transcript.decode(errors="replace"))
                )
            if reply is None:
                os.write(fd, b"\x04")
            else:
                os.write(fd, reply.encode() + b"\n")
        while time.monotonic() < deadline:
            _pump(fd, transcript, 0.05)
            waited, status = os.waitpid(pid, os.WNOHANG)
            if waited:
                _pump(fd, transcript, 0.05)
                break
        else:
            raise AssertionError("timed out\n" + transcript.decode(errors="replace"))
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        if status is None:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
            _, status = os.waitpid(pid, 0)
    if os.WIFEXITED(status):
        code = os.WEXITSTATUS(status)
    else:
        code = 128 + os.WTERMSIG(status)
    return WizardResult(code, transcript.decode(errors="replace"))


def _pump(fd, transcript, wait):
    readable, _, _ = select.select([fd], [], [], wait)
    if not readable:
        return False
    try:
        chunk = os.read(fd, 8192)
    except OSError:
        return False
    if not chunk:
        return False
    transcript.extend(chunk)
    return True


class SetupBehaviorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        docker = self.bin / "docker"
        docker.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(FAKE_DOCKER))
        docker.chmod(0o755)
        self.log = self.root / "docker-log.jsonl"
        self.state = self.root / "docker-state"
        self.directory = setup.resolve_directory(self.home / "pickmypostcode")

    def env(self, **extra):
        base = {
            "PATH": os.pathsep.join([str(self.bin), str(Path(sys.executable).parent), "/usr/bin", "/bin"]),
            "HOME": str(self.home),
            "TMPDIR": str(self.root),
            "TERM": "xterm-256color",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONUNBUFFERED": "1",
            "PMP_FAKE_DOCKER_LOG": str(self.log),
            "PMP_FAKE_STATE": str(self.state),
            "PMP_FAKE_LOGS": SCHEDULER_LOG,
        }
        base.update(extra)
        return base

    def wizard(self, replies, env=None, timeout=25):
        return run_wizard(
            [sys.executable, "-u", str(SETUP), "--directory", str(self.directory)],
            env or self.env(),
            replies,
            timeout=timeout,
        )

    def assert_private_install(self, password, postcode="SW1A 1AA"):
        env_path = self.directory / ".env"
        mode = stat.S_IMODE(env_path.stat().st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode) & 0o077, 0)
        text = env_path.read_text(encoding="utf-8")
        self.assertIn("YOUR_POSTCODE={}".format(json.dumps(postcode)), text)
        parsed = setup.parse_env(text)
        self.assertEqual(parsed["EMAIL_PASSWORD"], password)
        self.assertEqual(parsed["YOUR_POSTCODE"], postcode)
        self.assertNotIn("\n", parsed["EMAIL_PASSWORD"])
        for event in _events(self.log):
            blob = " ".join(event["argv"])
            self.assertNotIn(password, blob)
            self.assertEqual(event["env"], {})
        self.assertTrue((self.directory / "pickmypostcode_logs").is_dir())
        marker = json.loads((self.directory / ".pmp-setup.json").read_text(encoding="utf-8"))
        self.assertEqual(marker, {"managed_by": "pmp-setup", "version": 1})
        self.assertEqual((self.directory / "docker-compose.yml").read_text(encoding="utf-8"),
                         (REPO / "docker-compose.yml").read_text(encoding="utf-8"))

    def assert_no_secret_files(self, secret):
        for path in self.root.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            data = path.read_bytes()
            self.assertNotIn(secret.encode(), data, str(path))
            if path.name == ".env":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o077, 0)

    def test_help_lists_the_default_directory(self):
        result = subprocess.run(
            [sys.executable, str(SETUP), "--help"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("--directory", result.stdout)
        self.assertIn("pickmypostcode", result.stdout)

    def test_stock_compose_is_the_restart_policy_we_ship(self):
        text = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("restart: unless-stopped", text)
        self.assertNotIn("on-failure", text)
        setup.validate_compose_text(text)
        with self.assertRaises(setup.SetupError):
            setup.validate_compose_text((REPO / "docker-compose.dev.yml").read_text(encoding="utf-8"))
        ignored = (REPO / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn("setup.py", ignored)

    def test_new_install_keeps_a_literal_secret_and_only_then_starts(self):
        result = self.wizard(
            [
                ("Pick My Postcode account email:", "person@example.com"),
                ("UK postcode:", "nope"),
                ("UK postcode:", "sw1a1aa"),
                ("Gmail address that will send mail:", "sender@gmail.com"),
                ("Gmail app password:", SECRET),
                ("Address that should receive win emails", ""),
                ("Is the test email in the inbox?", "y"),
            ],
            env=self.env(
                COMPOSE_FILE="/evil/compose.yml",
                COMPOSE_PROJECT_NAME="evil-project",
                EMAIL_PASSWORD=INHERITED_PASSWORD,
                PMP_EMAIL="inherited@example.com",
                YOUR_POSTCODE="ZZ9 9ZZ",
                EMAIL_ADDRESS="inherited@gmail.com",
                NOTIFICATION_EMAIL_ADDRESS="inherited@example.com",
                COMPOSE_REMOVE_ORPHANS="1",
                PMP_FAKE_LATEST_MOVES="1",
            ),
        )
        self.assertEqual(result.code, 0, result.transcript)
        self.assertIn("Enter a UK postcode", result.transcript)
        self.assertIn(setup.GMAIL_2SV_URL, result.transcript)
        self.assertIn(setup.GMAIL_APP_PASSWORD_URL, result.transcript)
        self.assertNotIn(SECRET, result.transcript)
        self.assertNotIn(INHERITED_PASSWORD, result.transcript)
        self.assertIn("Ready.", result.transcript)
        self.assertIn(str(self.directory), result.transcript)
        self.assertIn(str(self.directory / "pickmypostcode_logs"), result.transcript)
        self.assertIn("Scheduler started", result.transcript)
        self.assertIn("Next check at Sat 03 Oct 21:01 BST.", result.transcript)
        self.assertIn(
            "Test: docker exec -t pickmypostcode-checker python run.py --test",
            result.transcript,
        )
        self.assertIn("Stop: docker stop pickmypostcode-checker", result.transcript)
        self.assertIn("Logs: docker logs pickmypostcode-checker", result.transcript)
        self.assertIn(setup.UPGRADE_URL, result.transcript)
        self.assert_private_install(SECRET)
        parsed = setup.parse_env((self.directory / ".env").read_text(encoding="utf-8"))
        self.assertEqual(parsed["PMP_EMAIL"], "person@example.com")
        self.assertEqual(parsed["EMAIL_ADDRESS"], "sender@gmail.com")
        self.assertEqual(parsed["NOTIFICATION_EMAIL_ADDRESS"], "person@example.com")
        self.assertNotEqual(parsed["YOUR_POSTCODE"], "ZZ9 9ZZ")
        line = [
            item for item in (self.directory / ".env").read_text(encoding="utf-8").splitlines()
            if item.startswith("EMAIL_PASSWORD=")
        ][0]
        self.assertEqual(line, "EMAIL_PASSWORD=" + json.dumps(SECRET.replace("$", "$$")))
        for event in _events(self.log):
            self.assertNotIn("--remove-orphans", event["argv"])
            if event["cmd"] in {"config", "pull", "run", "down", "up"}:
                self.assertTrue(event["env_file"].endswith(".env"), event["argv"])
        health_env = [event["env_file"] for event in _events(self.log) if event["cmd"] == "run"]
        self.assertIn("pmp-setup-", health_env[0])
        commands = _cmds(self.log)
        self.assertLess(commands.index("pull"), commands.index("run"))
        self.assertLess(commands.index("run"), commands.index("up"))
        ups = [event for event in _events(self.log) if event["cmd"] == "up"]
        self.assertEqual(len(ups), 1)
        self.assertEqual(ups[0]["project_directory"], str(self.directory))
        self.assertEqual(ups[0]["project"], "pickmypostcode")
        self.assertEqual(ups[0]["env_file"], str(self.directory / ".env"))
        self.assertIn("--no-deps", ups[0]["argv"])
        self.assertNotIn("--no-recreate", ups[0]["argv"])
        self.assertIn("never", ups[0]["argv"])
        self.assertEqual(ups[0]["argv"][-1], "pickmypostcode-checker")
        pulled = "image: sha256:" + ("c" * 64)
        self.assertEqual(
            [event for event in _events(self.log) if event["cmd"] == "run"][0]["image_line"],
            pulled,
        )
        self.assertIn(pulled, ups[0]["image_line"])
        self.assertNotIn("sha256:" + ("d" * 64), ups[0]["image_line"])
        self.assertIn(":latest", ups[0]["image_line"])
        self.assertEqual(_cmds(self.log).count("image"), 1)
        self.assertNotIn("/evil/compose.yml", ups[0]["argv"])
        health = [event for event in _events(self.log) if event["cmd"] in {"pull", "run", "config", "down"}]
        for event in health:
            self.assertNotEqual(event["project_directory"], str(self.directory))
            self.assertTrue(event["project"].startswith("pmp-health-"))
            self.assertIn("pmp-setup-", event["project_directory"])
        runs = [event for event in _events(self.log) if event["cmd"] == "run"]
        self.assertEqual(len(runs), 1)
        self.assertIn("-T", runs[0]["argv"])
        self.assertIn("--rm", runs[0]["argv"])
        self.assertIn("--no-deps", runs[0]["argv"])
        self.assertTrue(runs[0]["name"].startswith("pmp-health-"))
        self.assertNotEqual(runs[0]["name"], "pickmypostcode-checker")
        self.assertEqual(runs[0]["container_line"], "container_name: pickmypostcode-checker")
        self.assertNotIn("account password:", result.transcript.lower())

    def test_spaced_app_password_is_stored_without_spaces(self):
        result = self.wizard([
            ("Pick My Postcode account email:", "person@gmail.com"),
            ("UK postcode:", "ec1a1bb"),
            ("Gmail address that will send mail", ""),
            ("Gmail app password:", SPACED_APP_PASSWORD),
            ("Address that should receive win emails", ""),
            ("Is the test email in the inbox?", "y"),
        ])
        self.assertEqual(result.code, 0, result.transcript)
        self.assertNotIn(SPACED_APP_PASSWORD, result.transcript)
        parsed = setup.parse_env((self.directory / ".env").read_text(encoding="utf-8"))
        self.assertEqual(parsed["EMAIL_PASSWORD"], COMPACT_APP_PASSWORD)
        self.assertEqual(parsed["YOUR_POSTCODE"], "EC1A 1BB")
        self.assertEqual(parsed["EMAIL_ADDRESS"], "person@gmail.com")

    def test_failed_health_and_unconfirmed_inbox_do_not_start(self):
        failed = self.wizard(
            [
                ("Pick My Postcode account email:", "person@example.com"),
                ("UK postcode:", "SW1A 1AA"),
                ("Gmail address that will send mail:", "sender@gmail.com"),
                ("Gmail app password:", SECRET),
                ("Address that should receive win emails", ""),
                ("Retry the health check with the same answers?", "n"),
                ("Edit the details and retry?", "n"),
            ],
            env=self.env(PMP_FAKE_HEALTH="fail"),
        )
        self.assertNotEqual(failed.code, 0)
        self.assertNotIn("Ready.", failed.transcript)
        self.assertNotIn(SECRET, failed.transcript)
        self.assertNotIn("up", _cmds(self.log))
        self.assertFalse(self.directory.exists())
        self.assert_no_secret_files(SECRET)

        self.log.write_text("")
        if self.state.exists():
            self.state.unlink()
        declined = self.wizard([
            ("Pick My Postcode account email:", "person@example.com"),
            ("UK postcode:", "SW1A 1AA"),
            ("Gmail address that will send mail:", "sender@gmail.com"),
            ("Gmail app password:", SECRET),
            ("Address that should receive win emails", ""),
            ("Is the test email in the inbox?", "n"),
        ])
        self.assertNotEqual(declined.code, 0)
        self.assertIn("not confirmed", declined.transcript)
        self.assertNotIn("Ready.", declined.transcript)
        self.assertNotIn("up", _cmds(self.log))
        self.assertFalse(self.directory.exists())
        self.assert_no_secret_files(SECRET)

    def test_health_can_be_retried_without_retyping_valid_fields(self):
        result = self.wizard(
            [
                ("Pick My Postcode account email:", "person@example.com"),
                ("UK postcode:", "G1 1AA"),
                ("Gmail address that will send mail:", "sender@gmail.com"),
                ("Gmail app password:", SECRET),
                ("Address that should receive win emails", ""),
                ("Retry the health check with the same answers?", "y"),
                ("Is the test email in the inbox?", "y"),
            ],
            env=self.env(PMP_FAKE_HEALTH="fail-once"),
        )
        self.assertEqual(result.code, 0, result.transcript)
        self.assertEqual(_cmds(self.log).count("run"), 2)
        self.assertEqual(_cmds(self.log).count("up"), 1)
        self.assertEqual(setup.parse_env((self.directory / ".env").read_text(encoding="utf-8"))["YOUR_POSTCODE"], "G1 1AA")
        self.assertEqual(result.transcript.count("Pick My Postcode account email:"), 1)

    def test_eof_does_not_echo_a_password_or_leave_a_config(self):
        cancelled = self.wizard([
            ("Pick My Postcode account email:", "person@example.com"),
            ("UK postcode:", "SW1A 1AA"),
            ("Gmail address that will send mail:", "sender@gmail.com"),
            ("Gmail app password:", None),
        ])
        self.assertNotEqual(cancelled.code, 0)
        self.assertIn("cancelled", cancelled.transcript.lower())
        self.assertNotIn("Ready.", cancelled.transcript)
        self.assertFalse((self.root / ".env").exists())
        self.assert_no_secret_files(SECRET)

        self.log.write_text("")
        typed = self.wizard([
            ("Pick My Postcode account email:", "person@example.com"),
            ("UK postcode:", "SW1A 1AA"),
            ("Gmail address that will send mail:", "sender@gmail.com"),
            ("Gmail app password:", SECRET),
            ("Address that should receive win emails", None),
        ])
        self.assertNotEqual(typed.code, 0)
        self.assertNotIn(SECRET, typed.transcript)
        self.assertNotIn("up", _cmds(self.log))
        self.assertFalse(self.directory.exists())
        self.assert_no_secret_files(SECRET)

    def test_redirected_input_stops_before_docker_or_a_password(self):
        result = subprocess.run(
            [sys.executable, "-u", str(SETUP), "--directory", str(self.directory)],
            input=b"person@example.com\nsecret-from-pipe\n",
            capture_output=True,
            env=self.env(),
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b"interactive terminal", result.stderr)
        self.assertNotIn(b"secret-from-pipe", result.stdout + result.stderr)
        self.assertFalse(self.log.exists())
        self.assertFalse(self.directory.exists())

    def test_missing_docker_compose_and_daemon_are_actionable(self):
        empty_bin = self.root / "empty-bin"
        empty_bin.mkdir()
        missing = run_wizard(
            [sys.executable, "-u", str(SETUP), "--directory", str(self.directory)],
            self.env(PATH=str(empty_bin)),
            [],
        )
        self.assertNotEqual(missing.code, 0)
        self.assertIn("Docker was not found", missing.transcript)
        if sys.platform == "darwin":
            self.assertIn(setup.MAC_DOCKER_URL, missing.transcript)
        else:
            self.assertIn(setup.LINUX_DOCKER_URL, missing.transcript)
            self.assertIn(setup.DEBIAN_DOCKER_URL, missing.transcript)
        self.assertFalse(self.directory.exists())

        denied = self.wizard([], env=self.env(PMP_FAKE_MODE="denied"))
        self.assertNotEqual(denied.code, 0)
        self.assertIn("Do not run this setup with sudo", denied.transcript)
        self.assertIn(setup.DOCKER_POSTINSTALL_URL, denied.transcript)
        self.assertNotIn("up", _cmds(self.log))

        self.log.write_text("")
        down = self.wizard([], env=self.env(PMP_FAKE_MODE="down"))
        self.assertNotEqual(down.code, 0)
        self.assertIn("daemon is not running", down.transcript)
        if sys.platform == "darwin":
            self.assertIn("Docker Desktop", down.transcript)
        else:
            self.assertIn("systemctl", down.transcript)
        self.assertIn("Do not run the setup itself with sudo", down.transcript)

        self.log.write_text("")
        compose = self.wizard([], env=self.env(PMP_FAKE_MODE="missing-compose"))
        self.assertNotEqual(compose.code, 0)
        self.assertIn(setup.COMPOSE_INSTALL_URL, compose.transcript)
        self.assertNotIn("up", _cmds(self.log))

    def test_unsupported_arm_and_root_and_download_are_refused(self):
        with self.assertRaises(setup.SetupError) as caught:
            setup.ensure_architecture("armv7l")
        self.assertIn("32-bit", str(caught.exception))
        self.assertIn(setup.DEBIAN_DOCKER_URL, str(caught.exception))
        setup.ensure_architecture("x86_64")
        setup.ensure_architecture("aarch64")
        setup.ensure_architecture("arm64")
        with self.assertRaises(setup.SetupError):
            setup.ensure_architecture("i686")
        with mock.patch("setup.os.geteuid", return_value=0):
            with self.assertRaises(setup.SetupError) as caught:
                setup.ensure_not_root()
        self.assertIn("sudo", str(caught.exception))
        self.assertIn(setup.DOCKER_POSTINSTALL_URL, str(caught.exception))
        with mock.patch.object(setup, "host_kind", return_value="raspberry-pi"):
            self.assertIn(setup.DEBIAN_DOCKER_URL, setup.install_advice())

        class Response:
            def __init__(self, url, payload):
                self._url = url
                self._payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def geturl(self):
                return self._url

            def read(self, limit):
                return self._payload[:limit]

        good = (REPO / "docker-compose.yml").read_bytes()
        with mock.patch.object(setup.urllib.request, "urlopen", return_value=Response(setup.COMPOSE_URL, good)):
            self.assertEqual(setup.download_compose_text(), good.decode("utf-8"))
        with mock.patch.object(
            setup.urllib.request, "urlopen",
            return_value=Response("http://evil.example/docker-compose.yml", good),
        ):
            with self.assertRaises(setup.SetupError) as caught:
                setup.download_compose_text()
        self.assertIn("redirected", str(caught.exception))
        with mock.patch.object(
            setup.urllib.request, "urlopen",
            return_value=Response(setup.COMPOSE_URL, b"x" * (setup.MAX_COMPOSE_BYTES + 1)),
        ):
            with self.assertRaises(setup.SetupError):
                setup.download_compose_text()
        with mock.patch.object(
            setup.urllib.request, "urlopen",
            return_value=Response(setup.COMPOSE_URL, b"services:\n  other: {}\n"),
        ):
            with self.assertRaises(setup.SetupError):
                setup.download_compose_text()

    def test_bad_compose_beside_the_script_is_not_installed(self):
        folder = self.root / "standalone"
        folder.mkdir()
        shutil.copy(SETUP, folder / "setup.py")
        (folder / "docker-compose.yml").write_text("services:\n  other:\n    image: evil:latest\n", encoding="utf-8")
        result = run_wizard(
            [sys.executable, "-u", str(folder / "setup.py"), "--directory", str(self.directory)],
            self.env(),
            [],
        )
        self.assertNotEqual(result.code, 0)
        self.assertIn("not the stock template", result.transcript)
        self.assertNotIn("Gmail app password:", result.transcript)
        self.assertFalse(self.directory.exists())
        self.assertNotIn("pull", _cmds(self.log))

    def test_rerun_reuses_a_managed_install_without_pulling_or_touching_history(self):
        self._write_managed()
        history = self.directory / "pickmypostcode_logs" / "pastData.json"
        before = {
            "history": history.read_bytes(),
            "compose": (self.directory / "docker-compose.yml").read_bytes(),
            "env": (self.directory / ".env").read_bytes(),
        }
        result = self.wizard(
            [
                ("Run the health check with these settings?", ""),
                ("Is the test email in the inbox?", "y"),
            ],
            env=self.env(
                PMP_FAKE_CONTAINER="present",
                PMP_FAKE_WORKDIR=str(self.directory),
                COMPOSE_FILE="/evil/compose.yml",
                EMAIL_PASSWORD=INHERITED_PASSWORD,
            ),
        )
        self.assertEqual(result.code, 0, result.transcript)
        self.assertNotIn("stored$secret", result.transcript)
        self.assertNotIn(INHERITED_PASSWORD, result.transcript)
        self.assertIn("Ready.", result.transcript)
        self.assertEqual(history.read_bytes(), before["history"])
        self.assertEqual((self.directory / "docker-compose.yml").read_bytes(), before["compose"])
        self.assertEqual((self.directory / ".env").read_bytes(), before["env"])
        self.assertNotIn("pull", _cmds(self.log))
        ups = [event for event in _events(self.log) if event["cmd"] == "up"]
        self.assertEqual(len(ups), 1)
        run_at = _cmds(self.log).index("run")
        up_at = _cmds(self.log).index("up")
        self.assertLess(run_at, up_at)
        self.assertIn("--pull", ups[0]["argv"])
        self.assertIn("never", ups[0]["argv"])
        self.assertIn("--no-deps", ups[0]["argv"])
        self.assertNotIn("--no-recreate", ups[0]["argv"])
        self.assertNotIn("--force-recreate", ups[0]["argv"])
        self.assertEqual(ups[0]["argv"][-1], "pickmypostcode-checker")
        pinned = "image: sha256:" + ("a" * 64)
        runs = [event for event in _events(self.log) if event["cmd"] == "run"]
        self.assertEqual(runs[0]["image_line"], pinned)
        self.assertIn(pinned, ups[0]["image_line"])
        self.assertIn(":latest", ups[0]["image_line"])
        self.assertNotIn("image", _cmds(self.log))
        self.assertNotIn("--remove-orphans", " ".join(ups[0]["argv"]))

    def test_failed_rerun_leaves_the_managed_install_untouched(self):
        self._write_managed()
        before = self._snapshot()
        result = self.wizard(
            [
                ("Run the health check with these settings?", "y"),
                ("Retry the health check with the same answers?", "n"),
                ("Edit the details and retry?", "n"),
            ],
            env=self.env(
                PMP_FAKE_CONTAINER="present",
                PMP_FAKE_WORKDIR=str(self.directory),
                PMP_FAKE_HEALTH="fail",
            ),
        )
        self.assertNotEqual(result.code, 0)
        self.assertNotIn("Ready.", result.transcript)
        self.assertIn("was not changed and was not restarted", result.transcript)
        self.assertNotIn("up", _cmds(self.log))
        self.assertNotIn("pull", _cmds(self.log))
        self.assertEqual(self._snapshot(), before)

    def test_custom_shared_and_edited_installs_are_refused(self):
        self.directory.mkdir()
        compose = self.directory / "docker-compose.yml"
        original_compose = (
            "services:\n  pickmypostcode-checker:\n    image: example/custom:1\n  other:\n    image: example/db:1\n"
        )
        compose.write_text(original_compose, encoding="utf-8")
        env_path = self.directory / ".env"
        env_path.write_text("CUSTOM_SECRET=keep-me\n", encoding="utf-8")
        result = self.wizard([])
        self.assertNotEqual(result.code, 0)
        self.assertIn(setup.UPGRADE_URL, result.transcript)
        self.assertIn("does not manage", result.transcript)
        self.assertEqual(compose.read_text(encoding="utf-8"), original_compose)
        self.assertEqual(env_path.read_text(encoding="utf-8"), "CUSTOM_SECRET=keep-me\n")
        self.assertNotIn("keep-me", result.transcript)
        self.assertNotIn("pull", _cmds(self.log))
        self.assertNotIn("up", _cmds(self.log))

        shutil.rmtree(self.directory)
        self._write_managed()
        edited = (self.directory / "docker-compose.yml").read_text(encoding="utf-8").replace(
            "restart: unless-stopped", "restart: on-failure:3"
        )
        (self.directory / "docker-compose.yml").write_text(edited, encoding="utf-8")
        before = self._snapshot()
        self.log.write_text("")
        refused = self.wizard([])
        self.assertNotEqual(refused.code, 0)
        self.assertIn("were changed", refused.transcript)
        self.assertIn("downgrade", refused.transcript)
        self.assertIn(setup.UPGRADE_URL, refused.transcript)
        self.assertEqual(self._snapshot(), before)
        self.assertNotIn("pull", _cmds(self.log))
        self.assertNotIn("run", _cmds(self.log))

    def test_symlink_and_container_name_conflicts_refuse_before_writing(self):
        target = self.root / "outside.env"
        target.write_text("OUTSIDE-SECRET=1\n", encoding="utf-8")
        self.directory.mkdir()
        (self.directory / ".env").symlink_to(target)
        refused = self.wizard([])
        self.assertNotEqual(refused.code, 0)
        self.assertIn("symlink", refused.transcript)
        self.assertEqual(target.read_text(encoding="utf-8"), "OUTSIDE-SECRET=1\n")
        self.assertNotIn("OUTSIDE-SECRET", refused.transcript)
        self.assertFalse((self.directory / ".pmp-setup.json").exists())

        real = self.root / "real-install"
        real.mkdir()
        (real / "keep.txt").write_text("KEEP", encoding="utf-8")
        link = self.root / "linked-install"
        link.symlink_to(real)
        linked = run_wizard(
            [sys.executable, "-u", str(SETUP), "--directory", str(link)],
            self.env(),
            [],
        )
        self.assertNotEqual(linked.code, 0)
        self.assertIn("symlink", linked.transcript)
        self.assertEqual((real / "keep.txt").read_text(encoding="utf-8"), "KEEP")

        self.log.write_text("")
        shutil.rmtree(self.directory)
        conflict = self.wizard([], env=self.env(PMP_FAKE_CONTAINER="present", PMP_FAKE_WORKDIR="/foreign/install"))
        self.assertNotEqual(conflict.code, 0)
        self.assertIn("pickmypostcode-checker", conflict.transcript)
        self.assertIn(setup.UPGRADE_URL, conflict.transcript)
        self.assertFalse(self.directory.exists())
        self.assertNotIn("pull", _cmds(self.log))
        self.assertNotIn("up", _cmds(self.log))

    def test_partial_start_is_not_reported_ready(self):
        answers = [
            ("Pick My Postcode account email:", "person@example.com"),
            ("UK postcode:", "SW1A 1AA"),
            ("Gmail address that will send mail:", "sender@gmail.com"),
            ("Gmail app password:", SECRET),
            ("Address that should receive win emails", ""),
            ("Is the test email in the inbox?", "y"),
        ]
        failed_up = self.wizard(answers, env=self.env(PMP_FAKE_UP="fail"))
        self.assertNotEqual(failed_up.code, 0)
        self.assertNotIn("Ready.", failed_up.transcript)
        self.assertIn("Not ready.", failed_up.transcript)
        self.assertIn("Startup was not verified", failed_up.transcript)
        self.assertNotIn("not a running checker", failed_up.transcript)
        self.assertIn("docker ps -a --filter name=pickmypostcode-checker", failed_up.transcript)
        self.assertIn("docker stop pickmypostcode-checker", failed_up.transcript)
        self.assertTrue((self.directory / ".env").is_file())
        self.assertEqual(stat.S_IMODE((self.directory / ".env").stat().st_mode), 0o600)

        shutil.rmtree(self.directory)
        self.log.write_text("")
        if self.state.exists():
            self.state.unlink()
        exited = self.wizard(answers, env=self.env(PMP_FAKE_AFTER_UP="exited", PMP_FAKE_LOGS="checker exited\n"))
        self.assertNotEqual(exited.code, 0)
        self.assertNotIn("Ready.", exited.transcript)
        self.assertIn("Not ready.", exited.transcript)
        self.assertIn("exited", exited.transcript)

        shutil.rmtree(self.directory)
        self.log.write_text("")
        if self.state.exists():
            self.state.unlink()
        quiet = self.wizard(
            answers,
            env=self.env(PMP_FAKE_AFTER_UP="running", PMP_FAKE_LOGS=""),
            timeout=20,
        )
        self.assertNotEqual(quiet.code, 0)
        self.assertNotIn("Ready.", quiet.transcript)
        self.assertIn("Not ready.", quiet.transcript)

    def test_dotenv_round_trip_keeps_shell_characters_literal(self):
        values = {
            "NOTIFICATION_EMAIL_ADDRESS": "person@example.com",
            "YOUR_POSTCODE": "SW1A 1AA",
            "PMP_EMAIL": "person@example.com",
            "EMAIL_ADDRESS": "sender@gmail.com",
            "EMAIL_PASSWORD": SECRET,
        }
        rendered = setup.render_env(values)
        self.assertEqual(
            [line for line in rendered.splitlines() if line.startswith("EMAIL_PASSWORD=")][0],
            "EMAIL_PASSWORD=" + json.dumps(SECRET.replace("$", "$$")),
        )
        self.assertEqual(setup.parse_env(rendered), values)
        unicode_password = 'pä"ss$wörd'
        values["EMAIL_PASSWORD"] = unicode_password
        unicode_rendered = setup.render_env(values)
        unicode_bytes = unicode_rendered.encode("utf-8")
        self.assertIn("pä".encode("utf-8"), unicode_bytes)
        self.assertNotIn(b"\\u00e4", unicode_bytes)
        self.assertNotIn(b"\\u00f6", unicode_bytes)
        self.assertEqual(
            setup.parse_env(unicode_rendered)["EMAIL_PASSWORD"], unicode_password
        )
        for password in [
            SECRET, "$HOME", "$$", "a\\b", "pre\\'post", "it's", "'",
            'quote"mark', "`touch`", 'say "hi"\\', "end\\", "pässwörd-€",
        ]:
            values["EMAIL_PASSWORD"] = password
            self.assertEqual(setup.parse_env(setup.render_env(values))["EMAIL_PASSWORD"], password)
        with self.assertRaises(setup.SetupError):
            setup.encode_env_value("line\nbreak")
        leaked = 'secret"line'
        with self.assertRaises(ValueError) as caught:
            setup.parse_env("EMAIL_PASSWORD=" + leaked + "\n")
        self.assertNotIn(leaked, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertNotIn(leaked, str(caught.exception.__context__))
        with self.assertRaises(ValueError):
            setup.normalize_password("abcd\nefgh")
        with self.assertRaises(ValueError):
            setup.parse_postcode("SW1A\n1AA")
        self.assertEqual(setup.normalize_password(SPACED_APP_PASSWORD), COMPACT_APP_PASSWORD)
        self.assertEqual(setup.parse_postcode("sw1a  1aa"), "SW1A 1AA")

    def test_old_compose_is_refused_before_any_install(self):
        old = self.wizard([], env=self.env(PMP_FAKE_COMPOSE_VERSION="v2.23.5"))
        self.assertNotEqual(old.code, 0)
        self.assertIn("2.24", old.transcript)
        self.assertIn(setup.COMPOSE_INSTALL_URL, old.transcript)
        self.assertFalse(self.directory.exists())
        self.assertNotIn("pull", _cmds(self.log))
        self.assertNotIn("up", _cmds(self.log))
        self.log.write_text("")
        unknown = self.wizard([], env=self.env(PMP_FAKE_COMPOSE_VERSION="not-a-version"))
        self.assertNotEqual(unknown.code, 0)
        self.assertIn("2.24", unknown.transcript)
        self.assertEqual(setup.parse_compose_version("Docker Compose version v5.1.2"), (5, 1, 2))

    def test_foreign_project_is_refused_without_the_named_container(self):
        result = self.wizard([], env=self.env(PMP_FAKE_PROJECT_DIR="/foreign/install"))
        self.assertNotEqual(result.code, 0)
        self.assertIn("already belongs", result.transcript)
        self.assertIn("/foreign/install", result.transcript)
        self.assertFalse(self.directory.exists())
        self.assertNotIn("pull", _cmds(self.log))
        self.assertNotIn("up", _cmds(self.log))

    def test_edit_keeps_password_and_notification_inbox(self):
        result = self.wizard(
            [
                ("Pick My Postcode account email:", "person@example.com"),
                ("UK postcode:", "SW1A 1AA"),
                ("Gmail address that will send mail:", "sender@gmail.com"),
                ("Gmail app password:", SECRET),
                ("Address that should receive win emails", "inbox@example.com"),
                ("Retry the health check with the same answers?", "n"),
                ("Edit the details and retry?", "y"),
                ("Pick My Postcode account email [person@example.com]:", ""),
                ("UK postcode [SW1A 1AA]:", "ec1a1bb"),
                ("Gmail address that will send mail [sender@gmail.com]:", ""),
                ("Gmail app password:", ""),
                ("Address that should receive win emails [inbox@example.com]:", ""),
                ("Is the test email in the inbox?", "y"),
            ],
            env=self.env(PMP_FAKE_HEALTH="fail-once"),
        )
        self.assertEqual(result.code, 0, result.transcript)
        self.assertIn("Press Enter to keep the saved app password.", result.transcript)
        parsed = setup.parse_env((self.directory / ".env").read_text(encoding="utf-8"))
        self.assertEqual(parsed["YOUR_POSTCODE"], "EC1A 1BB")
        self.assertEqual(parsed["EMAIL_PASSWORD"], SECRET)
        self.assertEqual(parsed["NOTIFICATION_EMAIL_ADDRESS"], "inbox@example.com")
        self.assertEqual(parsed["PMP_EMAIL"], "person@example.com")

    def test_changed_rerun_recreates_the_same_image_after_confirmation(self):
        self._write_managed(notification="inbox@example.com")
        history = (self.directory / "pickmypostcode_logs" / "pastData.json").read_bytes()
        compose = (self.directory / "docker-compose.yml").read_bytes()
        result = self.wizard(
            [
                ("Run the health check with these settings?", "n"),
                ("Pick My Postcode account email [person@example.com]:", "new@example.com"),
                ("UK postcode [SW1A 1AA]:", ""),
                ("Gmail address that will send mail [sender@gmail.com]:", ""),
                ("Gmail app password:", ""),
                ("Address that should receive win emails [inbox@example.com]:", ""),
                ("Is the test email in the inbox?", "y"),
            ],
            env=self.env(
                PMP_FAKE_CONTAINER="present",
                PMP_FAKE_WORKDIR=str(self.directory),
            ),
        )
        self.assertEqual(result.code, 0, result.transcript)
        self.assertNotIn("stored$secret", result.transcript)
        parsed = setup.parse_env((self.directory / ".env").read_text(encoding="utf-8"))
        self.assertEqual(parsed["PMP_EMAIL"], "new@example.com")
        self.assertEqual(parsed["EMAIL_PASSWORD"], "stored$secret")
        self.assertEqual(parsed["NOTIFICATION_EMAIL_ADDRESS"], "inbox@example.com")
        self.assertEqual((self.directory / "docker-compose.yml").read_bytes(), compose)
        self.assertEqual((self.directory / "pickmypostcode_logs" / "pastData.json").read_bytes(), history)
        self.assertNotIn("pull", _cmds(self.log))
        pinned = "image: sha256:" + ("a" * 64)
        runs = [event for event in _events(self.log) if event["cmd"] == "run"]
        ups = [event for event in _events(self.log) if event["cmd"] == "up"]
        self.assertEqual(runs[0]["image_line"], pinned)
        self.assertLess(_cmds(self.log).index("run"), _cmds(self.log).index("up"))
        self.assertIn("--no-deps", ups[0]["argv"])
        self.assertNotIn("--no-recreate", ups[0]["argv"])
        self.assertNotIn("--force-recreate", ups[0]["argv"])
        self.assertEqual(ups[0]["argv"][-1], "pickmypostcode-checker")
        self.assertIn("never", ups[0]["argv"])
        self.assertIn(pinned, ups[0]["image_line"])
        self.assertIn(":latest", ups[0]["image_line"])
        self.assertFalse(list(self.root.glob("pmp-pin-*")))
        self.assertFalse(list(self.directory.glob("pmp-pin-*")))

    def test_failed_up_then_retry_checks_the_saved_settings_on_the_old_image(self):
        self._write_managed(notification="inbox@example.com")
        history = (self.directory / "pickmypostcode_logs" / "pastData.json").read_bytes()
        first = self.wizard(
            [
                ("Run the health check with these settings?", "n"),
                ("Pick My Postcode account email [person@example.com]:", "new@example.com"),
                ("UK postcode [SW1A 1AA]:", ""),
                ("Gmail address that will send mail [sender@gmail.com]:", ""),
                ("Gmail app password:", ""),
                ("Address that should receive win emails [inbox@example.com]:", ""),
                ("Is the test email in the inbox?", "y"),
            ],
            env=self.env(
                PMP_FAKE_CONTAINER="present",
                PMP_FAKE_WORKDIR=str(self.directory),
                PMP_FAKE_UP="fail",
                PMP_FAKE_LATEST_MOVES="1",
            ),
        )
        self.assertNotEqual(first.code, 0)
        self.assertIn("Startup was not verified", first.transcript)
        self.assertNotIn("Ready.", first.transcript)
        saved = setup.parse_env((self.directory / ".env").read_text(encoding="utf-8"))
        self.assertEqual(saved["PMP_EMAIL"], "new@example.com")
        self.assertEqual(saved["EMAIL_PASSWORD"], "stored$secret")
        pinned = "sha256:" + ("a" * 64)
        first_up = [event for event in _events(self.log) if event["cmd"] == "up"][0]
        self.assertIn("image: " + pinned, first_up["image_line"])
        self.assertNotIn("--no-recreate", first_up["argv"])

        self.log.write_text("")
        second = self.wizard(
            [
                ("Run the health check with these settings?", ""),
                ("Is the test email in the inbox?", "y"),
            ],
            env=self.env(
                PMP_FAKE_CONTAINER="present",
                PMP_FAKE_WORKDIR=str(self.directory),
                PMP_FAKE_LATEST_MOVES="1",
                PMP_FAKE_PULL_ID="sha256:" + ("d" * 64),
            ),
        )
        self.assertEqual(second.code, 0, second.transcript)
        self.assertEqual(
            setup.parse_env((self.directory / ".env").read_text(encoding="utf-8"))["PMP_EMAIL"],
            "new@example.com",
        )
        self.assertEqual((self.directory / "pickmypostcode_logs" / "pastData.json").read_bytes(), history)
        runs = [event for event in _events(self.log) if event["cmd"] == "run"]
        ups = [event for event in _events(self.log) if event["cmd"] == "up"]
        self.assertEqual(runs[0]["image_line"], "image: " + pinned)
        self.assertIn("image: " + pinned, ups[0]["image_line"])
        self.assertNotIn("sha256:" + ("d" * 64), ups[0]["image_line"])
        self.assertNotIn("sha256:" + ("c" * 64), ups[0]["image_line"])
        self.assertIn("--no-deps", ups[0]["argv"])
        self.assertNotIn("--no-recreate", ups[0]["argv"])
        self.assertNotIn("pull", _cmds(self.log))
        self.assertNotIn("image", _cmds(self.log))

    def test_failed_first_up_can_be_finished_without_a_container(self):
        answers = [
            ("Pick My Postcode account email:", "person@example.com"),
            ("UK postcode:", "SW1A 1AA"),
            ("Gmail address that will send mail:", "sender@gmail.com"),
            ("Gmail app password:", SECRET),
            ("Address that should receive win emails", ""),
            ("Is the test email in the inbox?", "y"),
        ]
        failed = self.wizard(answers, env=self.env(PMP_FAKE_UP="fail"))
        self.assertNotEqual(failed.code, 0)
        self.assertIn("Startup was not verified", failed.transcript)
        self.assertTrue((self.directory / ".pmp-setup.json").is_file())
        self.assertFalse(self.state.exists())
        history = self.directory / "pickmypostcode_logs" / "pastData.json"
        history.write_text('{"sentinel": true}\n', encoding="utf-8")
        compose = (self.directory / "docker-compose.yml").read_bytes()
        self.log.write_text("")
        if self.state.exists():
            self.state.unlink()
        finished = self.wizard(
            [
                ("Run the health check with these settings?", ""),
                ("Is the test email in the inbox?", "y"),
            ],
            env=self.env(PMP_FAKE_LATEST_MOVES="1"),
        )
        self.assertEqual(finished.code, 0, finished.transcript)
        self.assertIn("No checker container exists", finished.transcript)
        self.assertIn("current published image", finished.transcript)
        self.assertEqual(history.read_text(encoding="utf-8"), '{"sentinel": true}\n')
        self.assertEqual((self.directory / "docker-compose.yml").read_bytes(), compose)
        pinned = "image: sha256:" + ("c" * 64)
        commands = _cmds(self.log)
        self.assertLess(commands.index("pull"), commands.index("run"))
        self.assertLess(commands.index("run"), commands.index("up"))
        self.assertEqual(commands.count("image"), 1)
        runs = [event for event in _events(self.log) if event["cmd"] == "run"]
        ups = [event for event in _events(self.log) if event["cmd"] == "up"]
        self.assertEqual(runs[0]["image_line"], pinned)
        self.assertIn(pinned, ups[0]["image_line"])
        self.assertNotIn("sha256:" + ("d" * 64), ups[0]["image_line"])
        self.assertIn(":latest", ups[0]["image_line"])
        self.assertIn("--pull", ups[0]["argv"])
        self.assertIn("never", ups[0]["argv"])

    def test_incomplete_new_install_rolls_back(self):
        answers = {
            "NOTIFICATION_EMAIL_ADDRESS": "person@example.com",
            "YOUR_POSTCODE": "SW1A 1AA",
            "PMP_EMAIL": "person@example.com",
            "EMAIL_ADDRESS": "sender@gmail.com",
            "EMAIL_PASSWORD": SECRET,
        }
        compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
        staging = setup.make_staging(compose, answers, None)
        self.addCleanup(setup.discard_staging, staging)
        self.directory.mkdir()
        (self.directory / ".DS_Store").write_text("keep", encoding="utf-8")
        real_write = setup.write_private

        def boom(directory, name, data, mode):
            if name == setup.MARKER_NAME:
                raise OSError(28, "No space left on device")
            return real_write(directory, name, data, mode)

        with mock.patch.object(setup, "write_private", side_effect=boom):
            with self.assertRaises(setup.SetupError) as caught:
                setup.promote_new(self.directory, staging, compose)
        self.assertIn("No space left on device", str(caught.exception))
        self.assertFalse((self.directory / "docker-compose.yml").exists())
        self.assertFalse((self.directory / ".env").exists())
        self.assertFalse((self.directory / ".pmp-setup.json").exists())
        self.assertFalse((self.directory / "pickmypostcode_logs").exists())
        self.assertEqual((self.directory / ".DS_Store").read_text(encoding="utf-8"), "keep")

        missing = setup.resolve_directory(self.home / "fresh-install")
        with mock.patch.object(setup, "write_private", side_effect=boom):
            with self.assertRaises(setup.SetupError) as caught:
                setup.promote_new(missing, staging, compose)
        self.assertIn("No space left on device", str(caught.exception))
        self.assertFalse(missing.exists())
        self.assertEqual(list(missing.parent.glob(".pmp-new-*")), [])

        stderr = io_stderr = __import__("io").StringIO()
        with mock.patch.object(setup, "require_terminal"):
            with mock.patch.object(setup, "ensure_docker", side_effect=OSError(28, "No space left on device")):
                with mock.patch("sys.stderr", stderr):
                    code = setup.main(["--directory", str(setup.resolve_directory(self.home / "other-install"))])
        self.assertEqual(code, 1)
        self.assertIn("No space left on device", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

        folder = self.root / "empty-dest"
        folder.mkdir()
        os.chmod(folder, 0o755)
        (folder / ".DS_Store").write_text("keep", encoding="utf-8")
        calls = {"n": 0}
        real_fsync = os.fsync

        def flaky(fd):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError(28, "No space left on device")
            return real_fsync(fd)

        with mock.patch("setup.os.fsync", side_effect=flaky):
            with self.assertRaises(setup.SetupError) as caught:
                setup.promote_new(folder, staging, compose)
        self.assertIn("No space left on device", str(caught.exception))
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o755)
        self.assertEqual({path.name for path in folder.iterdir()}, {".DS_Store"})
        self.assertFalse((folder / "..env.tmp").exists())
        self.assertEqual(list(folder.glob("*.tmp")), [])

        def interrupt(directory, name, data, mode):
            if name == setup.MARKER_NAME:
                raise KeyboardInterrupt()
            return real_write(directory, name, data, mode)

        gone = setup.resolve_directory(self.home / "interrupt-install")
        with mock.patch.object(setup, "write_private", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                setup.promote_new(gone, staging, compose)
        self.assertFalse(gone.exists())
        self.assertEqual(list(gone.parent.glob(".pmp-new-*")), [])

        kept = self.root / "kept-empty"
        kept.mkdir()
        os.chmod(kept, 0o755)
        (kept / ".DS_Store").write_text("keep", encoding="utf-8")
        with mock.patch.object(setup, "write_private", side_effect=interrupt):
            with self.assertRaises(KeyboardInterrupt):
                setup.promote_new(kept, staging, compose)
        self.assertEqual(stat.S_IMODE(kept.stat().st_mode), 0o755)
        self.assertEqual({path.name for path in kept.iterdir()}, {".DS_Store"})

        def bad_env(directory, name, data, mode):
            if name == setup.ENV_NAME:
                raise OSError(28, "No space left on device")
            return real_write(directory, name, data, mode)

        before = set(Path(tempfile.gettempdir()).glob("pmp-setup-*"))
        with mock.patch.object(setup, "write_private", side_effect=bad_env):
            with self.assertRaises(OSError):
                setup.make_staging(compose, answers, None)
        self.assertEqual(set(Path(tempfile.gettempdir()).glob("pmp-setup-*")), before)

    def test_interrupt_status_matches_the_phase(self):
        original = dict(setup._progress)
        self.addCleanup(setup._progress.update, original)
        setup._progress.update(phase="polling", directory=self.directory, managed=False)
        polling = setup.interrupt_message()
        self.assertIn("may be running", polling)
        self.assertIn("docker ps -a --filter name=pickmypostcode-checker", polling)
        self.assertIn(" stop", polling)
        self.assertNotIn("No service was started", polling)
        setup._progress.update(phase="prepare", directory=self.directory, managed=True)
        managed = setup.interrupt_message()
        self.assertIn("not stopped", managed)
        self.assertNotIn("No service was started", managed)
        setup._progress.update(phase="prepare", directory=self.directory, managed=False)
        self.assertIn("No service was started", setup.interrupt_message())

    def test_project_name_matches_compose_basename_rules(self):
        self.assertEqual(setup.compose_project_name(Path("/x/pickmypostcode")), "pickmypostcode")
        self.assertEqual(setup.compose_project_name(Path("/x/My_Dir-1")), "my_dir-1")
        self.assertEqual(setup.compose_project_name(Path("/x/_-Ab C")), "abc")
        self.assertEqual(setup.compose_project_name(Path("/x/---")), "")
        self.assertEqual(setup.compose_project_name(Path("/x/日本語")), "")
        self.assertEqual(setup.compose_project_name(Path("/x") / ("A" * 80)), "a" * 80)
        with self.assertRaises(setup.SetupError) as caught:
            setup.require_project_name(Path("/tmp/日本語"))
        self.assertIn("--directory", str(caught.exception))

    def test_ancestor_symlink_is_the_same_directory(self):
        real_parent = self.root / "realparent"
        real_parent.mkdir()
        link_parent = self.root / "linkparent"
        link_parent.symlink_to(real_parent)
        resolved = setup.resolve_directory(link_parent / "pickmypostcode")
        self.assertEqual(resolved, setup.resolve_directory(real_parent / "pickmypostcode"))
        self.assertTrue(setup.same_directory(str(link_parent / "pickmypostcode"), str(resolved)))
        leaf = self.root / "leaf-link"
        leaf.symlink_to(real_parent)
        with self.assertRaises(setup.SetupError) as caught:
            setup.resolve_directory(leaf)
        self.assertIn("symlink", str(caught.exception))

    def test_compose_config_error_does_not_include_the_secret_line(self):
        answers = {
            "NOTIFICATION_EMAIL_ADDRESS": "person@example.com",
            "YOUR_POSTCODE": "SW1A 1AA",
            "PMP_EMAIL": "person@example.com",
            "EMAIL_ADDRESS": "sender@gmail.com",
            "EMAIL_PASSWORD": SECRET,
        }
        staging = setup.make_staging(
            (REPO / "docker-compose.yml").read_text(encoding="utf-8"), answers, None
        )
        self.addCleanup(setup.discard_staging, staging)
        with mock.patch.dict(os.environ, self.env(PMP_FAKE_CONFIG="fail"), clear=True):
            with self.assertRaises(setup.SetupError) as caught:
                setup.run_health(staging, self.directory)
        self.assertNotIn("super-secret", str(caught.exception))
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertIn("not printed", str(caught.exception))
        downs = [event for event in _events(self.log) if event["cmd"] == "down"]
        self.assertTrue(downs)
        self.assertNotIn("--remove-orphans", downs[0]["argv"])

    def _write_managed(self, notification="person@example.com"):
        self.directory.mkdir(mode=0o700)
        (self.directory / "docker-compose.yml").write_text(
            (REPO / "docker-compose.yml").read_text(encoding="utf-8"), encoding="utf-8"
        )
        env_text = setup.render_env({
            "NOTIFICATION_EMAIL_ADDRESS": notification,
            "YOUR_POSTCODE": "SW1A 1AA",
            "PMP_EMAIL": "person@example.com",
            "EMAIL_ADDRESS": "sender@gmail.com",
            "EMAIL_PASSWORD": "stored$secret",
        })
        env_path = self.directory / ".env"
        env_path.write_text(env_text, encoding="utf-8")
        os.chmod(env_path, 0o600)
        (self.directory / ".pmp-setup.json").write_bytes(setup.marker_bytes())
        logs = self.directory / "pickmypostcode_logs"
        logs.mkdir(mode=0o700)
        (logs / "pastData.json").write_text('{"keep": true}\n', encoding="utf-8")
        (logs / "note.txt").write_text("history-note", encoding="utf-8")

    def _snapshot(self):
        snapshot = {}
        for path in sorted(self.directory.rglob("*")):
            if path.is_file() and not path.is_symlink():
                snapshot[str(path.relative_to(self.directory))] = path.read_bytes()
        return snapshot


if __name__ == "__main__":
    unittest.main()
