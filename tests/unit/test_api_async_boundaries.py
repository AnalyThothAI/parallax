import ast
from pathlib import Path

HTTP_METHODS = {"delete", "get", "patch", "post", "put"}


def test_api_http_routes_use_sync_boundary_for_blocking_read_models() -> None:
    source = Path("src/gmgn_twitter_intel/app/surfaces/api/http.py").read_text(encoding="utf-8")
    async_routes = [
        route.name
        for route in _api_route_functions(source, outer_function_name="create_api_router")
        if isinstance(route, ast.AsyncFunctionDef)
    ]

    assert async_routes == []


def test_api_surface_does_not_manually_offload_sync_repository_reads() -> None:
    source = Path("src/gmgn_twitter_intel/app/surfaces/api/http.py").read_text(encoding="utf-8")

    assert "asyncio.to_thread" not in source


def test_readyz_uses_sync_route_boundary() -> None:
    source = Path("src/gmgn_twitter_intel/app/runtime/app.py").read_text(encoding="utf-8")
    routes = _api_route_functions(source, outer_function_name="create_app")
    readyz = next(route for route in routes if route.name == "readyz")

    assert isinstance(readyz, ast.FunctionDef)


def test_runtime_splits_db_pools_by_execution_role() -> None:
    app_source = Path("src/gmgn_twitter_intel/app/runtime/app.py").read_text(encoding="utf-8")
    source = Path("src/gmgn_twitter_intel/app/runtime/bootstrap.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    runtime_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Runtime")
    fields = {
        statement.target.id
        for statement in runtime_class.body
        if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name)
    }

    assert {"settings", "db", "telemetry", "providers", "hub", "workers", "scheduler"} <= fields
    assert "api_db_pool" not in fields
    assert "worker_db_pool" not in fields
    assert "wake_db_pool" not in fields
    assert "DBPoolBundle.create(settings, telemetry=telemetry)" in source
    assert "db.api_session()" in source
    assert "db.worker_session(" in source
    assert "_build_runtime" not in app_source
    assert "_start_runtime_tasks" not in app_source
    assert "_stop_runtime" not in app_source


def _api_route_functions(source: str, *, outer_function_name: str) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(source)
    outer = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == outer_function_name
    )
    return [
        node
        for node in ast.walk(outer)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and _is_http_route(node)
    ]


def _is_http_route(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(_is_http_route_decorator(decorator) for decorator in node.decorator_list)


def _is_http_route_decorator(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    function = node.func
    return (
        isinstance(function, ast.Attribute)
        and function.attr in HTTP_METHODS
        and isinstance(function.value, ast.Name)
        and function.value.id in {"app", "router"}
    )
