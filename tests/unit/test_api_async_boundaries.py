import ast
from pathlib import Path

API_DIR = Path("src/parallax/app/surfaces/api")
HTTP_METHODS = {"delete", "get", "patch", "post", "put"}


def test_api_http_routes_use_sync_boundary_for_blocking_read_models() -> None:
    async_routes = [
        f"{path}:{route.name}"
        for path in _api_route_paths()
        for route in _api_route_functions(path.read_text(encoding="utf-8"))
        if isinstance(route, ast.AsyncFunctionDef)
    ]

    assert async_routes == []


def test_api_surface_does_not_manually_offload_sync_repository_reads() -> None:
    offenders = [
        str(path)
        for path in [API_DIR / "http.py", *_api_route_paths()]
        if "asyncio.to_thread" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []


def test_readyz_uses_sync_route_boundary() -> None:
    source = Path("src/parallax/app/runtime/app.py").read_text(encoding="utf-8")
    routes = _api_route_functions(source, outer_function_name="create_app")
    readyz = next(route for route in routes if route.name == "readyz")

    assert isinstance(readyz, ast.FunctionDef)


def test_runtime_splits_db_pools_by_execution_role() -> None:
    app_source = Path("src/parallax/app/runtime/app.py").read_text(encoding="utf-8")
    source = Path("src/parallax/app/runtime/bootstrap.py").read_text(encoding="utf-8")
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


def _api_route_paths() -> list[Path]:
    return sorted(API_DIR.glob("routes_*.py"))


def _api_route_functions(
    source: str,
    *,
    outer_function_name: str | None = None,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    tree = ast.parse(source)
    outer: ast.AST = tree
    if outer_function_name is not None:
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
