from __future__ import annotations

"""One bounded syntax repair; source bytes are never modified."""
import hashlib
import json
from typing import Any


def repair_missing_object_comma(data: bytes) -> tuple[bytes, dict[str, Any]]:
    text = data.decode('utf-8-sig')
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        position = exc.pos
        if exc.msg != "Expecting ',' delimiter" or text[position:position+1] != '{' or not text[:position].rstrip().endswith('}'):
            raise ValueError('Only a single missing comma between JSON objects can be repaired') from exc
        repaired = (text[:position] + ',' + text[position:]).encode('utf-8')
        json.loads(repaired)
        return repaired, {'operation': 'insert_comma_between_objects', 'character_offset': position,
                          'source_sha256': hashlib.sha256(data).hexdigest(),
                          'result_sha256': hashlib.sha256(repaired).hexdigest(),
                          'source_retained': True}
    raise ValueError('JSON is already valid')
