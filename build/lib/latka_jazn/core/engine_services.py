from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class EngineServices:
    """Compatibility seams for staged JaznEngine decomposition.

    v108 does not transfer ownership. These fields expose the already-existing
    collaborators so later releases can extract them behind typed coordinators
    without rebuilding a second runtime.
    """

    memory: Any
    cognition: Any
    route_registry: Any
    route_dispatcher: Any
    affect: Any
    generation: Any
    validation: Any
    diagnostics: Any | None = None
    recovery: Any | None = None
    finalization: Any | None = None
    persistence: Any | None = None

    @classmethod
    def from_legacy_engine(
        cls,
        engine: Any,
        *,
        diagnostics: Any | None = None,
    ) -> "EngineServices":
        return cls(
            memory=getattr(engine, "living_memory_gateway", None),
            cognition=getattr(engine, "cognitive_runtime_coordinator", None),
            route_registry=getattr(engine, "route_registry", None),
            route_dispatcher=getattr(engine, "route_handler_dispatcher", None),
            affect=getattr(engine, "affective_granularity", None),
            generation=getattr(engine, "runtime_response_synthesizer", None),
            validation=getattr(engine, "runtime_answer_validator", None),
            diagnostics=diagnostics,
        )

    def readiness(self) -> dict[str, bool]:
        return {
            "memory": self.memory is not None,
            "cognition": self.cognition is not None,
            "route_registry": self.route_registry is not None,
            "route_dispatcher": self.route_dispatcher is not None,
            "affect": self.affect is not None,
            "generation": self.generation is not None,
            "validation": self.validation is not None,
            "diagnostics": self.diagnostics is not None,
            "recovery": self.recovery is not None,
            "finalization": self.finalization is not None,
            "persistence": self.persistence is not None,
        }
