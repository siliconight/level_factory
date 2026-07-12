"""Adapter registry.

Maps ``adapter_id`` to a concrete adapter instance. Kept tiny and explicit so
adding a tool is a one-line change and there is no import-time magic.
"""
from __future__ import annotations

from packages.adapters.sdk import ToolAdapter


def build_default_registry() -> dict[str, ToolAdapter]:
    # Imported lazily to avoid a package<->adapters import cycle at module load.
    from adapters.deli_counter import DeliCounterAdapter
    from adapters.dispatch import DispatchAdapter
    from adapters.laser_tag import LaserTagAdapter
    from adapters.lot import LotAdapter

    instances: list[ToolAdapter] = [
        DeliCounterAdapter(),
        LotAdapter(),
        LaserTagAdapter(),
        DispatchAdapter(),
    ]
    return {a.adapter_id: a for a in instances}


class AdapterRegistry:
    def __init__(self, adapters: dict[str, ToolAdapter] | None = None) -> None:
        self._adapters = adapters if adapters is not None else build_default_registry()

    def get(self, adapter_id: str) -> ToolAdapter:
        try:
            return self._adapters[adapter_id]
        except KeyError as exc:
            raise KeyError(f"no adapter registered for '{adapter_id}'") from exc

    def ids(self) -> list[str]:
        return sorted(self._adapters)

    def register(self, adapter: ToolAdapter) -> None:
        self._adapters[adapter.adapter_id] = adapter

    def __contains__(self, adapter_id: str) -> bool:
        return adapter_id in self._adapters
