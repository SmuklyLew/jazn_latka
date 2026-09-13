from __future__ import annotations

from enum import Enum


class HostExecutorState(str, Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    HOST_EXECUTOR_UNAVAILABLE = "host_executor_unavailable"


class HostEnvironmentState(str, Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    REMOTE_CAPABLE = "remote_capable"
    HANDOFF_REQUIRED = "handoff_required"
    HANDOFF_PENDING = "handoff_pending"
    HANDOFF_ACCEPTED = "handoff_accepted"
    HANDOFF_DECLINED = "handoff_declined"
    UNAVAILABLE = "unavailable"


class HostCommandState(str, Enum):
    NOT_STARTED = "not_started"
    STARTED_UNFINISHED = "started_unfinished"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class HostFilesystemState(str, Enum):
    UNKNOWN = "unknown"
    OBSERVED = "observed"


class HostExecutionRoute(str, Enum):
    NONE = "none"
    LOCAL_EXECUTOR = "local_executor"
    REMOTE_RUNTIME = "remote_runtime"
    HOST_HANDOFF = "host_handoff"


class HostRecoveryAction(str, Enum):
    PROBE_ALTERNATIVE_ONCE = "probe_alternative_once"
    STOP_LOCAL_BOOTSTRAP = "stop_local_bootstrap"
    RESUME_CANONICAL_DISCOVERY = "resume_canonical_discovery"
    DIAGNOSE_LOCAL_COMMAND = "diagnose_local_command"
    USE_REMOTE_RUNTIME_TRANSPORT = "use_remote_runtime_transport"
    REQUEST_EXECUTION_HANDOFF = "request_execution_handoff"
    AWAIT_EXECUTION_HANDOFF = "await_execution_handoff"
    USE_ACCEPTED_EXECUTION_HANDOFF = "use_accepted_execution_handoff"
