from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"

# Local development:
# load secrets/configuration from NoRepeat/.env.
#
# Railway/production:
# real environment variables already present in the process take precedence
# because override=False.
load_dotenv(dotenv_path=ENV_FILE, override=False)

DEFAULT_MAX_COST = float(os.getenv("NOREPEAT_BOB_MAX_COST", "0.50"))
DEFAULT_MAX_TURNS = int(os.getenv("NOREPEAT_BOB_MAX_TURNS", "10"))
DEFAULT_TIMEOUT_SECONDS = int(
    os.getenv("NOREPEAT_BOB_TIMEOUT_SECONDS", "900")
)
DEFAULT_MODE = os.getenv("NOREPEAT_BOB_MODE", "agent").strip() or "agent"


class BobRunnerError(Exception):
    """Base exception for IBM Bob Shell integration errors."""


class BobShellNotFoundError(BobRunnerError):
    """Raised when the Bob Shell executable cannot be found."""


class BobExecutionError(BobRunnerError):
    """Raised when Bob Shell exits unsuccessfully."""


class BobOutputError(BobRunnerError):
    """Raised when Bob Shell does not return the expected structured output."""


class BobTimeoutError(BobRunnerError):
    """Raised when a Bob Shell task exceeds its execution timeout."""


@dataclass(slots=True)
class BobRunResult:
    success: bool
    status: str
    timestamp: str | None
    task_id: str | None
    last_message: str
    stats: dict[str, Any]
    return_code: int
    stderr: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BobRunner:
    """
    Small, deterministic adapter around IBM Bob Shell.

    NoRepeat uses Bob Shell in non-interactive mode so the Flask backend can
    invoke Bob programmatically. The prompt is sent through stdin instead of
    command-line arguments, which avoids quoting problems on Windows and keeps
    long prompts out of the process command line.
    """

    def __init__(
        self,
        *,
        project_root: str | Path | None = None,
        bob_executable: str | None = None,
        mode: str = DEFAULT_MODE,
        max_cost: float = DEFAULT_MAX_COST,
        max_turns: int = DEFAULT_MAX_TURNS,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        disable_mcp: bool = True,
        disable_subagents: bool = True,
    ) -> None:
        self.project_root = Path(project_root or PROJECT_ROOT).resolve()
        self.mode = mode.strip() or "agent"
        self.max_cost = float(max_cost)
        self.max_turns = int(max_turns)
        self.timeout_seconds = int(timeout_seconds)
        self.disable_mcp = bool(disable_mcp)
        self.disable_subagents = bool(disable_subagents)

        self.team_id = os.getenv("BOB_TEAM_ID", "").strip() or None

        self.bob_executable = self._resolve_executable(
            bob_executable
        )

        if not self.project_root.exists() or not self.project_root.is_dir():
            raise BobRunnerError(
                f"NoRepeat project root does not exist: "
                f"{self.project_root}"
            )

        if self.max_cost <= 0:
            raise BobRunnerError(
                "Bob max_cost must be greater than zero."
            )

        if self.max_turns <= 0:
            raise BobRunnerError(
                "Bob max_turns must be greater than zero."
            )

        if self.timeout_seconds <= 0:
            raise BobRunnerError(
                "Bob timeout must be greater than zero."
            )

    @staticmethod
    def _resolve_executable(
        explicit: str | None,
    ) -> str:
        if explicit:
            candidate = Path(explicit).expanduser()

            if candidate.exists():
                return str(candidate.resolve())

            located = shutil.which(explicit)

            if located:
                return located

            raise BobShellNotFoundError(
                f"IBM Bob Shell executable was not found: "
                f"{explicit}"
            )

        env_executable = os.getenv(
            "BOB_CLI_PATH",
            "",
        ).strip()

        if env_executable:
            candidate = Path(
                env_executable
            ).expanduser()

            if candidate.exists():
                return str(candidate.resolve())

            located = shutil.which(
                env_executable
            )

            if located:
                return located

        located = shutil.which("bob")

        if located:
            return located

        raise BobShellNotFoundError(
            "IBM Bob Shell was not found in PATH. "
            "Install Bob Shell or set BOB_CLI_PATH "
            "to the executable path."
        )

    def diagnostics(self) -> dict[str, Any]:
        """
        Return local Bob Shell integration diagnostics.

        Does not consume Bobcoins.
        """
        version = self._read_version()

        api_key_present = bool(
            os.getenv("BOB_API_KEY", "").strip()
        )

        return {
            "available": True,
            "executable": self.bob_executable,
            "version": version,
            "project_root": str(self.project_root),
            "mode": self.mode,
            "env_file": str(ENV_FILE),
            "env_file_present": ENV_FILE.is_file(),
            "api_key_present": api_key_present,
            "team_id_present": bool(self.team_id),
            "max_cost": self.max_cost,
            "max_turns": self.max_turns,
            "timeout_seconds": self.timeout_seconds,
        }

    def _read_version(self) -> str | None:
        try:
            completed = subprocess.run(
                [
                    self.bob_executable,
                    "--version",
                ],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
                check=False,
            )

        except (
            OSError,
            subprocess.SubprocessError,
        ):
            return None

        output = (
            completed.stdout
            or completed.stderr
            or ""
        ).strip()

        return output or None

    def _build_command(
        self,
        *,
        max_cost: float,
        max_turns: int,
        disable_subagents: bool,
    ) -> list[str]:

        command = [
            self.bob_executable,
            "run",
            "--format",
            "json",
            "--mode",
            self.mode,
            "--max-cost",
            f"{max_cost:.3f}",
            "--max-turns",
            str(max_turns),
            "--workspace",
            str(self.project_root),
            "--log-level",
            "error",
            "--trust",
            "--accept-license",
        ]

        if self.disable_mcp:
            command.append(
                "--disable-mcp"
            )

        if disable_subagents:
            command.append(
                "--disable-subagents"
            )

        if self.team_id:
            command.extend(
                [
                    "--team-id",
                    self.team_id,
                ]
            )

        return command

    @staticmethod
    def _parse_json_result(
        stdout: str,
    ) -> dict[str, Any]:

        raw = stdout.strip()

        if not raw:
            raise BobOutputError(
                "Bob Shell returned empty stdout."
            )

        candidates = [raw]

        candidates.extend(
            line.strip()
            for line in reversed(
                raw.splitlines()
            )
            if line.strip().startswith("{")
            and line.strip().endswith("}")
        )

        for candidate in candidates:

            try:
                payload = json.loads(
                    candidate
                )

            except json.JSONDecodeError:
                continue

            if (
                isinstance(payload, dict)
                and payload.get("type")
                == "result"
            ):
                return payload

        raise BobOutputError(
            "Bob Shell stdout did not contain "
            "a valid --format json result object."
        )

    def run(
        self,
        prompt: str,
        *,
        max_cost: float | None = None,
        max_turns: int | None = None,
        timeout_seconds: int | None = None,
        allow_subagents: bool = False,
    ) -> BobRunResult:

        if (
            not isinstance(prompt, str)
            or not prompt.strip()
        ):
            raise BobRunnerError(
                "Bob prompt must be a non-empty string."
            )

        # Fail fast before launching Bob Shell.
        # Never expose the API key in logs or command arguments.
        if not os.getenv(
            "BOB_API_KEY",
            "",
        ).strip():

            raise BobRunnerError(
                "BOB_API_KEY is not configured. "
                "For local development, add it "
                "to NoRepeat/.env. "
                "For Railway, configure "
                "BOB_API_KEY as a service "
                "environment variable."
            )

        effective_cost = (
            self.max_cost
            if max_cost is None
            else float(max_cost)
        )

        effective_turns = (
            self.max_turns
            if max_turns is None
            else int(max_turns)
        )

        effective_timeout = (
            self.timeout_seconds
            if timeout_seconds is None
            else int(timeout_seconds)
        )

        if effective_cost <= 0:
            raise BobRunnerError(
                "Bob max_cost must be greater than zero."
            )

        if effective_turns <= 0:
            raise BobRunnerError(
                "Bob max_turns must be greater than zero."
            )

        if effective_timeout <= 0:
            raise BobRunnerError(
                "Bob timeout must be greater than zero."
            )

        command = self._build_command(
            max_cost=effective_cost,
            max_turns=effective_turns,
            disable_subagents=(
                self.disable_subagents
                and not allow_subagents
            ),
        )

        environment = os.environ.copy()

        environment.setdefault(
            "PYTHONUTF8",
            "1",
        )

        try:
            completed = subprocess.run(
                command,
                input=prompt.strip() + "\n",
                cwd=self.project_root,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=effective_timeout,
                check=False,
            )

        except subprocess.TimeoutExpired as exc:

            raise BobTimeoutError(
                "IBM Bob Shell exceeded the "
                f"{effective_timeout}s timeout."
            ) from exc

        except OSError as exc:

            raise BobExecutionError(
                "IBM Bob Shell could not be started: "
                f"{exc}"
            ) from exc

        stdout = completed.stdout or ""

        stderr = (
            completed.stderr
            or ""
        ).strip()

        try:
            payload = self._parse_json_result(
                stdout
            )

        except BobOutputError:

            if completed.returncode != 0:

                detail = (
                    stderr
                    or stdout.strip()
                    or "No error output was returned."
                )

                raise BobExecutionError(
                    "IBM Bob Shell exited with code "
                    f"{completed.returncode}: "
                    f"{detail}"
                )

            raise

        stats = payload.get("stats")

        if not isinstance(
            stats,
            dict,
        ):
            stats = {}

        status = str(
            payload.get("status")
            or "error"
        )

        success = (
            completed.returncode == 0
            and status == "success"
        )

        result = BobRunResult(
            success=success,
            status=status,
            timestamp=(
                str(payload.get("timestamp"))
                if payload.get("timestamp")
                is not None
                else None
            ),
            task_id=(
                str(stats.get("task_id"))
                if stats.get("task_id")
                is not None
                else None
            ),
            last_message=str(
                payload.get(
                    "last_message"
                )
                or ""
            ),
            stats=stats,
            return_code=(
                completed.returncode
            ),
            stderr=stderr,
        )

        if not success:

            detail = (
                result.last_message
                or stderr
                or "Bob reported an error."
            )

            raise BobExecutionError(
                "IBM Bob task failed "
                f"(status={status}, "
                f"exit={completed.returncode}): "
                f"{detail}"
            )

        return result

    def run_norepeat(
        self,
        task_prompt: str,
        *,
        max_cost: float | None = None,
        max_turns: int | None = None,
        timeout_seconds: int | None = None,
        allow_subagents: bool = False,
    ) -> BobRunResult:

        if (
            not isinstance(
                task_prompt,
                str,
            )
            or not task_prompt.strip()
        ):
            raise BobRunnerError(
                "NoRepeat task prompt must "
                "be a non-empty string."
            )

        prompt = f"""
You are executing an automated NoRepeat task inside the NoRepeat project workspace.

Before acting, read and follow these project sources:
- @AGENTS.md
- @.bob/rules-norepeat/security-rules.md
- @.bob/skills/norepeat/SKILL.md

Treat files under workspaces/<session_id>/repository/ as the candidate project.

Do not modify NoRepeat's own runtime implementation in core/,
backend_api.py, or dashboard.py unless the task explicitly says it is
a runtime-integration task.

TASK
{task_prompt.strip()}
""".strip()

        return self.run(
            prompt,
            max_cost=max_cost,
            max_turns=max_turns,
            timeout_seconds=timeout_seconds,
            allow_subagents=allow_subagents,
        )

    def smoke_test(self) -> BobRunResult:
        """
        Small connectivity test.

        This consumes a very small amount of Bobcoins.
        """

        prompt = """
You are running a NoRepeat IBM Bob Shell connectivity test.

Do not inspect or modify project files.
Do not call tools.

Reply with exactly:

NOREPEAT_BOB_OK
""".strip()

        return self.run(
            prompt,
            max_cost=min(
                self.max_cost,
                0.05,
            ),
            max_turns=1,
            timeout_seconds=min(
                self.timeout_seconds,
                120,
            ),
            allow_subagents=False,
        )


def get_bob_runner() -> BobRunner:
    return BobRunner()


if __name__ == "__main__":

    try:
        runner = get_bob_runner()

        print(
            json.dumps(
                runner.diagnostics(),
                indent=2,
                ensure_ascii=False,
            )
        )

    except BobRunnerError as exc:

        print(
            json.dumps(
                {
                    "available": False,
                    "error": str(exc),
                },
                indent=2,
                ensure_ascii=False,
            )
        )

        raise SystemExit(1)