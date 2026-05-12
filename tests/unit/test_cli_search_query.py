import pytest

from gmgn_twitter_intel.cli import build_parser


def test_search_accepts_positional_query_and_cursor():
    args = build_parser().parse_args(["search", "btc", "--cursor", "0.1:100:event-1"])

    assert args.command == "search"
    assert args.query == "btc"
    assert args.cursor == "0.1:100:event-1"


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
    assert "--symbol" not in output
    assert "--ca" not in output
    assert "--chain" not in output
    assert "--handle" not in output
