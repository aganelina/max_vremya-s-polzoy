import json
from pathlib import Path

from app.main import create_app, export_openapi

FILE = Path(__file__).resolve().parents[2] / "openapi" / "openapi.json"

def test_committed_openapi_is_up_to_date() -> None:
    current = json.loads(json.dumps(export_openapi(create_app()), ensure_ascii=False))
    assert json.loads(FILE.read_text(encoding="utf-8")) == current, (
        "OpenAPI устарел: APP_ENV=test uv run python -m app.cli export-openapi"
    )
