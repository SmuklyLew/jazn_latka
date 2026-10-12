from __future__ import annotations
from dataclasses import dataclass, asdict
@dataclass(slots=True)
class AudioSessionLedgerEntry:
    session_id: str
    status: str = "not_started"
    schema_version: str = "audio_session_ledger/v15.1.0.3.89"
    def to_dict(self): return asdict(self)
