from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from latka_jazn.config import JaznConfig
from latka_jazn.core.engine_construction import EngineRuntimeServices

if TYPE_CHECKING:
    from latka_jazn.core.engine import JaznEngine


class CompositionState(str, Enum):
    NEW = "new"
    BUILT = "built"
    VALIDATED = "validated"
    HYDRATED = "hydrated"
    STARTED = "started"
    FAILED = "failed"
    CLOSED = "closed"


class RuntimeCompositionRoot:
    """Assemble dependencies for the existing session owner, never another session."""

    def __init__(self, config: JaznConfig | None = None) -> None:
        self.config = config or JaznConfig()
        self.state = CompositionState.NEW
        self.services = EngineRuntimeServices(self.config)
        self._engine: JaznEngine | None = None
        self.cleanup_errors: list[str] = []
        self._resources_closed = False

    def _require(self, state: CompositionState) -> None:
        if self.state is not state:
            raise RuntimeError(f"composition_stage_mismatch:{self.state.value}:expected:{state.value}")

    def build(self) -> EngineRuntimeServices:
        self._require(CompositionState.NEW)
        try:
            self.services.build_dependencies()
        except Exception:
            self.state = CompositionState.FAILED
            self._close_partial_resources()
            raise
        self.state = CompositionState.BUILT
        return self.services

    def validate(self) -> None:
        self._require(CompositionState.BUILT)
        if self.services.store is None or self.services.audit_store is None:
            self.state = CompositionState.FAILED
            self._close_partial_resources()
            raise RuntimeError("runtime_composition_stores_not_ready")
        self.state = CompositionState.VALIDATED

    def hydrate(self) -> None:
        self._require(CompositionState.VALIDATED)
        try:
            self.services.hydrate()
        except Exception:
            self.state = CompositionState.FAILED
            self._close_partial_resources()
            raise
        self.state = CompositionState.HYDRATED

    def start(self) -> EngineRuntimeServices:
        self._require(CompositionState.HYDRATED)
        try:
            self.services.start()
        except Exception:
            self.state = CompositionState.FAILED
            self._close_partial_resources()
            raise
        self.state = CompositionState.STARTED
        return self.services

    def create_engine(self) -> JaznEngine:
        from latka_jazn.core.engine import JaznEngine

        if self._engine is not None:
            self._require(CompositionState.STARTED)
            return self._engine
        self.build()
        self.validate()
        self.hydrate()
        self.start()
        self._engine = JaznEngine(self.services)
        return self._engine

    def _close_partial_resources(self) -> None:
        if self._resources_closed:
            return
        self._resources_closed = True
        self.services.ready = False
        for name in ("external_dictionary_adapter", "audit_store", "store"):
            resource = getattr(self.services, name, None)
            close = getattr(resource, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    self.cleanup_errors.append(f"{name}:{type(exc).__name__}:{exc}")

    def close(self) -> None:
        if self.state is CompositionState.CLOSED:
            return
        try:
            if self._engine is not None:
                self._engine.shutdown()
            else:
                self._close_partial_resources()
        finally:
            self.services.ready = False
            self.state = CompositionState.CLOSED
        if self.cleanup_errors:
            raise RuntimeError("composition_cleanup_failed:" + ";".join(self.cleanup_errors))
