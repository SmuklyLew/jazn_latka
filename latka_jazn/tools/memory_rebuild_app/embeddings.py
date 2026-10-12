from __future__ import annotations

"""Optional embedding boundary; FTS5 remains the required retrieval baseline."""

from array import array
from math import sqrt
from typing import Protocol, Sequence


class EmbeddingProvider(Protocol):
    model_id: str
    dimensions: int

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


def pack_vector(vector: Sequence[float]) -> bytes:
    values = array("f", (float(item) for item in vector))
    return values.tobytes()


def unpack_vector(blob: bytes, dimensions: int) -> tuple[float, ...]:
    values = array("f")
    values.frombytes(blob)
    if len(values) != dimensions:
        raise ValueError("Embedding blob dimension mismatch")
    return tuple(float(item) for item in values)


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Cosine similarity requires equal non-empty vectors")
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = sqrt(sum(float(item) ** 2 for item in left))
    right_norm = sqrt(sum(float(item) ** 2 for item in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


__all__ = ["EmbeddingProvider", "cosine_similarity", "pack_vector", "unpack_vector"]
