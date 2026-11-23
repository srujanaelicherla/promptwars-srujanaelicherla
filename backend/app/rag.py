"""Local RAG over bundled synthetic documents. No arbitrary filesystem access."""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

CORPUS_DIR = Path(__file__).resolve().parent / "ai_corpus"
_ALLOWED_SUFFIX = ".md"
_MAX_FILE_BYTES = 64_000
_MAX_FILES = 20
_MAX_CHUNK_CHARS = 800
_HEADING = re.compile(r"^(#{1,3})\s+(.+)$")


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    section: str
    page: str
    text: str
    synthetic: bool
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class Retrieved:
    chunk: Chunk
    score: float


def _cosine(left: list[float] | tuple[float, ...], right: list[float] | tuple[float, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    na = math.sqrt(sum(a * a for a in left))
    nb = math.sqrt(sum(b * b for b in right))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def hashed_embedding(text: str, dims: int = 64) -> list[float]:
    """Deterministic fallback embedding used when Gemini embeddings are not configured."""

    vector = [0.0] * dims
    for token in re.findall(r"[a-z0-9]+", text.casefold()):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % dims
        vector[index] += 1.0
    return vector


class HashEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [hashed_embedding(item) for item in texts]


def _split_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading = "Preamble"
    buf: list[str] = []
    for line in text.splitlines():
        match = _HEADING.match(line.strip())
        if match:
            if buf:
                sections.append((heading, "\n".join(buf).strip()))
                buf = []
            heading = match.group(2).strip()
            buf.append(line)
            continue
        buf.append(line)
    if buf:
        sections.append((heading, "\n".join(buf).strip()))
    return [(title, body) for title, body in sections if body]


def _chunks_from_section(doc_id: str, title: str, section: str, body: str, page: int) -> list[tuple[str, str, str, str, str]]:
    pieces: list[tuple[str, str, str, str, str]] = []
    remaining = body
    part = 0
    while remaining:
        piece = remaining[:_MAX_CHUNK_CHARS]
        remaining = remaining[_MAX_CHUNK_CHARS:]
        part += 1
        label = section if part == 1 else f"{section} (cont. {part})"
        chunk_id = f"{doc_id}-{page}-{part}"
        pieces.append((chunk_id, doc_id, title, label, piece))
    return pieces


def load_corpus(directory: Path = CORPUS_DIR) -> list[tuple[str, str, str, str, str]]:
    """Return (chunk_id, doc_id, title, section, text) from bundled markdown only."""

    resolved = directory.resolve()
    if resolved != CORPUS_DIR.resolve():
        raise ValueError("RAG corpus path is outside the allowed directory")
    if not resolved.is_dir():
        return []
    files = sorted(path for path in resolved.iterdir() if path.is_file())
    if len(files) > _MAX_FILES:
        files = files[:_MAX_FILES]
    records: list[tuple[str, str, str, str, str]] = []
    for path in files:
        if path.suffix != _ALLOWED_SUFFIX:
            continue
        if path.stat().st_size > _MAX_FILE_BYTES:
            continue
        text = path.read_text(encoding="utf-8")
        title = path.stem.replace("-", " ")
        page = 0
        for section, body in _split_sections(text):
            page += 1
            records.extend(_chunks_from_section(path.stem, title, section, body, page))
    return records


def build_index(embedder: Embedder, directory: Path = CORPUS_DIR) -> list[Chunk]:
    raw = load_corpus(directory)
    if not raw:
        return []
    vectors = embedder.embed([item[4] for item in raw])
    chunks: list[Chunk] = []
    for (chunk_id, doc_id, title, section, text), vector in zip(raw, vectors, strict=True):
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                title=title,
                section=section,
                page=section,
                text=text,
                synthetic=True,
                embedding=tuple(vector),
            )
        )
    return chunks


def retrieve(index: list[Chunk], query_vector: list[float], *, limit: int = 4, floor: float = 0.12) -> list[Retrieved]:
    scored = [Retrieved(chunk=chunk, score=_cosine(query_vector, chunk.embedding)) for chunk in index]
    scored.sort(key=lambda item: (-item.score, item.chunk.chunk_id))
    return [item for item in scored if item.score >= floor][:limit]
