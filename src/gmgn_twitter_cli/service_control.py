from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

SERVICE_LABEL = "com.local.gmgn-twitter-cli"
DEFAULT_INSTALL_DIR = Path.home() / ".local" / "share" / "gmgn-twitter-cli" / "app"


@dataclass(frozen=True, slots=True)
class ServicePaths:
    project_dir: Path
    install_dir: Path = DEFAULT_INSTALL_DIR
    plist_path: Path = Path.home() / "Library" / "LaunchAgents" / f"{SERVICE_LABEL}.plist"

    @property
    def log_dir(self) -> Path:
        return self.install_dir / "logs"

    @property
    def data_dir(self) -> Path:
        return self.install_dir / "data"


class MacLaunchAgentService:
    label = SERVICE_LABEL

    def __init__(self, paths: ServicePaths | None = None, *, stdout: TextIO | None = None):
        self.paths = paths or ServicePaths(project_dir=Path.cwd())
        self.stdout = stdout
        self.uid = os.getuid()

    def install(self, *, start: bool) -> None:
        self._require_uv()
        self._sync_project()
        self._ensure_runtime_files()
        self._run(["uv", "sync", "--frozen"], cwd=self.paths.install_dir)
        self._write_plist()
        self._emit(f"Installed {self.label}")
        self._emit(f"Install dir: {self.paths.install_dir}")
        if start:
            self.start()

    def start(self) -> None:
        self._run(["launchctl", "bootout", f"gui/{self.uid}", str(self.paths.plist_path)], check=False)
        self._run(["launchctl", "bootstrap", f"gui/{self.uid}", str(self.paths.plist_path)])
        self._run(["launchctl", "enable", f"gui/{self.uid}/{self.label}"])
        self._run(["launchctl", "kickstart", "-k", f"gui/{self.uid}/{self.label}"])
        self._emit(f"Started {self.label}")
        self._emit("Health: curl http://127.0.0.1:8765/healthz")

    def stop(self) -> None:
        self._run(["launchctl", "bootout", f"gui/{self.uid}", str(self.paths.plist_path)], check=False)
        self._emit(f"Stopped {self.label}")

    def restart(self) -> None:
        self.stop()
        self.start()

    def status(self) -> int:
        return self._run(["launchctl", "print", f"gui/{self.uid}/{self.label}"], check=False).returncode

    def logs(self, *, lines: int) -> None:
        for path in (self.paths.log_dir / "launchd.stderr.log", self.paths.log_dir / "launchd.stdout.log"):
            if not path.exists():
                continue
            self._emit(f"==> {path}")
            self._emit("\n".join(path.read_text(errors="replace").splitlines()[-lines:]))

    def uninstall(self, *, remove_files: bool) -> None:
        self.stop()
        self.paths.plist_path.unlink(missing_ok=True)
        if remove_files and self.paths.install_dir.exists():
            shutil.rmtree(self.paths.install_dir)
        self._emit(f"Uninstalled {self.label}")

    def render_plist(self) -> str:
        payload = {
            "Label": self.label,
            "WorkingDirectory": str(self.paths.install_dir),
            "ProgramArguments": [
                str(self.paths.install_dir / ".venv" / "bin" / "gmgn-twitter-cli"),
                "serve",
            ],
            "RunAtLoad": True,
            "KeepAlive": True,
            "StandardOutPath": str(self.paths.log_dir / "launchd.stdout.log"),
            "StandardErrorPath": str(self.paths.log_dir / "launchd.stderr.log"),
            "EnvironmentVariables": {
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
            },
        }
        return plistlib.dumps(payload, sort_keys=False).decode()

    def install_plan(self, *, start: bool) -> list[list[str]]:
        commands = []
        if self.paths.project_dir.resolve() != self.paths.install_dir.resolve():
            commands.append(self._rsync_command())
        commands.append(["uv", "sync", "--frozen"])
        if start:
            commands.extend(
                [
                    ["launchctl", "bootout", f"gui/{self.uid}", str(self.paths.plist_path)],
                    ["launchctl", "bootstrap", f"gui/{self.uid}", str(self.paths.plist_path)],
                    ["launchctl", "enable", f"gui/{self.uid}/{self.label}"],
                    ["launchctl", "kickstart", "-k", f"gui/{self.uid}/{self.label}"],
                ]
            )
        return commands

    def _sync_project(self) -> None:
        self.paths.install_dir.mkdir(parents=True, exist_ok=True)
        if self.paths.project_dir.resolve() == self.paths.install_dir.resolve():
            return
        self._run(self._rsync_command())
        source_env = self.paths.project_dir / ".env"
        install_env = self.paths.install_dir / ".env"
        if source_env.exists() and not install_env.exists():
            shutil.copy2(source_env, install_env)

    def _ensure_runtime_files(self) -> None:
        self.paths.plist_path.parent.mkdir(parents=True, exist_ok=True)
        self.paths.log_dir.mkdir(parents=True, exist_ok=True)
        self.paths.data_dir.mkdir(parents=True, exist_ok=True)
        env_path = self.paths.install_dir / ".env"
        if not env_path.exists():
            shutil.copy2(self.paths.install_dir / ".env.example", env_path)
            self._emit(f"Created {env_path} from .env.example. Update WS_TOKEN before exposing the service.")

    def _write_plist(self) -> None:
        self.paths.plist_path.write_text(self.render_plist())

    def _rsync_command(self) -> list[str]:
        return [
            "rsync",
            "-a",
            "--delete",
            "--exclude",
            ".git/",
            "--exclude",
            ".venv/",
            "--exclude",
            ".env",
            "--exclude",
            ".pytest_cache/",
            "--exclude",
            ".ruff_cache/",
            "--exclude",
            "__pycache__/",
            "--exclude",
            "browser_data/",
            "--exclude",
            "data/",
            "--exclude",
            "logs/",
            "--exclude",
            "monitor_running.png",
            f"{self.paths.project_dir}/",
            f"{self.paths.install_dir}/",
        ]

    def _require_uv(self) -> None:
        if shutil.which("uv") is None:
            raise RuntimeError("uv is required. Install it first: https://docs.astral.sh/uv/")

    def _run(self, command: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(command, cwd=cwd, check=check, text=True)

    def _emit(self, message: str) -> None:
        if self.stdout is None:
            print(message)
            return
        self.stdout.write(message + "\n")
