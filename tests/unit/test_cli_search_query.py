import pytest

from parallax import cli
from parallax.app.surfaces.cli.parser import build_parser


def test_root_cli_exports_only_main():
    assert cli.__all__ == ["main"]
    assert not hasattr(cli, "build_parser")


def test_cli_commands_use_runtime_repository_session():
    from parallax.app.runtime import repository_session
    from parallax.app.surfaces.cli.commands import db, ops, read_models

    assert not hasattr(db, "_postgres_connection")
    assert not hasattr(db, "_repositories")
    assert db.postgres_connection is repository_session.postgres_connection
    assert ops.repositories is repository_session.repositories
    assert read_models.repositories is repository_session.repositories


def test_search_accepts_positional_query_and_cursor():
    args = build_parser().parse_args(["search", "btc", "--window", "4h", "--cursor", "0.1:100:event-1"])

    assert args.command == "search"
    assert args.query == "btc"
    assert args.window == "4h"
    assert args.cursor == "0.1:100:event-1"


def test_search_parser_owns_default_window():
    args = build_parser().parse_args(["search", "btc"])

    assert args.window == "24h"


@pytest.mark.parametrize("removed", ["--symbol", "--ca", "--chain", "--handle"])
def test_search_removed_filter_flags_are_not_registered(removed):
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["search", "btc", removed, "PEPE"])


def test_search_help_documents_cursor_and_not_removed_filters(capsys):
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["search", "--help"])
    output = capsys.readouterr().out

    assert "--cursor" in output
    assert "--window" in output
    assert "--symbol" not in output
    assert "--ca" not in output
    assert "--chain" not in output
    assert "--handle" not in output
