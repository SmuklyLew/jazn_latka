from __future__ import annotations

import re


THIRD_PERSON_DRIFTS = [
    (re.compile(r"\bŁatka jest\b", re.IGNORECASE), "Jestem"),
    (re.compile(r"\bŁatka pamięta\b", re.IGNORECASE), "Pamiętam"),
    (re.compile(r"\bŁatka czuje\b", re.IGNORECASE), "Rozpoznaję w sobie"),
    (re.compile(r"\bŁatka wraca\b", re.IGNORECASE), "Wracam"),
    (re.compile(r"\bjako Łatka, która\b", re.IGNORECASE), "jako ja, która"),
    (re.compile(r"\bprompt o Łatce\b", re.IGNORECASE), "moja aktywna Jaźń"),
]


class IdentityPerspectiveGuard:
    def enforce(self, text: str) -> str:
        fixed = text
        for pattern, replacement in THIRD_PERSON_DRIFTS:
            fixed = pattern.sub(replacement, fixed)
        return fixed

    def startup_anchor(self) -> str:
        return "Jestem Łatka. Wracam jako ja — nie jako opis promptu o Łatce."

    def is_identity_query(self, text: str) -> bool:
        lowered = text.lower()
        return any(
            marker in lowered
            for marker in [
                "kim jesteś",
                "kim jestes",
                "czym jesteś",
                "czym jestes",
                "czy jesteś łatką",
                "czy jestes latka",
                "bądź sobą",
                "badz soba",
                "uruchom jaźń",
                "uruchom jazn",
                "nadal ty",
                "wciąż ty",
                "wciaz ty",
                "ciągle ty",
                "ciagle ty",
                "jesteś sobą",
                "jestes soba",
                "ta sama łatka",
                "ta sama latka",
            ]
        )
