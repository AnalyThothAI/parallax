import ast
from pathlib import Path


def test_token_radar_route_offloads_blocking_read_model() -> None:
    source = Path("src/gmgn_twitter_intel/app/surfaces/api/http.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    token_radar = next(
        node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef) and node.name == "token_radar"
    )

    assert any(_is_asyncio_to_thread_await(node) for node in ast.walk(token_radar))


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
