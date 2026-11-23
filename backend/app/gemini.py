"""Gemini client wrapper. Credentials stay in the process environment."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ValidationError

from app.bookings import BookingError

logger = logging.getLogger("lablink")

_DEFAULT_MODEL = "gemini-3.5-flash-lite"
_DEFAULT_EMBED_MODEL = "gemini-embedding-001"
_MAX_OUTPUT_TOKENS = 1024
_TIMEOUT_SECONDS = 15.0
_RETRIES = 2


class AIClient(Protocol):
    def generate_json(self, *, system: str, user: str) -> dict[str, object]: ...

    def generate_text(self, *, system: str, user: str) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def load_gemini_key_from_file(path: Path) -> None:
    """Set GEMINI_API_KEY from a dotenv file when the process does not already have one."""

    if os.environ.get("GEMINI_API_KEY", "").strip():
        return
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() != "GEMINI_API_KEY":
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        value = value.strip()
        if value:
            os.environ["GEMINI_API_KEY"] = value
        return


def api_key_from_env() -> str | None:
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        raw = os.environ.get(name, "").strip()
        if raw:
            return raw
    return None


class GeminiError(BookingError):
    pass


def _unusable() -> BookingError:
    return BookingError(502, "request_failed", "The model returned an unusable result.")


def _timeout() -> BookingError:
    return BookingError(504, "request_failed", "The AI request timed out.")


def _quota() -> BookingError:
    return BookingError(503, "unavailable", "The AI service is temporarily unavailable.")


class GeminiClient:
    def __init__(self, api_key: str, model: str | None = None) -> None:
        from google import genai
        from google.genai import types

        self._types = types
        self._model = model or os.environ.get("GEMINI_MODEL", _DEFAULT_MODEL)
        self._embed_model = os.environ.get("GEMINI_EMBED_MODEL", _DEFAULT_EMBED_MODEL)
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=int(_TIMEOUT_SECONDS * 1000)))

    def generate_json(self, *, system: str, user: str) -> dict[str, object]:
        text = self._complete(system=system, user=user, json_mode=True)
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise _unusable() from exc
        if not isinstance(parsed, dict):
            raise _unusable()
        return parsed

    def generate_text(self, *, system: str, user: str) -> str:
        return self._complete(system=system, user=user, json_mode=False)

    def embed(self, texts: list[str]) -> list[list[float]]:
        last: Exception | None = None
        for _attempt in range(_RETRIES):
            try:
                result = self._client.models.embed_content(model=self._embed_model, contents=texts)
                embeddings = getattr(result, "embeddings", None)
                if not embeddings:
                    raise _unusable()
                vectors: list[list[float]] = []
                for item in embeddings:
                    values = getattr(item, "values", None)
                    if not values:
                        raise _unusable()
                    vectors.append([float(value) for value in values])
                return vectors
            except BookingError:
                raise
            except Exception as exc:
                last = exc
                name = type(exc).__name__.casefold()
                if "timeout" in name:
                    last = _timeout()
                    continue
                if "429" in name or "resourceexhausted" in name.casefold():
                    last = _quota()
                    continue
                logger.info("Gemini embed failed: %s", type(exc).__name__)
                raise BookingError(503, "unavailable", "The AI service is unavailable.") from exc
        if isinstance(last, BookingError):
            raise last
        raise _timeout()

    def _complete(self, *, system: str, user: str, json_mode: bool) -> str:
        config_kwargs: dict[str, object] = {
            "system_instruction": system,
            "temperature": 0.2,
            "max_output_tokens": _MAX_OUTPUT_TOKENS,
        }
        if json_mode:
            config_kwargs["response_mime_type"] = "application/json"
        last: Exception | None = None
        for _attempt in range(_RETRIES):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=user,
                    config=self._types.GenerateContentConfig(**config_kwargs),
                )
                text = getattr(response, "text", None)
                if not isinstance(text, str) or text.strip() == "":
                    raise _unusable()
                return text
            except BookingError:
                raise
            except Exception as exc:
                last = exc
                name = type(exc).__name__.casefold()
                if "timeout" in name:
                    last = _timeout()
                    continue
                if "429" in name or "resourceexhausted" in name:
                    last = _quota()
                    continue
                logger.info("Gemini generate failed: %s", type(exc).__name__)
                raise BookingError(503, "unavailable", "The AI service is unavailable.") from exc
        if isinstance(last, BookingError):
            raise last
        raise _timeout()


def require_ai(state: object) -> AIClient:
    client = getattr(state, "ai_client", None)
    if client is None:
        raise BookingError(503, "unavailable", "AI is not configured.")
    return client


def parse_model(model_type: type[BaseModel], payload: dict[str, object]) -> BaseModel:
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise _unusable() from exc
