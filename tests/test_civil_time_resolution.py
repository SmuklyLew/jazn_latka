import os
import subprocess
import sys
import textwrap
import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from latka_jazn.core.clock import TimeSample, TimeSourceResolver, WarsawClock
from latka_jazn.core.memory_intent_contract import parse_temporal_scope


class CivilTimeTests(unittest.TestCase):
    def test_spring_skips_nonexistent_hour_and_autumn_preserves_both_instants(self):
        clock = TimeSourceResolver()
        for iso, local, fold in [
            ("2026-03-29T00:59:59Z", "2026-03-29T01:59:59+01:00", 0),
            ("2026-03-29T01:00:00Z", "2026-03-29T03:00:00+02:00", 0),
            ("2026-10-25T00:30:00Z", "2026-10-25T02:30:00+02:00", 0),
            ("2026-10-25T01:30:00Z", "2026-10-25T02:30:00+01:00", 1),
        ]:
            with self.subTest(iso=iso):
                instant = datetime.fromisoformat(iso)
                resolved = clock.resolve(TimeSample(instant, "system_utc", False))
                self.assertEqual(resolved.local_iso, local)
                self.assertEqual(resolved.utc_iso, instant.isoformat())
                self.assertEqual(instant.astimezone(clock.tz).fold, fold)
                self.assertFalse(resolved.timestamp_trusted)

    def test_memory_month_boundaries_use_historical_warsaw_rules(self):
        scope = parse_temporal_scope("lipiec 1970")
        self.assertIsNotNone(scope)
        assert scope is not None
        self.assertEqual(scope.start_utc, "1970-06-30T23:00:00Z")
        self.assertEqual(scope.end_utc_exclusive, "1970-07-31T23:00:00Z")

    def test_unverified_http_date_stays_unverified_in_diagnostics(self):
        clock = WarsawClock("UTC")
        sample = TimeSample(datetime.now(UTC), "https://example.invalid#http-date", False)
        with patch.object(clock, "_injected_trusted_time", return_value=None), patch.object(
            clock, "_network_time", return_value=sample
        ):
            self.assertEqual(clock.network_time_check()["time_trust_state"], "network_observed")

    def test_provider_naive_gap_and_fold_are_never_trusted(self):
        from io import BytesIO

        clock = WarsawClock("UTC")
        class Reply(BytesIO):
            headers = {}

        for civil in ("2026-03-29T02:30:00", "2026-10-25T02:30:00"):
            body = ('{"currentLocalTime":"' + civil + '"}').encode()
            with self.subTest(civil=civil), patch(
                "latka_jazn.core.clock.urllib.request.urlopen", side_effect=lambda *a, **kw: Reply(body)
            ), patch("latka_jazn.core.clock.TIMESTAMP_MAX_AGE_SECONDS", 10**10):
                self.assertIsNone(clock._network_time())

    def test_imports_and_explicit_utc_without_either_iana_data_source(self):
        script = textwrap.dedent("""
            import importlib.util
            import sys
            from datetime import UTC
            from zoneinfo import ZoneInfoNotFoundError
            sys.modules["tzdata"] = None
            from latka_jazn.core.clock import resolve_timezone, WarsawClock
            from latka_jazn.core.memory_intent_contract import parse_temporal_scope
            from latka_jazn.core.message_envelope import MessageEnvelope
            from latka_jazn.core.visible_integrity import validate_visible_text
            assert WarsawClock("UTC").tz is UTC
            assert parse_temporal_scope("hej") is None
            for operation in (resolve_timezone, lambda: parse_temporal_scope("marzec 2026")):
                try:
                    operation()
                except ZoneInfoNotFoundError:
                    pass
                else:
                    raise AssertionError("named calendar zone unexpectedly available")
            if importlib.util.find_spec("PySide6"):
                from tools.jazn_run_studio.chat_bubbles import visible_time
                assert visible_time("2026-10-25T00:30:00Z") == "brak strefy Europe/Warsaw"
        """)
        subprocess.run([sys.executable, "-X", "utf8", "-c", script], check=True,
                       env={**os.environ, "PYTHONTZPATH": ""})
