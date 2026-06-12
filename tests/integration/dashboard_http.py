from __future__ import annotations

import json
from dataclasses import dataclass
from http.client import HTTPConnection
from urllib.parse import urlparse

from pydantic import TypeAdapter

type JsonValue = (
    None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]
)
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class HttpJsonResponse:
    status: int
    content_type: str
    payload: JsonObject


@dataclass(frozen=True, slots=True)
class HttpTextResponse:
    status: int
    content_type: str
    body: str


JSON_OBJECT: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)


def get_json(url: str) -> HttpJsonResponse:
    parsed = urlparse(url)
    connection = HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port or 80)
    try:
        connection.request(
            "GET",
            parsed.path,
            headers={"Accept": "application/json"},
        )
        response = connection.getresponse()
        body = response.read().decode()
        payload = JSON_OBJECT.validate_json(body)
        return HttpJsonResponse(
            status=response.status,
            content_type=response.headers.get("content-type", ""),
            payload=payload,
        )
    finally:
        connection.close()


def get_text(url: str) -> HttpTextResponse:
    parsed = urlparse(url)
    connection = HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port or 80)
    try:
        connection.request("GET", parsed.path)
        response = connection.getresponse()
        return HttpTextResponse(
            status=response.status,
            content_type=response.headers.get("content-type", ""),
            body=response.read().decode(),
        )
    finally:
        connection.close()


def post_json(url: str, payload: JsonObject) -> HttpJsonResponse:
    parsed = urlparse(url)
    connection = HTTPConnection(parsed.hostname or "127.0.0.1", parsed.port or 80)
    try:
        body = json.dumps(payload).encode()
        connection.request(
            "POST",
            parsed.path,
            body=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        response_body = response.read().decode()
        parsed_payload = JSON_OBJECT.validate_json(response_body)
        return HttpJsonResponse(
            status=response.status,
            content_type=response.headers.get("content-type", ""),
            payload=parsed_payload,
        )
    finally:
        connection.close()
