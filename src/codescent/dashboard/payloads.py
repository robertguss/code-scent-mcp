from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)
type JsonObject = dict[str, JsonValue]

JSON_OBJECT: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)
DASHBOARD_API_ROUTES = (
    "/api/status",
    "/api/findings",
    "/api/progress",
    "/api/precision",
    "/api/rules",
    "/api/reports",
    "/api/exports",
)


def string_list(value: JsonValue) -> list[str] | None:
    if not isinstance(value, list):
        return None
    strings: list[str] = []
    for item in value:
        if not isinstance(item, str):
            return None
        strings.append(item)
    return strings


def json_int_map(values: dict[str, int]) -> JsonObject:
    result: JsonObject = {}
    for key, value in values.items():
        result[key] = value
    return result


def asset_text(relative_path: str) -> str:
    asset_root = Path(__file__).parent
    asset_path = (asset_root / relative_path).resolve()
    if not asset_path.is_relative_to(asset_root.resolve()):
        raise FileNotFoundError(relative_path)
    return asset_path.read_text()
