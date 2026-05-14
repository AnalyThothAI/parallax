import ast
from pathlib import Path


def test_home_hot_read_routes_offload_blocking_read_models() -> None:
    source = Path("src/gmgn_twitter_intel/app/surfaces/api/http.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    for function_name in (
        "recent",
        "status",
        "token_radar",
        "notifications",
        "notification_summary",
        "signal_lab_pulse",
    ):
        route = next(
            node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name
        )
        assert any(_is_asyncio_to_thread_await(node) for node in ast.walk(route)), function_name


def test_readyz_offloads_readiness_probe() -> None:
    source = Path("src/gmgn_twitter_intel/app/runtime/app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    route = next(node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "readyz")

    assert any(_is_asyncio_to_thread_await(node) for node in ast.walk(route))


def _is_asyncio_to_thread_await(node: ast.AST) -> bool:
    if not isinstance(node, ast.Await) or not isinstance(node.value, ast.Call):
        return False
    function = node.value.func
    return (
        isinstance(function, ast.Attribute)
        and function.attr == "to_thread"
        and isinstance(function.value, ast.Name)
        and function.value.id == "asyncio"
    )
