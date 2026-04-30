from io import StringIO
from pathlib import Path
from subprocess import CompletedProcess

from gmgn_twitter_cli.service_control import MacLaunchAgentService, ServicePaths


def make_service(tmp_path: Path) -> MacLaunchAgentService:
    paths = ServicePaths(
        project_dir=tmp_path / "repo",
        install_dir=tmp_path / "install",
        plist_path=tmp_path / "agent.plist",
    )
    return MacLaunchAgentService(paths=paths)


def test_macos_plist_runs_installed_cli_service(tmp_path):
    service = make_service(tmp_path)

    plist = service.render_plist()

    assert "<string>com.local.gmgn-twitter-cli</string>" in plist
    assert f"<string>{tmp_path}/install</string>" in plist
    assert f"<string>{tmp_path}/install/.venv/bin/gmgn-twitter-cli</string>" in plist
    assert "<string>serve</string>" in plist


def test_install_plan_preserves_runtime_state_and_uses_launchctl(tmp_path):
    service = make_service(tmp_path)

    plan = service.install_plan(start=True)

    assert plan[0][:3] == ["rsync", "-a", "--delete"]
    assert "--exclude" in plan[0]
    assert ".env" in plan[0]
    assert ["uv", "sync", "--frozen"] in plan
    assert ["launchctl", "bootstrap", f"gui/{service.uid}", str(service.paths.plist_path)] in plan
    assert ["launchctl", "kickstart", "-k", f"gui/{service.uid}/{service.label}"] in plan


def test_stop_is_idempotent_when_launch_agent_is_not_loaded(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    output = StringIO()
    service.stdout = output
    commands = []

    def fake_run(command, *, cwd=None, check=True, quiet=False):
        commands.append(command)
        return CompletedProcess(command, returncode=113)

    monkeypatch.setattr(service, "_run", fake_run)

    service.stop()

    assert commands == [["launchctl", "print", f"gui/{service.uid}/{service.label}"]]
    assert output.getvalue() == f"Already stopped {service.label}\n"


def test_start_skips_bootout_when_launch_agent_is_not_loaded(tmp_path, monkeypatch):
    service = make_service(tmp_path)
    commands = []

    def fake_run(command, *, cwd=None, check=True, quiet=False):
        commands.append(command)
        return CompletedProcess(command, returncode=113 if command[1] == "print" else 0)

    monkeypatch.setattr(service, "_run", fake_run)

    service.start()

    assert commands == [
        ["launchctl", "print", f"gui/{service.uid}/{service.label}"],
        ["launchctl", "bootstrap", f"gui/{service.uid}", str(service.paths.plist_path)],
        ["launchctl", "enable", f"gui/{service.uid}/{service.label}"],
        ["launchctl", "kickstart", "-k", f"gui/{service.uid}/{service.label}"],
    ]
