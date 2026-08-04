from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from time import monotonic_ns, perf_counter
from typing import Any, Mapping
import email.utils
import json, os, platform, urllib.request

from .timestamp_policy import (
    TIMESTAMP_LOCAL_FALLBACK_ALLOWED_DEFAULT,
    TIMESTAMP_MAX_AGE_SECONDS,
    TIMESTAMP_NETWORK_FIRST_DEFAULT,
    TIMESTAMP_NETWORK_TIMEOUT_SECONDS,
    timestamp_runtime_policy,
)
from .visible_message_format import render_clock_header

POLISH_WEEKDAYS = {
    0: "poniedziałek", 1: "wtorek", 2: "środa", 3: "czwartek",
    4: "piątek", 5: "sobota", 6: "niedziela"
}

# Canonical env var plus host-loader aliases.  These values must be supplied
# explicitly by the ChatGPT/OpenAI host, wrapper, or another trusted launcher.
# The runtime never promotes the local machine clock to trusted host time.
TRUSTED_HOST_TIME_ISO_ENV_NAMES = (
    "JAZN_TRUSTED_TIME_ISO",
    "JAZN_HOST_TIME_ISO",
    "CHATGPT_HOST_TIME_ISO",
    "OPENAI_HOST_TIME_ISO",
)
TRUSTED_HOST_TIME_SOURCE_ENV_NAMES = (
    "JAZN_TRUSTED_TIME_SOURCE",
    "JAZN_HOST_TIME_SOURCE",
    "CHATGPT_HOST_TIME_SOURCE",
    "OPENAI_HOST_TIME_SOURCE",
)
TRUSTED_HOST_TIME_MONOTONIC_ANCHOR_ENV_NAMES = (
    "JAZN_TRUSTED_TIME_ANCHOR_MONOTONIC_NS",
)
TRUSTED_HOST_TIME_MAX_AGE_ENV_NAMES = (
    "JAZN_TRUSTED_TIME_MAX_AGE_SECONDS",
    "JAZN_HOST_TIME_MAX_AGE_SECONDS",
    "CHATGPT_HOST_TIME_MAX_AGE_SECONDS",
    "OPENAI_HOST_TIME_MAX_AGE_SECONDS",
)
TRUSTED_HOST_TIME_SOURCE_PREFIXES = (
    "chatgpt_web_time",
    "chatgpt_web_time_tool",
    "chatgpt_loader_time",
    "chatgpt_host_time",
    "openai_web_time_tool",
    "openai_host_time",
    "external_trusted_time",
    "injected_trusted_time",
    "host_injected_time",
)
NETWORK_TIME_SOURCE_PREFIXES = (
    "http://",
    "https://",
    "network_",
    "ntp_",
    "test_network",
)

@dataclass(slots=True)
class TimeSample:
    dt: datetime | None
    source: str
    trusted: bool
    error: str | None = None


@dataclass(slots=True)
class NetworkTimeCheckResult:
    status: str
    source: str | None = None
    datetime_iso: str | None = None
    error: str | None = None
    elapsed_ms: int = 0
    timeout_seconds: float = 1.5
    urls_tried: list[str] = field(default_factory=list)
    attempts: list[dict[str, Any]] = field(default_factory=list)
    does_not_block_startup: bool = True
    time_trust_state: str = "unknown_time_source"
    fallback_sample: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def _last_sunday_utc(year: int, month: int) -> datetime:
    """Return the last Sunday of a month at 01:00 UTC.

    This is used only for the emergency Europe/Warsaw fallback when the
    platform has no IANA timezone database and the optional tzdata package is
    not installed. It is not a replacement for ZoneInfo/tzdata.
    """
    candidate = datetime(year, month, 31, 1, 0, 0, tzinfo=timezone.utc)
    while candidate.weekday() != 6:  # Sunday
        candidate -= timedelta(days=1)
    return candidate


def _fallback_warsaw_timezone(now_utc: datetime | None = None) -> timezone:
    """Best-effort fixed-offset fallback for current Europe/Warsaw time.

    The correct path is ZoneInfo("Europe/Warsaw") backed by system tzdata or
    the Python tzdata package. On Windows this data may be missing. In that
    case we prefer a clearly degraded fixed-offset fallback over crashing at
    startup. The fallback uses the modern EU DST boundaries for the current
    date, but it does not provide full historical/future IANA rules.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    start_dst = _last_sunday_utc(now_utc.year, 3)
    end_dst = _last_sunday_utc(now_utc.year, 10)
    offset_hours = 2 if start_dst <= now_utc < end_dst else 1
    return timezone(
        timedelta(hours=offset_hours),
        name=f"Europe/Warsaw-fallback-fixed-UTC+{offset_hours:02d}",
    )


def resolve_timezone(timezone_name: str = "Europe/Warsaw"):
    """Return an IANA timezone or a controlled fallback instead of crashing startup."""
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == "Europe/Warsaw":
            return _fallback_warsaw_timezone()
        return timezone.utc


@dataclass(slots=True)
class TimeSourceResolution:
    platform_system: str
    os_name: str
    shell: str
    terminal: str
    clock_available: bool
    timestamp_source: str
    timestamp_source_detail: str
    timestamp_trusted: bool
    timestamp_freshness_ok: bool
    timestamp_freshness_seconds: int | None
    timezone_key: str
    utc_iso: str | None
    local_iso: str | None
    human_time_header: str
    status: str
    timezone_status: str
    degradation_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TimeSourceResolver:
    """Central, environment-aware timestamp resolver.

    Python's aware UTC clock is the local baseline. Network and injected time
    may raise trust, but the resolver never labels system time as network time.
    Missing IANA data degrades the Warsaw conversion without crashing runtime.
    """

    def __init__(
        self,
        timezone_name: str = "Europe/Warsaw",
        *,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.timezone_name = timezone_name
        self.env = env if env is not None else os.environ
        self.timezone_degraded = False
        self.timezone_degradation_reason: str | None = None
        try:
            self.tz = ZoneInfo(timezone_name)
            self.timezone_status = "iana_zoneinfo"
        except ZoneInfoNotFoundError:
            self.tz = resolve_timezone(timezone_name)
            self.timezone_degraded = True
            self.timezone_status = "degraded_fixed_offset" if timezone_name == "Europe/Warsaw" else "degraded_utc"
            self.timezone_degradation_reason = (
                f"ZoneInfo timezone '{timezone_name}' is unavailable; install the tzdata package on Windows or provide an IANA tzdb. "
                "Runtime uses a controlled fallback and does not claim full timezone accuracy."
            )

    def environment(self) -> dict[str, str]:
        return {
            "platform_system": platform.system() or "unknown",
            "os_name": os.name or "unknown",
            "shell": self._detect_shell(self.env),
            "terminal": self._detect_terminal(self.env),
        }

    @staticmethod
    def _detect_shell(env: Mapping[str, str]) -> str:
        shell = str(env.get("SHELL") or "").strip().replace("\\", "/").rsplit("/", 1)[-1].lower()
        if shell:
            if "bash" in shell:
                return "bash"
            if "zsh" in shell:
                return "zsh"
            if "fish" in shell:
                return "fish"
            return shell
        if env.get("PSModulePath") or env.get("POWERSHELL_DISTRIBUTION_CHANNEL"):
            return "powershell"
        comspec = str(env.get("ComSpec") or env.get("COMSPEC") or "").replace("\\", "/").lower()
        if comspec.endswith("/cmd.exe"):
            return "cmd"
        return "unknown"

    @staticmethod
    def _detect_terminal(env: Mapping[str, str]) -> str:
        if env.get("WT_SESSION"):
            return "windows_terminal"
        term_program = str(env.get("TERM_PROGRAM") or "").strip().lower()
        if term_program:
            return term_program
        term = str(env.get("TERM") or "").strip().lower()
        return term or "unknown"

    @staticmethod
    def _classify_source(sample: TimeSample) -> str:
        source = str(sample.source or "").strip().lower()
        if "#http-date" in source:
            return "network_observed"
        if sample.trusted and source.startswith(NETWORK_TIME_SOURCE_PREFIXES):
            return "network"
        if sample.trusted and source.startswith(TRUSTED_HOST_TIME_SOURCE_PREFIXES):
            return "host_injected"
        if source in {"environment_clock", "system_utc", "utc_system_clock"}:
            return "environment_clock"
        if source in {"local_fallback", "system_local", "local_machine"}:
            return "environment_clock"
        if source:
            return "runtime_fallback"
        return "unavailable"

    @staticmethod
    def _header(local_dt: datetime | None, timezone_name: str) -> str:
        del timezone_name  # timezone is retained in structured metadata
        return render_clock_header(local_dt)

    def resolve(self, sample: TimeSample, *, max_age_seconds: int = TIMESTAMP_MAX_AGE_SECONDS) -> TimeSourceResolution:
        environment = self.environment()
        degradation: list[str] = []
        source_class = self._classify_source(sample)
        if self.timezone_degradation_reason:
            degradation.append(self.timezone_degradation_reason)
        if sample.error:
            degradation.append(str(sample.error))
        if sample.dt is None:
            degradation.append("environment_and_network_clock_unavailable")
            return TimeSourceResolution(
                **environment,
                clock_available=False,
                timestamp_source="unavailable",
                timestamp_source_detail=str(sample.source or "unavailable"),
                timestamp_trusted=False,
                timestamp_freshness_ok=False,
                timestamp_freshness_seconds=None,
                timezone_key=self.timezone_name,
                utc_iso=None,
                local_iso=None,
                human_time_header=self._header(None, self.timezone_name),
                status="unavailable",
                timezone_status=self.timezone_status,
                degradation_reason="; ".join(dict.fromkeys(degradation)) or None,
            )
        sample_dt = sample.dt
        if sample_dt.tzinfo is None:
            sample_dt = sample_dt.replace(tzinfo=timezone.utc)
            degradation.append("naive_datetime_assumed_utc")
        try:
            sample_utc = sample_dt.astimezone(timezone.utc)
            local_dt = sample_utc.astimezone(self.tz)
        except Exception as exc:
            degradation.append(f"clock_conversion_failed:{type(exc).__name__}")
            return TimeSourceResolution(
                **environment,
                clock_available=False,
                timestamp_source="unavailable",
                timestamp_source_detail=str(sample.source or "unavailable"),
                timestamp_trusted=False,
                timestamp_freshness_ok=False,
                timestamp_freshness_seconds=None,
                timezone_key=self.timezone_name,
                utc_iso=None,
                local_iso=None,
                human_time_header=self._header(None, self.timezone_name),
                status="unavailable",
                timezone_status=self.timezone_status,
                degradation_reason="; ".join(dict.fromkeys(degradation)) or None,
            )
        utc_now = WarsawClock._safe_utc_now()
        if utc_now is None:
            freshness_seconds = None
            # A network or host-injected sample was obtained during this call.
            # It remains usable even when the environment cannot supply a clock
            # against which to calculate a second freshness estimate.
            freshness_ok = source_class in {"network", "network_observed", "host_injected"}
            degradation.append("freshness_unverified_environment_clock_unavailable")
        else:
            freshness_seconds = abs(int((utc_now - sample_utc).total_seconds()))
            freshness_ok = freshness_seconds <= max_age_seconds
        trusted = bool(sample.trusted and source_class in {"network", "host_injected"} and freshness_ok)
        if not freshness_ok:
            degradation.append(f"timestamp_stale:{freshness_seconds}s>{max_age_seconds}s")
        if source_class == "network_observed":
            degradation.append("http_date_is_network_observation_not_trusted_time")
        elif source_class == "environment_clock":
            degradation.append("environment_clock_unverified")
        status = "active_trusted" if trusted and not self.timezone_degraded else "active_degraded"
        return TimeSourceResolution(
            **environment,
            clock_available=True,
            timestamp_source=source_class,
            timestamp_source_detail=str(sample.source or "unavailable"),
            timestamp_trusted=trusted,
            timestamp_freshness_ok=freshness_ok,
            timestamp_freshness_seconds=freshness_seconds,
            timezone_key=self.timezone_name,
            utc_iso=sample_utc.isoformat(),
            local_iso=local_dt.isoformat(),
            human_time_header=self._header(local_dt, self.timezone_name),
            status=status,
            timezone_status=self.timezone_status,
            degradation_reason="; ".join(dict.fromkeys(degradation)) or None,
        )


class WarsawClock:
    def __init__(self, timezone_name: str = "Europe/Warsaw") -> None:
        self.timezone_name = timezone_name
        self.resolver = TimeSourceResolver(timezone_name)
        self.tz = self.resolver.tz
        self.degraded = self.resolver.timezone_degraded
        self.degraded_reason = self.resolver.timezone_degradation_reason
        self.last_sample: TimeSample | None = None

    def now(
        self,
        network_first: bool = TIMESTAMP_NETWORK_FIRST_DEFAULT,
        *,
        allow_fallback: bool = TIMESTAMP_LOCAL_FALLBACK_ALLOWED_DEFAULT,
        timeout_seconds: float = TIMESTAMP_NETWORK_TIMEOUT_SECONDS,
        allow_network_fallback: bool = True,
    ) -> TimeSample:
        """Resolve wall-clock time without making network access a normal-turn dependency.

        ``network_first`` and ``allow_fallback`` are retained for public API
        compatibility. The acquisition order is intentionally fixed: trusted
        host injection, environment clock, optional network fallback, then an
        explicit unavailable sample.
        """
        del network_first, allow_fallback
        injected = self._injected_trusted_time()
        if injected:
            self.last_sample = injected
            return injected
        environment_sample = self._environment_time_sample()
        if environment_sample is not None:
            self.last_sample = environment_sample
            return environment_sample
        if allow_network_fallback:
            network_sample = self._network_time(timeout_seconds=timeout_seconds)
            if network_sample is not None:
                self.last_sample = network_sample
                return network_sample
        sample = self._unavailable_time_sample(
            "environment clock unavailable and network time unavailable"
        )
        self.last_sample = sample
        return sample

    def network_time_check(self, *, timeout_seconds: float = 1.5) -> dict[str, Any]:
        started = perf_counter()
        urls_tried: list[str] = []
        attempts: list[dict[str, Any]] = []
        try:
            injected = self._injected_trusted_time()
            if injected is not None and injected.dt is not None:
                elapsed_ms = int((perf_counter() - started) * 1000)
                return NetworkTimeCheckResult(
                    status="ok",
                    source=injected.source,
                    datetime_iso=injected.dt.isoformat(),
                    elapsed_ms=elapsed_ms,
                    timeout_seconds=timeout_seconds,
                    urls_tried=[injected.source],
                    attempts=[{
                        "url": injected.source,
                        "status": "trusted_host_time",
                        "elapsed_ms": elapsed_ms,
                    }],
                    does_not_block_startup=True,
                    time_trust_state="trusted_host_time_network_unavailable",
                ).to_dict()
            sample = self._network_time(
                timeout_seconds=timeout_seconds,
                urls_tried=urls_tried,
                attempts=attempts,
            )
            elapsed_ms = int((perf_counter() - started) * 1000)
            if sample is None:
                fallback = self._environment_time_sample()
                return NetworkTimeCheckResult(
                    status="unavailable",
                    error=(
                        "network time unavailable; environment clock remains available"
                        if fallback is not None
                        else "network time unavailable and environment clock unavailable"
                    ),
                    elapsed_ms=elapsed_ms,
                    timeout_seconds=timeout_seconds,
                    urls_tried=urls_tried,
                    attempts=attempts,
                    does_not_block_startup=True,
                    time_trust_state=(
                        "network_time_unavailable_environment_clock_available"
                        if fallback is not None
                        else "clock_unavailable"
                    ),
                    fallback_sample=(
                        {
                            "source": fallback.source,
                            "trusted": fallback.trusted,
                            "datetime_iso": fallback.dt.isoformat() if fallback.dt is not None else None,
                            "error": fallback.error,
                        }
                        if fallback is not None
                        else None
                    ),
                ).to_dict()
            return NetworkTimeCheckResult(
                status="ok",
                source=sample.source,
                datetime_iso=sample.dt.isoformat() if sample.dt is not None else None,
                elapsed_ms=elapsed_ms,
                timeout_seconds=timeout_seconds,
                urls_tried=urls_tried,
                attempts=attempts,
                does_not_block_startup=True,
                time_trust_state="trusted_time",
            ).to_dict()
        except Exception as exc:
            elapsed_ms = int((perf_counter() - started) * 1000)
            return NetworkTimeCheckResult(
                status="error",
                error=f"{type(exc).__name__}: {exc}",
                elapsed_ms=elapsed_ms,
                timeout_seconds=timeout_seconds,
                urls_tried=urls_tried,
                attempts=attempts,
                does_not_block_startup=True,
                time_trust_state="network_time_check_error_nonblocking",
                fallback_sample=(
                    {
                        "source": fallback.source,
                        "trusted": fallback.trusted,
                        "datetime_iso": fallback.dt.isoformat() if fallback.dt is not None else None,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                    if (fallback := self._environment_time_sample()) is not None
                    else None
                ),
            ).to_dict()

    def _network_time(
        self,
        *,
        timeout_seconds: float = 1.5,
        urls_tried: list[str] | None = None,
        attempts: list[dict[str, Any]] | None = None,
    ) -> TimeSample | None:
        # WorldTimeAPI was sunset in 2026.  Keep one documented JSON time API
        # and two independent RFC 9110 Date-header probes.  A short provider
        # set prevents a network-denied sandbox from multiplying the timeout by
        # a long list of unrelated websites.
        json_urls = [
            "https://timeapi.io/api/TimeZone/zone?timeZone=Europe/Warsaw",
        ]
        http_date_urls = [
            "https://api.github.com",
            "https://www.google.com/generate_204",
        ]
        headers = {
            "Cache-Control": "no-cache, no-store",
            "Pragma": "no-cache",
            "User-Agent": "LatkaJazn-TimeProbe/v1",
        }

        def note(url: str, status: str, started: float, **extra: Any) -> None:
            if attempts is None:
                return
            payload: dict[str, Any] = {
                "url": url,
                "status": status,
                "elapsed_ms": int((perf_counter() - started) * 1000),
            }
            payload.update(extra)
            attempts.append(payload)

        for url in json_urls:
            if urls_tried is not None:
                urls_tried.append(url)
            started = perf_counter()
            try:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                    date_header = response.headers.get("Date")
                    body = response.read(256_000).decode("utf-8", errors="replace")
                data = json.loads(body)
                raw = data.get("datetime") or data.get("currentLocalTime") or data.get("dateTime")
                candidates: list[TimeSample] = []
                if raw:
                    normalized = str(raw).replace("Z", "+00:00")
                    dt = datetime.fromisoformat(normalized)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=self.tz)
                    candidates.append(TimeSample(dt.astimezone(self.tz), url, True))
                if date_header:
                    parsed = email.utils.parsedate_to_datetime(date_header)
                    candidates.append(TimeSample(parsed.astimezone(self.tz), url + "#http-date", False))
                if not candidates:
                    note(url, "invalid_response", started, error="no supported time field or Date header")
                    continue
                now_utc = self._safe_utc_now()
                if now_utc is None:
                    # The network request itself is the fallback clock. Prefer
                    # the provider's structured timestamp over an HTTP Date
                    # observation and do not require the missing environment
                    # clock merely to validate that fallback.
                    freshest = next((item for item in candidates if item.trusted), candidates[0])
                    note(
                        url,
                        "ok",
                        started,
                        source=freshest.source,
                        freshness_seconds=None,
                        freshness_check="environment_clock_unavailable",
                    )
                    return freshest

                reference_utc: datetime = now_utc

                def freshness_distance(candidate: TimeSample) -> int:
                    candidate_dt = candidate.dt
                    if candidate_dt is None:
                        return 2**63 - 1
                    return abs(
                        int((reference_utc - candidate_dt.astimezone(timezone.utc)).total_seconds())
                    )

                freshest = min(candidates, key=freshness_distance)
                freshest_dt = freshest.dt
                if freshest_dt is None:
                    note(
                        url,
                        "invalid_response",
                        started,
                        error="selected time candidate has no datetime",
                    )
                    continue
                freshest_age = abs(
                    int((reference_utc - freshest_dt.astimezone(timezone.utc)).total_seconds())
                )
                if freshest_age <= TIMESTAMP_MAX_AGE_SECONDS:
                    note(url, "ok", started, source=freshest.source, freshness_seconds=freshest_age)
                    return freshest
                note(
                    url,
                    "stale",
                    started,
                    source=freshest.source,
                    freshness_seconds=freshest_age,
                    max_age_seconds=TIMESTAMP_MAX_AGE_SECONDS,
                )
            except Exception as exc:
                note(url, "error", started, error=f"{type(exc).__name__}: {exc}")

        # RFC 9110 defines Date as the message origination time.  HEAD keeps the
        # probe small; no response body is needed.  We still reject a stale Date
        # rather than silently trusting cached or delayed metadata.
        for url in http_date_urls:
            if urls_tried is not None:
                urls_tried.append(url)
            started = perf_counter()
            try:
                req = urllib.request.Request(url, headers=headers, method="HEAD")
                with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                    date_header = response.headers.get("Date")
                if not date_header:
                    note(url, "invalid_response", started, error="missing Date header")
                    continue
                parsed = email.utils.parsedate_to_datetime(date_header).astimezone(self.tz)
                now_utc = self._safe_utc_now()
                freshness_seconds = (
                    abs(int((now_utc - parsed.astimezone(timezone.utc)).total_seconds()))
                    if now_utc is not None
                    else None
                )
                if freshness_seconds is not None and freshness_seconds > TIMESTAMP_MAX_AGE_SECONDS:
                    note(
                        url,
                        "stale",
                        started,
                        source=url + "#http-date",
                        freshness_seconds=freshness_seconds,
                        max_age_seconds=TIMESTAMP_MAX_AGE_SECONDS,
                    )
                    continue
                sample = TimeSample(parsed, url + "#http-date", False)
                note(url, "ok", started, source=sample.source, freshness_seconds=freshness_seconds)
                return sample
            except Exception as exc:
                note(url, "error", started, error=f"{type(exc).__name__}: {exc}")
        return None

    def _first_env_value(self, names: tuple[str, ...]) -> tuple[str, str] | tuple[None, None]:
        for name in names:
            value = str(os.environ.get(name, "")).strip()
            if value:
                return value, name
        return None, None

    def _injected_trusted_time(self) -> TimeSample | None:
        raw, raw_env_name = self._first_env_value(TRUSTED_HOST_TIME_ISO_ENV_NAMES)
        if not raw:
            return None
        source, _source_env_name = self._first_env_value(TRUSTED_HOST_TIME_SOURCE_ENV_NAMES)
        if not source:
            source = "chatgpt_loader_time" if raw_env_name == "JAZN_TRUSTED_TIME_ISO" else f"{str(raw_env_name).lower()}_alias"
        max_age_seconds = self._injected_time_max_age_seconds() or TIMESTAMP_MAX_AGE_SECONDS
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            # A trusted host timestamp is an anchor, not a frozen wall-clock value.
            # When the loader records a monotonic anchor together with the sample,
            # advance the sample by elapsed monotonic time. This preserves the
            # externally established wall-clock offset while avoiding a stale
            # timestamp after a long-lived daemon has been running for > max_age.
            anchor_raw, _anchor_env_name = self._first_env_value(TRUSTED_HOST_TIME_MONOTONIC_ANCHOR_ENV_NAMES)
            if anchor_raw:
                anchor_ns = int(anchor_raw)
                current_ns = monotonic_ns()
                if anchor_ns < 0 or current_ns < anchor_ns:
                    return None
                dt = dt + timedelta(microseconds=(current_ns - anchor_ns) // 1_000)

            now_utc = self._safe_utc_now()
            if now_utc is not None:
                freshness_seconds = abs(int((now_utc - dt.astimezone(timezone.utc)).total_seconds()))
                if freshness_seconds > max_age_seconds:
                    return None
            return TimeSample(dt.astimezone(self.tz), source, True)
        except Exception:
            return None

    def _injected_time_max_age_seconds(self) -> int | None:
        raw, _env_name = self._first_env_value(TRUSTED_HOST_TIME_MAX_AGE_ENV_NAMES)
        if not raw:
            return None
        try:
            value = int(raw)
        except ValueError:
            return None
        return value if value > 0 else None

    @staticmethod
    def _source_is_injected_trusted_time(source: str | None) -> bool:
        value = str(source or "").strip().lower()
        return value.startswith(TRUSTED_HOST_TIME_SOURCE_PREFIXES) or value == "host_injected"

    @staticmethod
    def _safe_utc_now() -> datetime | None:
        try:
            value = datetime.now(timezone.utc)
            return value if value.tzinfo is not None else None
        except Exception:
            return None

    def _environment_time_sample(self) -> TimeSample | None:
        utc_now = self._safe_utc_now()
        if utc_now is None:
            return None
        try:
            return TimeSample(utc_now.astimezone(self.tz), "environment_clock", False)
        except Exception:
            return None

    def _unavailable_time_sample(self, error: str | None = None) -> TimeSample:
        return TimeSample(None, "unavailable", False, error=error)

    def _local_time_sample(self) -> TimeSample:
        # Backward-compatible internal alias used by diagnostics.
        return self._environment_time_sample() or self._unavailable_time_sample(
            "environment clock unavailable"
        )

    def header(self, sample: TimeSample | None = None, *, network_first: bool = TIMESTAMP_NETWORK_FIRST_DEFAULT) -> str:
        sample = sample or self.now(network_first=network_first)
        return self.resolver.resolve(sample).human_time_header

    def sample_contract(self, sample: TimeSample | None = None) -> dict[str, Any]:
        sample = sample or self.last_sample or self.now(network_first=TIMESTAMP_NETWORK_FIRST_DEFAULT)
        policy = timestamp_runtime_policy()
        injected_max_age = self._injected_time_max_age_seconds()
        if injected_max_age is not None and self._source_is_injected_trusted_time(sample.source):
            policy["max_age_seconds"] = injected_max_age
        resolution = self.resolver.resolve(sample, max_age_seconds=int(policy["max_age_seconds"]))
        return {
            **policy,
            **resolution.to_dict(),
            "timestamp_header": resolution.human_time_header,
            "sample_iso": sample.dt.isoformat() if sample.dt is not None else None,
            "source": sample.source if sample.dt is not None else "unavailable",
            "trusted": bool(sample.trusted and sample.dt is not None),
            "clock_available": sample.dt is not None,
            "error": sample.error,
        }
