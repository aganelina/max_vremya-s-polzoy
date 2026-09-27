import ast
from pathlib import Path

from app.worker.jobs import HANDLERS

APP = Path(__file__).resolve().parents[2] / "app"
ENQUEUERS = {"enqueue", "fan_out"}

def _enqueued_kinds() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or len(node.args) < 2:
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            kind = node.args[1]
            if name in ENQUEUERS and isinstance(kind, ast.Constant) and isinstance(kind.value, str):
                found[kind.value] = f"{path.relative_to(APP.parent)}:{node.lineno}"
    return found

def test_every_enqueued_kind_has_handler() -> None:
    kinds = _enqueued_kinds()
    assert len(kinds) >= 10
    missing = {k: where for k, where in kinds.items() if k not in HANDLERS}
    assert missing == {}
