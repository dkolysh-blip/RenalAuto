from __future__ import annotations

from ..config import Settings
from .base import Source, SourceError
from .dongchedi import DongchediSource
from .encar import EncarSource

REGISTRY: dict[str, type[Source]] = {
    EncarSource.name: EncarSource,
    DongchediSource.name: DongchediSource,
}


def build_sources(settings: Settings) -> dict[str, Source]:
    unknown = [name for name in settings.sources if name not in REGISTRY]
    if unknown:
        raise ValueError(f"Unknown sources: {unknown}. Available: {sorted(REGISTRY)}")
    return {name: REGISTRY[name](settings) for name in settings.sources}


__all__ = ["REGISTRY", "Source", "SourceError", "build_sources"]
