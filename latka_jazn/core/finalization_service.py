from __future__ import annotations

from dataclasses import asdict
from typing import Any

from latka_jazn.config import JaznConfig
from latka_jazn.core.epistemic_decision_ledger import EpistemicDecisionLedger, epistemic_ledger_path
from latka_jazn.core.final_visible_reply_capture import FinalVisibleReplyCapture
from latka_jazn.core.runtime_root import workspace_runtime_path
from latka_jazn.memory.event_ledger import RuntimeEventLedger


class FinalizationService:
    """Persist a verified visible candidate without constructing the cognitive engine.

    Binding, candidate validation, durable claim and settlement remain in the
    canonical host finalization transaction. Construction performs no writes;
    the append-only ledger is opened only after capture validation succeeds.
    """

    def __init__(self, config: JaznConfig, *, event_ledger: RuntimeEventLedger | None = None) -> None:
        self.config = config
        self._event_ledger = event_ledger

    @property
    def event_ledger(self) -> RuntimeEventLedger:
        if self._event_ledger is None:
            self._event_ledger = RuntimeEventLedger(
                self.config.root, version=self.config.version, timezone_name=self.config.timezone,
            )
        return self._event_ledger

    def shutdown(self) -> None:
        """Ledger appends own their file handles; there is no engine lifecycle to stop."""

    def persist_final_visible_reply(
        self,
        *,
        turn_id: str,
        trace_id: str,
        timestamp_header: str,
        timezone: str,
        timestamp_sample_iso: str,
        timestamp_source: str,
        timestamp_trusted: bool,
        author_id: str,
        author_label: str,
        author_source: str,
        final_text: str,
        state_emoticon: str,
        source: str = "chatgpt_visible_layer",
        client_context: dict | None = None,
        runtime_evidence: dict[str, Any] | None = None,
        memory_evidence: dict[str, Any] | None = None,
        external_evidence: dict[str, Any] | None = None,
        generated_evidence: dict[str, Any] | None = None,
    ) -> dict:
        """Persist an externally rendered final only with the verified turn envelope."""
        capture = FinalVisibleReplyCapture.build(
            turn_id=turn_id,
            trace_id=trace_id,
            timestamp_header=timestamp_header,
            timezone=timezone,
            timestamp_sample_iso=timestamp_sample_iso,
            timestamp_source=timestamp_source,
            timestamp_trusted=timestamp_trusted,
            author_id=author_id,
            author_label=author_label,
            author_source=author_source,
            state_emoticon=state_emoticon,
            final_text=final_text,
            source=source,
            config=self.config,
            runtime_evidence=runtime_evidence,
            memory_evidence=memory_evidence,
            external_evidence=external_evidence,
            generated_evidence=generated_evidence,
        )
        envelope_stub = {
            "schema_version": "external_final_visible_reply_envelope/v2",
            "runtime_version": self.config.version,
            "trace": {
                "turn_id": turn_id,
                "trace_id": trace_id,
                "timestamp_header": timestamp_header,
                "timezone": timezone,
                "runtime_mode": "external_visible_layer_capture",
                "client": source,
                "lifecycle": (client_context or {}).get("lifecycle", "one_shot_visible_layer"),
            },
            "final_response_contract": {
                "turn_id": turn_id,
                "trace_id": trace_id,
                "runtime_version": self.config.version,
                "timestamp_header": timestamp_header,
                "timezone": timezone,
                "timestamp_sample_iso": timestamp_sample_iso,
                "timestamp_source": timestamp_source,
                "timestamp_trusted": timestamp_trusted,
                "state_emoticon": state_emoticon,
                "author_id": author_id,
                "author_label": author_label,
                "author_source": author_source,
                "final_visible_text": capture.final_visible_text,
                "schema_version": "external_final_response_contract/v2",
            },
            "dialogue_state": {},
            "affect_mix": {"state_emoticon": state_emoticon},
        }
        ledger_result = self.event_ledger.append_final_visible_reply(
            envelope_stub,
            final_text=capture.final_visible_text,
            source=source,
            client_context=client_context or {},
            local_time_label=timestamp_header,
        )
        if ledger_result is None:
            raise RuntimeError("final_visible_reply_ledger_write_failed")
        capture_payload = capture.to_dict()
        epistemic_ledger_append: list[dict[str, Any]] = []
        if capture.epistemic_claims:
            with EpistemicDecisionLedger(
                epistemic_ledger_path(workspace_runtime_path(self.config.root))
            ) as epistemic_ledger:
                epistemic_ledger_append = [
                    item.to_dict()
                    for item in epistemic_ledger.append_assessments(
                        turn_id=turn_id,
                        trace_id=trace_id,
                        assessments=capture.epistemic_claims,
                    )
                ]
        return {
            **capture_payload,
            "final_visible_reply_capture": dict(capture_payload),
            "ledger_append": asdict(ledger_result),
            "epistemic_ledger_append": epistemic_ledger_append,
        }

