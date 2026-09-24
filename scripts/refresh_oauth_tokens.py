from __future__ import annotations
import subprocess
import argparse
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs
from wsgiref.simple_server import (
    WSGIRequestHandler,
    WSGIServer,
    make_server,
)
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page, sync_playwright

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SHEETS_READ_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"
SHEETS_WRITE_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
PROJECT_ID = "job-application-tracker-508819"
REGION = "us-west2"
CLOUD_RUN_JOB = "job-application-agent"
SCHEDULER_JOB = "job-application-agent-every-15-min"
DEFAULT_PROFILE_DIR = Path.home() / ".job-application-agent" / "google-profile"


@dataclass(frozen=True)
class OAuthTarget:
    name: str
    scopes: tuple[str, ...]
    token_path: Path
    secret_name: str
    validator: Callable[[Credentials, str | None], None]


@dataclass
class CallbackState:
    received: threading.Event = field(default_factory=threading.Event)
    authorization_response: str | None = None
    oauth_error: str | None = None


class LocalOAuthCallback:
    def __init__(self) -> None:
        self.state = CallbackState()
        self.server: WSGIServer | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "LocalOAuthCallback":
        def app(environ, start_response):
            host = environ.get("HTTP_HOST", "localhost")
            path = environ.get("PATH_INFO", "/")
            query = environ.get("QUERY_STRING", "")
            params = parse_qs(query)

            if "code" in params or "error" in params:
                response = f"http://{host}{path}"
                if query:
                    response += f"?{query}"
                self.state.authorization_response = response
                if "error" in params:
                    self.state.oauth_error = params["error"][0]
                self.state.received.set()
                body = b"OAuth authorization received. You can close this tab."
            else:
                body = b"OAuth callback server is running."

            start_response(
                "200 OK",
                [
                    ("Content-Type", "text/plain; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                ],
            )
            return [body]

        self.server = make_server(
            "localhost",
            0,
            app,
            handler_class=QuietOAuthRequestHandler,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.1},
            daemon=True,
        )
        self.thread.start()
        return self

    @property
    def redirect_uri(self) -> str:
        if self.server is None:
            raise RuntimeError("Callback server has not started.")
        return f"http://localhost:{self.server.server_port}/"

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2)


def validate_gmail(creds: Credentials, _: str | None) -> None:
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    service.users().getProfile(userId="me").execute()


def validate_sheets_access(creds: Credentials, spreadsheet_id: str | None) -> None:
    if not spreadsheet_id:
        raise RuntimeError(
            "TRACKER_SPREADSHEET_ID is required for Sheets validation."
        )

    service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    result = (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="spreadsheetId,properties.title",
        )
        .execute()
    )

    if result.get("spreadsheetId") != spreadsheet_id:
        raise RuntimeError("Sheets validation returned an unexpected spreadsheet.")

def build_targets() -> tuple[OAuthTarget, ...]:
    return (
        OAuthTarget(
            name="gmail",
            scopes=(GMAIL_SCOPE,),
            token_path=REPO_ROOT / "token.json",
            secret_name="job-agent-gmail-token",
            validator=validate_gmail,
        ),
        OAuthTarget(
            name="sheets-read",
            scopes=(SHEETS_READ_SCOPE,),
            token_path=REPO_ROOT / "token_sheets_readonly.json",
            secret_name="job-agent-sheets-readonly-token",
            validator=validate_sheets_access,
        ),
        OAuthTarget(
            name="sheets-write",
            scopes=(SHEETS_WRITE_SCOPE,),
            token_path=REPO_ROOT / "token_sheets_write.json",
            secret_name="job-agent-sheets-write-token",
            validator=validate_sheets_access,
        ),
    )
def is_visible(page: Page, selector: str) -> bool:
    locator = page.locator(selector)
    return locator.count() > 0 and locator.first.is_visible()

def choose_single_account(page: Page) -> bool:
    accounts = page.locator("[data-identifier]:visible")
    count = accounts.count()

    if count == 1:
        account = accounts.first
        before_url = page.url

        try:
            # Google's account tile contains an overlay element that can
            # intercept pointer events. We already know exactly which single
            # remembered account is present, so force the click.
            account.click(
                force=True,
                timeout=5_000,
            )

        except PlaywrightError:
            # Google frequently destroys the account-picker DOM immediately
            # after a successful selection. In that case Playwright may report
            # a detached element / timeout even though navigation succeeded.
            if page.url != before_url:
                return True

            # If the account chooser itself disappeared, treat that as the
            # same successful state transition.
            try:
                if accounts.count() == 0 or not account.is_visible():
                    return True
            except PlaywrightError:
                return True

            # Still on the same page with the chooser intact: real failure.
            raise

        return True

    if count > 1:
        raise RuntimeError(
            "Google presented multiple remembered accounts. "
            "Refusing to guess which one to authorize."
        )

    return False
def handle_unverified_app(page: Page) -> bool:
    body = page.locator("body").inner_text(timeout=2_000)

    if (
        "Google hasn’t verified this app" in body
        or "Google hasn't verified this app" in body
    ):
        advanced = page.get_by_role(
            "button",
            name=re.compile(r"^Advanced$", re.IGNORECASE),
        )
        if advanced.count() > 0 and advanced.first.is_visible():
            advanced.first.click()
            return True

    unsafe = page.get_by_text(
        re.compile(r"Go to .+\(unsafe\)", re.IGNORECASE)
    )
    if unsafe.count() > 0 and unsafe.first.is_visible():
        unsafe.first.click()
        return True

    return False
def click_select_all(page: Page) -> bool:
    checkbox = page.get_by_role(
        "checkbox", name=re.compile(r"select all", re.IGNORECASE)
    )
    if (
        checkbox.count() > 0
        and checkbox.first.is_visible()
        and not checkbox.first.is_checked()
    ):
        checkbox.first.check()
        return True
    return False


def check_one_permission_box(page: Page) -> bool:
    checkboxes = page.get_by_role("checkbox")

    for index in range(checkboxes.count()):
        checkbox = checkboxes.nth(index)
        if not checkbox.is_visible():
            continue

        label = checkbox.get_attribute("aria-label") or ""
        if re.search(r"select all", label, re.IGNORECASE):
            continue

        if not checkbox.is_checked():
            checkbox.check()
            return True

    return False


def click_named_button(page: Page, *names: str) -> bool:
    for name in names:
        button = page.get_by_role(
            "button",
            name=re.compile(rf"^{re.escape(name)}$", re.IGNORECASE),
        )
        if button.count() > 0 and button.first.is_visible():
            button.first.click()
            return True
    return False


def refuse_password_or_mfa(page: Page) -> None:
    if is_visible(page, 'input[type="password"]'):
        raise RuntimeError(
            "Google requested a password. Password entry is intentionally not "
            "automated. Re-authenticate the dedicated Edge profile manually, "
            "then rerun."
        )

    body = page.locator("body").inner_text(timeout=2_000)
    blocked_markers = (
        "2-Step Verification",
        "2-step verification",
        "Verify it’s you",
        "Verify it's you",
        "Enter a code",
        "Get a verification code",
        "Use your passkey",
    )
    if any(marker in body for marker in blocked_markers):
        raise RuntimeError(
            "Google requested MFA or identity verification. That step is "
            "intentionally not automated. Re-authenticate the dedicated Edge "
            "profile manually, then rerun."
        )


def complete_google_consent(
    page: Page,
    auth_url: str,
    callback_state: CallbackState,
    timeout_seconds: int,
) -> None:
    page.goto(auth_url, wait_until="domcontentloaded")
    deadline = time.monotonic() + timeout_seconds

    while not callback_state.received.is_set():
        if time.monotonic() >= deadline:
            raise TimeoutError("Timed out waiting for the Google OAuth callback.")

        refuse_password_or_mfa(page)

        if callback_state.received.is_set():
            break

        if choose_single_account(page):
            page.wait_for_timeout(400)
            continue

        if callback_state.received.is_set():
            break

        if handle_unverified_app(page):
            page.wait_for_timeout(400)
            continue

        if callback_state.received.is_set():
            break

        if click_select_all(page):
            page.wait_for_timeout(250)
            continue

        if callback_state.received.is_set():
            break

        if check_one_permission_box(page):
            page.wait_for_timeout(250)
            continue

        if callback_state.received.is_set():
            break

        if click_named_button(page, "Continue", "Allow"):
            page.wait_for_timeout(400)
            continue

        page.wait_for_timeout(250)


def ensure_expected_scopes(target: OAuthTarget, creds: Credentials) -> None:
    if not creds.refresh_token:
        raise RuntimeError(f"{target.name}: Google did not return a refresh token.")

    granted = set(
        getattr(creds, "granted_scopes", None)
        or creds.scopes
        or ()
    )
    required = set(target.scopes)

    if required - granted:
        raise RuntimeError(f"{target.name}: required OAuth scope was not granted.")

    if target.name == "gmail":
        extra_gmail = {
            scope
            for scope in granted
            if "/auth/gmail." in scope and scope not in required
        }
        if extra_gmail:
            raise RuntimeError(
                "gmail: unexpected broader Gmail scope detected; refusing "
                "to save the credential."
            )

    if target.name == "sheets-read" and SHEETS_WRITE_SCOPE in granted:
        raise RuntimeError(
            "sheets-read: write scope was granted to the read-only credential; "
            "refusing to collapse the credential boundary."
        )


def obtain_credentials(
    page: Page,
    credentials_path: Path,
    target: OAuthTarget,
    timeout_seconds: int,
) -> Credentials:
    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_path),
        scopes=list(target.scopes),
    )

    with LocalOAuthCallback() as callback:
        flow.redirect_uri = callback.redirect_uri

        auth_url, _ = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="false",
        )

        complete_google_consent(
            page=page,
            auth_url=auth_url,
            callback_state=callback.state,
            timeout_seconds=timeout_seconds,
        )

        if callback.state.oauth_error:
            raise RuntimeError(
                f"{target.name}: Google returned OAuth error "
                f"{callback.state.oauth_error!r}."
            )

        authorization_response = callback.state.authorization_response
        if not authorization_response:
            raise RuntimeError(
                f"{target.name}: callback arrived without an authorization response."
            )

        # Keep the real redirect URI as HTTP localhost. Only normalize the
        # callback string passed into oauthlib so it does not reject localhost
        # as insecure transport while parsing the response.
        secure_authorization_response = authorization_response.replace(
            "http://", "https://", 1
        )

        flow.fetch_token(
            authorization_response=secure_authorization_response
        )

    creds = flow.credentials
    ensure_expected_scopes(target, creds)
    return creds


def backup_path(token_path: Path) -> Path:
    return token_path.with_name(
        f"{token_path.stem}.pre-refresh{token_path.suffix}"
    )


def commit_local_tokens(
    targets: tuple[OAuthTarget, ...],
    credentials_by_name: dict[str, Credentials],
) -> None:
    original_exists: dict[Path, bool] = {}
    backups: dict[Path, Path] = {}
    replacement_tmps: list[Path] = []

    # Back up every existing token before replacing any token.
    for target in targets:
        token_path = target.token_path
        original_exists[token_path] = token_path.exists()

        if token_path.exists():
            backup = backup_path(token_path)
            shutil.copy2(token_path, backup)
            backups[token_path] = backup

    try:
        for target in targets:
            token_path = target.token_path
            replacement = token_path.with_name(
                f".{token_path.name}.refreshing"
            )
            replacement_tmps.append(replacement)

            replacement.write_text(
                credentials_by_name[target.name].to_json(),
                encoding="utf-8",
            )
            os.replace(replacement, token_path)

    except Exception:
        # Restore the complete pre-refresh local state if any replacement fails.
        for token_path, existed in original_exists.items():
            backup = backups.get(token_path)
            if existed and backup:
                shutil.copy2(backup, token_path)
            elif not existed and token_path.exists():
                token_path.unlink()
        raise

    finally:
        for replacement in replacement_tmps:
            if replacement.exists():
                replacement.unlink()

def find_gcloud() -> str:
    # Optional explicit override, useful on Windows/n8n.
    configured = os.environ.get("GCLOUD_BIN")
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path)

        raise RuntimeError(
            f"GCLOUD_BIN points to a file that does not exist: {path}"
        )

    # shutil.which understands Windows PATHEXT, including .cmd.
    for executable in ("gcloud", "gcloud.cmd", "gcloud.exe"):
        resolved = shutil.which(executable)
        if resolved:
            return resolved

    # Common Google Cloud SDK locations on Windows.
    if os.name == "nt":
        candidates = []

        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            candidates.append(
                Path(local_app_data)
                / "Google"
                / "Cloud SDK"
                / "google-cloud-sdk"
                / "bin"
                / "gcloud.cmd"
            )

        program_files_x86 = os.environ.get("PROGRAMFILES(X86)")
        if program_files_x86:
            candidates.append(
                Path(program_files_x86)
                / "Google"
                / "Cloud SDK"
                / "google-cloud-sdk"
                / "bin"
                / "gcloud.cmd"
            )

        program_files = os.environ.get("PROGRAMFILES")
        if program_files:
            candidates.append(
                Path(program_files)
                / "Google"
                / "Cloud SDK"
                / "google-cloud-sdk"
                / "bin"
                / "gcloud.cmd"
            )

        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)

    raise RuntimeError(
        "gcloud could not be located. "
        "Set GCLOUD_BIN to the full path to gcloud.cmd."
    )


def run_gcloud(*args: str) -> str:
    gcloud = find_gcloud()

    result = subprocess.run(
        [gcloud, *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or "unknown gcloud failure"

        raise RuntimeError(
            f"gcloud command failed: {detail}"
        )

    return result.stdout.strip()

def version_id(resource_name: str) -> str:
    value = resource_name.strip()

    if not value:
        raise RuntimeError(
            "gcloud returned an empty secret version resource name."
        )

    return value.rsplit("/", 1)[-1]

def get_scheduler_state(
    project_id: str,
    scheduler_job: str,
    region: str,
) -> str:
    return run_gcloud(
        "scheduler",
        "jobs",
        "describe",
        scheduler_job,
        f"--location={region}",
        f"--project={project_id}",
        "--format=value(state)",
    ).strip()


def require_scheduler_paused(
    project_id: str,
    scheduler_job: str,
    region: str,
) -> None:
    state = get_scheduler_state(
        project_id=project_id,
        scheduler_job=scheduler_job,
        region=region,
    )

    if state != "PAUSED":
        raise RuntimeError(
            "Secret rotation refused because Cloud Scheduler is not PAUSED. "
            f"Current state: {state or '<empty>'}"
        )


def require_scheduler_enabled(
    project_id: str,
    scheduler_job: str,
    region: str,
) -> None:
    state = get_scheduler_state(
        project_id=project_id,
        scheduler_job=scheduler_job,
        region=region,
    )

    if state != "ENABLED":
        raise RuntimeError(
            "Production maintenance refused because Cloud Scheduler did not "
            "start in ENABLED state. This prevents the script from assuming "
            "ownership of a scheduler that was already paused. "
            f"Current state: {state or '<empty>'}"
        )


def pause_scheduler(
    project_id: str,
    scheduler_job: str,
    region: str,
) -> None:
    # Production mode only owns the pause if the scheduler began ENABLED.
    require_scheduler_enabled(
        project_id=project_id,
        scheduler_job=scheduler_job,
        region=region,
    )

    run_gcloud(
        "scheduler",
        "jobs",
        "pause",
        scheduler_job,
        f"--location={region}",
        f"--project={project_id}",
        "--quiet",
    )

    require_scheduler_paused(
        project_id=project_id,
        scheduler_job=scheduler_job,
        region=region,
    )

    print("[scheduler] PAUSED")


def resume_scheduler(
    project_id: str,
    scheduler_job: str,
    region: str,
) -> None:
    run_gcloud(
        "scheduler",
        "jobs",
        "resume",
        scheduler_job,
        f"--location={region}",
        f"--project={project_id}",
        "--quiet",
    )

    state = get_scheduler_state(
        project_id=project_id,
        scheduler_job=scheduler_job,
        region=region,
    )

    if state != "ENABLED":
        raise RuntimeError(
            "Scheduler resume command completed, but ENABLED state could not "
            f"be verified. Current state: {state or '<empty>'}"
        )

    print("[scheduler] ENABLED")

def get_latest_secret_version(
    secret_name: str,
    project_id: str,
) -> str:
    resource_name = run_gcloud(
        "secrets",
        "versions",
        "describe",
        "latest",
        f"--secret={secret_name}",
        f"--project={project_id}",
        "--format=value(name)",
    )

    return version_id(resource_name)


def add_secret_version(
    secret_name: str,
    token_path: Path,
    project_id: str,
) -> str:
    resource_name = run_gcloud(
        "secrets",
        "versions",
        "add",
        secret_name,
        f"--data-file={token_path}",
        f"--project={project_id}",
        "--format=value(name)",
    )

    return version_id(resource_name)


def verify_secret_version_enabled(
    secret_name: str,
    version: str,
    project_id: str,
) -> None:
    state = run_gcloud(
        "secrets",
        "versions",
        "describe",
        version,
        f"--secret={secret_name}",
        f"--project={project_id}",
        "--format=value(state)",
    ).strip()

    if state != "ENABLED":
        raise RuntimeError(
            f"{secret_name} version {version} is not ENABLED "
            f"(state={state!r})."
        )


def rotate_secrets(
    targets: tuple[OAuthTarget, ...],
    project_id: str,
    scheduler_job: str,
    region: str,
) -> dict[str, tuple[str, str]]:
    # The scheduler must remain paused while `latest` changes sequentially.
    require_scheduler_paused(
        project_id=project_id,
        scheduler_job=scheduler_job,
        region=region,
    )

    previous_versions: dict[str, str] = {}

    print()
    print("Preflighting Secret Manager.")

    # Complete all metadata/access checks before the first mutation.
    for target in targets:
        if not target.token_path.is_file():
            raise RuntimeError(
                f"{target.name}: local token does not exist: "
                f"{target.token_path}"
            )

        previous = get_latest_secret_version(
            secret_name=target.secret_name,
            project_id=project_id,
        )

        previous_versions[target.name] = previous

        print(
            f"[secret-preflight] {target.name}: "
            f"current version {previous}"
        )

    # Check scheduler state again immediately before the first upload.
    require_scheduler_paused(
        project_id=project_id,
        scheduler_job=scheduler_job,
        region=region,
    )

    rotated: dict[str, tuple[str, str]] = {}

    print()
    print("Beginning Secret Manager rotation.")

    try:
        for target in targets:
            previous = previous_versions[target.name]

            new_version = add_secret_version(
                secret_name=target.secret_name,
                token_path=target.token_path,
                project_id=project_id,
            )

            # Record immediately: from this point onward production has changed.
            rotated[target.name] = (
                previous,
                new_version,
            )

            verify_secret_version_enabled(
                secret_name=target.secret_name,
                version=new_version,
                project_id=project_id,
            )

            print(
                f"[secret] {target.name}: "
                f"{previous} -> {new_version}"
            )

    except Exception as exc:
        print()
        print(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!",
            file=sys.stderr,
        )
        print(
            "PARTIAL SECRET ROTATION",
            file=sys.stderr,
        )
        print(
            "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!",
            file=sys.stderr,
        )

        if rotated:
            print(
                "Secrets already changed:",
                file=sys.stderr,
            )

            for name, (previous, new) in rotated.items():
                print(
                    f"- {name}: previous={previous}, new={new}",
                    file=sys.stderr,
                )
        else:
            print(
                "No secret versions were uploaded.",
                file=sys.stderr,
            )

        pending = [
            target.name
            for target in targets
            if target.name not in rotated
        ]

        if pending:
            print(
                "Not successfully completed:",
                file=sys.stderr,
            )
            for name in pending:
                print(
                    f"- {name}",
                    file=sys.stderr,
                )

        print(
            "Cloud Run was NOT triggered.",
            file=sys.stderr,
        )
        print(
            "Scheduler must remain PAUSED.",
            file=sys.stderr,
        )

        raise RuntimeError(
            f"Secret rotation did not complete: {exc}"
        ) from exc

    return rotated
def resource_id(resource_name: str) -> str:
    value = resource_name.strip()

    if not value:
        raise RuntimeError("Received an empty Google Cloud resource name.")

    return value.rsplit("/", 1)[-1]


def get_latest_execution_name(
    cloud_run_job: str,
    project_id: str,
    region: str,
) -> str | None:
    value = run_gcloud(
        "run",
        "jobs",
        "describe",
        cloud_run_job,
        f"--region={region}",
        f"--project={project_id}",
        "--format=value(status.latestCreatedExecution.name)",
    ).strip()

    if not value:
        return None

    return resource_id(value)


def start_cloud_run_execution(
    cloud_run_job: str,
    project_id: str,
    region: str,
) -> str:
    previous_execution = get_latest_execution_name(
        cloud_run_job=cloud_run_job,
        project_id=project_id,
        region=region,
    )

    # Do not use --wait here as the sole success signal.
    # We want the exact execution identity first, then independently inspect it.
    output = run_gcloud(
        "run",
        "jobs",
        "execute",
        cloud_run_job,
        f"--region={region}",
        f"--project={project_id}",
        "--format=value(metadata.name)",
        "--quiet",
    ).strip()

    captured_execution = (
        resource_id(output)
        if output
        else None
    )

    latest_execution = get_latest_execution_name(
        cloud_run_job=cloud_run_job,
        project_id=project_id,
        region=region,
    )

    # Prefer the identity returned directly by the execute command.
    # The latest-created execution is only a fallback/cross-check.
    execution_name = captured_execution or latest_execution

    if not execution_name:
        raise RuntimeError(
            "Cloud Run execution was requested, but no execution name "
            "could be captured."
        )

    if (
        previous_execution is not None
        and execution_name == previous_execution
    ):
        raise RuntimeError(
            "Cloud Run execution identity is ambiguous: the captured "
            "execution is the same as the execution that existed before "
            "the trigger."
        )

    # Scheduler is paused, so a mismatch here is unexpected and should
    # fail closed instead of guessing which execution belongs to us.
    if (
        latest_execution is not None
        and latest_execution != execution_name
    ):
        raise RuntimeError(
            "Cloud Run execution identity is ambiguous. "
            f"execute returned {execution_name!r}, but the job reports "
            f"{latest_execution!r} as its latest execution."
        )

    print(f"[cloud-run] execution started: {execution_name}")
    return execution_name


def describe_cloud_run_execution(
    execution_name: str,
    project_id: str,
    region: str,
) -> dict:
    raw = run_gcloud(
        "run",
        "jobs",
        "executions",
        "describe",
        execution_name,
        f"--region={region}",
        f"--project={project_id}",
        "--format=json",
    )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Could not parse Cloud Run execution {execution_name!r}."
        ) from exc

    actual_name = (
        payload.get("metadata", {}).get("name")
        or payload.get("name")
    )

    if actual_name:
        actual_id = resource_id(actual_name)

        if actual_id != execution_name:
            raise RuntimeError(
                "Cloud Run returned details for an unexpected execution: "
                f"expected={execution_name!r}, actual={actual_id!r}"
            )

    return payload


def execution_status(payload: dict) -> dict:
    # gcloud may expose the v1-style nested status object or v2-style
    # execution fields at the top level. Support both while remaining strict.
    status = payload.get("status")

    if isinstance(status, dict):
        return status

    return payload


def completed_condition_state(status: dict) -> str | None:
    conditions = status.get("conditions") or []

    for condition in conditions:
        if str(condition.get("type", "")).lower() != "completed":
            continue

        raw_state = condition.get("status")

        if raw_state is None:
            raw_state = condition.get("state")

        normalized = str(raw_state or "").strip().upper()

        if normalized in {
            "TRUE",
            "CONDITION_SUCCEEDED",
        }:
            return "SUCCEEDED"

        if normalized in {
            "FALSE",
            "CONDITION_FAILED",
        }:
            return "FAILED"

        return normalized or None

    return None


def wait_for_cloud_run_execution(
    execution_name: str,
    project_id: str,
    region: str,
    timeout_seconds: int,
) -> dict:
    deadline = time.monotonic() + timeout_seconds

    while True:
        payload = describe_cloud_run_execution(
            execution_name=execution_name,
            project_id=project_id,
            region=region,
        )

        status = execution_status(payload)

        completion_time = status.get("completionTime")
        condition_state = completed_condition_state(status)

        if (
            completion_time
            or condition_state in {"SUCCEEDED", "FAILED"}
        ):
            return payload

        if time.monotonic() >= deadline:
            raise TimeoutError(
                "Timed out waiting for exact Cloud Run execution "
                f"{execution_name!r} to complete."
            )

        time.sleep(5)


def verify_cloud_run_execution_succeeded(
    execution_name: str,
    project_id: str,
    region: str,
    timeout_seconds: int,
) -> None:
    payload = wait_for_cloud_run_execution(
        execution_name=execution_name,
        project_id=project_id,
        region=region,
        timeout_seconds=timeout_seconds,
    )

    status = execution_status(payload)

    completion_time = status.get("completionTime")
    condition_state = completed_condition_state(status)

    succeeded_count = int(status.get("succeededCount") or 0)
    failed_count = int(status.get("failedCount") or 0)
    cancelled_count = int(status.get("cancelledCount") or 0)

    if not completion_time:
        raise RuntimeError(
            f"Execution {execution_name} reached a terminal-looking state "
            "without a completionTime."
        )

    if condition_state != "SUCCEEDED":
        raise RuntimeError(
            f"Execution {execution_name} did not report a successful "
            f"Completed condition (state={condition_state!r})."
        )

    if succeeded_count < 1:
        raise RuntimeError(
            f"Execution {execution_name} completed without a succeeded task."
        )

    if failed_count != 0 or cancelled_count != 0:
        raise RuntimeError(
            f"Execution {execution_name} was not cleanly successful: "
            f"succeeded={succeeded_count}, "
            f"failed={failed_count}, "
            f"cancelled={cancelled_count}."
        )

    print(
        f"[cloud-run] execution verified successful: "
        f"{execution_name}"
    )


def verify_run_succeeded_log(
    execution_name: str,
    cloud_run_job: str,
    project_id: str,
    timeout_seconds: int,
) -> None:
    log_filter = (
        'resource.type="cloud_run_job" '
        f'AND resource.labels.job_name="{cloud_run_job}" '
        f'AND labels."run.googleapis.com/execution_name"="{execution_name}" '
        'AND jsonPayload.event="run_succeeded"'
    )

    deadline = time.monotonic() + timeout_seconds

    while True:
        match = run_gcloud(
            "logging",
            "read",
            log_filter,
            f"--project={project_id}",
            "--freshness=1h",
            "--limit=1",
            "--format=value(timestamp)",
        ).strip()

        if match:
            print(
                f"[cloud-run] run_succeeded log verified: "
                f"{execution_name}"
            )
            return

        if time.monotonic() >= deadline:
            raise RuntimeError(
                "Exact Cloud Run execution completed successfully, but its "
                f"run_succeeded application event was not found in Cloud "
                f"Logging within {timeout_seconds} seconds. "
                f"Execution: {execution_name}"
            )

        # Cloud Logging ingestion may lag slightly behind execution completion.
        time.sleep(2)
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh Gmail, Sheets read-only, and Sheets write OAuth "
            "credentials. Local-only behavior is the default; production "
            "mutation requires an explicit flag."
        )
    )

    parser.add_argument(
        "--credentials",
        type=Path,
        default=REPO_ROOT / "credentials.json",
    )

    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
    )

    parser.add_argument(
        "--tracker-spreadsheet-id",
        default=os.environ.get("TRACKER_SPREADSHEET_ID"),
    )

    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=180,
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--rotate-secrets",
        action="store_true",
        help=(
            "After local OAuth generation and validation succeeds, upload "
            "all three token files as new Secret Manager versions. "
            "Scheduler must already be PAUSED. Cloud Run is not executed."
        ),
    )

    mode.add_argument(
        "--production",
        action="store_true",
        help=(
            "Run the complete production maintenance workflow: refresh and "
            "validate OAuth, commit local tokens, pause Scheduler, rotate "
            "Secret Manager, execute and verify the exact Cloud Run "
            "execution, verify run_succeeded, then resume Scheduler."
        ),
    )

    parser.add_argument(
        "--project-id",
        default=PROJECT_ID,
    )

    parser.add_argument(
        "--scheduler-job",
        default=SCHEDULER_JOB,
    )

    parser.add_argument(
        "--scheduler-region",
        default=REGION,
    )

    parser.add_argument(
        "--cloud-run-job",
        default=CLOUD_RUN_JOB,
    )

    parser.add_argument(
        "--cloud-run-timeout-seconds",
        type=int,
        default=900,
    )

    parser.add_argument(
        "--log-timeout-seconds",
        type=int,
        default=60,
    )

    return parser.parse_args()

def main() -> int:
    args = parse_args()

    if not args.credentials.is_file():
        print(
            f"ERROR: OAuth client credentials file not found: {args.credentials}",
            file=sys.stderr,
        )
        return 1

    if not args.profile_dir.exists():
        print(
            f"ERROR: dedicated Google browser profile not found: {args.profile_dir}",
            file=sys.stderr,
        )
        return 1

    if (
        args.timeout_seconds <= 0
        or args.cloud_run_timeout_seconds <= 0
        or args.log_timeout_seconds <= 0
    ):
        print(
            "ERROR: timeout values must be positive integers.",
            file=sys.stderr,
        )
        return 1

    tracker_spreadsheet_id = (
        args.tracker_spreadsheet_id.strip()
        if args.tracker_spreadsheet_id
        else None
    )

    if not tracker_spreadsheet_id:
        print(
            "ERROR: TRACKER_SPREADSHEET_ID is not set. Set it in the "
            "environment or pass --tracker-spreadsheet-id.",
            file=sys.stderr,
        )
        return 1

    targets = build_targets()
    fresh: dict[str, Credentials] = {}

    rotation_enabled = args.rotate_secrets or args.production

    if args.production:
        print("PRODUCTION OAUTH MAINTENANCE")
    else:
        print("LOCAL OAUTH MAINTENANCE")

    if rotation_enabled:
        print("Secret Manager: ROTATION ENABLED")
    else:
        print("Secret Manager: WILL NOT BE MODIFIED")

    if args.production:
        print("Cloud Scheduler: WILL BE PAUSED DURING MAINTENANCE")
        print("Cloud Run: WILL BE EXECUTED AND VERIFIED")
    else:
        print("Cloud Run: WILL NOT BE MODIFIED")

    print()

    local_commit_completed = False
    rotated_versions: dict[str, tuple[str, str]] = {}

    scheduler_pause_attempted = False
    execution_name: str | None = None

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(args.profile_dir),
                channel="msedge",
                headless=False,
                no_viewport=True,
            )

            try:
                page = (
                    context.pages[0]
                    if context.pages
                    else context.new_page()
                )

                # Generation pass: all three must succeed before any local
                # token file is replaced.
                for target in targets:
                    print(f"[oauth] {target.name}: starting")

                    fresh[target.name] = obtain_credentials(
                        page=page,
                        credentials_path=args.credentials,
                        target=target,
                        timeout_seconds=args.timeout_seconds,
                    )

                    print(
                        f"[oauth] {target.name}: credential generated"
                    )

            finally:
                context.close()

        print()
        print(
            "All three credentials generated. "
            "Beginning validation pass."
        )

        # Still no local replacement and no production mutation.
        for target in targets:
            target.validator(
                fresh[target.name],
                tracker_spreadsheet_id,
            )

            print(f"[validate] {target.name}: OK")

        print()
        print(
            "All validations passed. "
            "Committing local token files."
        )

        commit_local_tokens(
            targets=targets,
            credentials_by_name=fresh,
        )

        local_commit_completed = True

        if args.production:
            print()
            print("Beginning production maintenance boundary.")

            scheduler_pause_attempted = True

            pause_scheduler(
                project_id=args.project_id,
                scheduler_job=args.scheduler_job,
                region=args.scheduler_region,
            )

            # rotate_secrets independently verifies PAUSED before
            # preflight and again immediately before its first mutation.
            rotated_versions = rotate_secrets(
                targets=targets,
                project_id=args.project_id,
                scheduler_job=args.scheduler_job,
                region=args.scheduler_region,
            )

            execution_name = start_cloud_run_execution(
                cloud_run_job=args.cloud_run_job,
                project_id=args.project_id,
                region=args.scheduler_region,
            )

            verify_cloud_run_execution_succeeded(
                execution_name=execution_name,
                project_id=args.project_id,
                region=args.scheduler_region,
                timeout_seconds=args.cloud_run_timeout_seconds,
            )

            verify_run_succeeded_log(
                execution_name=execution_name,
                cloud_run_job=args.cloud_run_job,
                project_id=args.project_id,
                timeout_seconds=args.log_timeout_seconds,
            )

            # This is intentionally NOT in finally.
            # Scheduler resumes only after both exact execution success
            # and the application-level run_succeeded event are confirmed.
            resume_scheduler(
                project_id=args.project_id,
                scheduler_job=args.scheduler_job,
                region=args.scheduler_region,
            )

        elif args.rotate_secrets:
            rotated_versions = rotate_secrets(
                targets=targets,
                project_id=args.project_id,
                scheduler_job=args.scheduler_job,
                region=args.scheduler_region,
            )

    except Exception as exc:
        print()
        print(
            "OAUTH MAINTENANCE FAILED",
            file=sys.stderr,
        )

        print(
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )

        if local_commit_completed:
            print(
                "Fresh validated local tokens remain in place.",
                file=sys.stderr,
            )
            print(
                "Pre-refresh local backups remain available.",
                file=sys.stderr,
            )
        else:
            print(
                "Existing local token files were left unchanged or "
                "restored from backup.",
                file=sys.stderr,
            )

        if args.production:
            print()
            print(
                "PRODUCTION RECOVERY STATE",
                file=sys.stderr,
            )

            if rotated_versions:
                print(
                    "Completed secret rotations:",
                    file=sys.stderr,
                )

                for name, (previous, new) in rotated_versions.items():
                    print(
                        f"- {name}: previous={previous}, new={new}",
                        file=sys.stderr,
                    )

            if execution_name:
                print(
                    f"Cloud Run execution: {execution_name}",
                    file=sys.stderr,
                )
            else:
                print(
                    "No verified Cloud Run execution name was captured.",
                    file=sys.stderr,
                )

            if scheduler_pause_attempted:
                try:
                    scheduler_state = get_scheduler_state(
                        project_id=args.project_id,
                        scheduler_job=args.scheduler_job,
                        region=args.scheduler_region,
                    )
                except Exception as state_exc:
                    scheduler_state = None
                    print(
                        "Could not determine current Scheduler state: "
                        f"{state_exc}",
                        file=sys.stderr,
                    )

                if scheduler_state:
                    print(
                        f"Scheduler state: {scheduler_state}",
                        file=sys.stderr,
                    )

                if scheduler_state == "PAUSED":
                    print(
                        "Scheduler remains PAUSED.",
                        file=sys.stderr,
                    )
                    print(
                        "It was intentionally NOT resumed after the failure.",
                        file=sys.stderr,
                    )
                elif scheduler_state != "ENABLED":
                    print(
                        "Scheduler was NOT automatically resumed.",
                        file=sys.stderr,
                    )

            print(
                "No automatic secret rollback was attempted.",
                file=sys.stderr,
            )

        else:
            print(
                "Cloud Run was not triggered.",
                file=sys.stderr,
            )

        return 1

    print()
    print("OAUTH MAINTENANCE SUCCEEDED")
    print("Fresh local tokens:")

    for target in targets:
        print(f"- {target.token_path.name}")

    if rotation_enabled:
        print()
        print("Secret Manager rotation:")

        for name, (previous, new) in rotated_versions.items():
            print(
                f"- {name}: {previous} -> {new}"
            )

        print("Secret Manager: ROTATED")
    else:
        print("Secret Manager: NOT MODIFIED")

    if args.production:
        print()
        print(f"Cloud Run execution: {execution_name}")
        print("Cloud Run: VERIFIED")
        print("run_succeeded: VERIFIED")
        print("Cloud Scheduler: ENABLED")
    else:
        print("Cloud Run: NOT MODIFIED")

    return 0

class QuietOAuthRequestHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        # Do not log OAuth callback query parameters / authorization codes.
        pass

if __name__ == "__main__":
    raise SystemExit(main())
