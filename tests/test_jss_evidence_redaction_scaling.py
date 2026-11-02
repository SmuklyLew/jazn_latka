"""Long evidence text must remain redactable without weakening secret masking."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools.jazn_run_studio.core import Redactor


@pytest.mark.parametrize("raw,expected", [
    ('token=abc', 'token="[UKRYTO]"'),
    ('"api_key": "abc def"', '"api_key": "[UKRYTO]"'),
    ("password='abc def'", 'password="[UKRYTO]"'),
    ('my-credential-extra = abc, visible=ok', 'my-credential-extra = "[UKRYTO]", visible=ok'),
    ('prefixTOKENsuffix=abc', 'prefixTOKENsuffix="[UKRYTO]"'),
    ('public="token=private"', 'public="token="[UKRYTO]"'),
    ('public=visible password=private', 'public=visible password="[UKRYTO]"'),
    ('Authorization: Bearer opaque', 'Authorization: Bearer [UKRYTO]'),
    ('nonsecret=private', 'nonsecret="[UKRYTO]"'),
    ('ordinary=visible', 'ordinary=visible'),
])
def test_existing_assignment_redaction_contract(raw, expected):
    assert Redactor({}).text(raw) == expected


@pytest.mark.parametrize("shape", ["plain", "many-keywords"])
def test_megabyte_word_completes_in_bounded_owned_process(shape):
    root = Path(__file__).resolve().parents[1]
    script = '''
from tools.jazn_run_studio.core import Redactor
import sys
word = 'x' * (1024 * 1024) if sys.argv[1] == 'plain' else 'token' * 210000
redactor = Redactor({})
assert redactor.text(word) == word
assert redactor.text(word + '=private') == (word + '="[UKRYTO]"' if 'token' in word else word + '=private')
print('redaction-completed')
'''
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("JAZN_")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run([sys.executable, "-X", "utf8", "-c", script, shape], cwd=root, env=env,
                            capture_output=True, timeout=5, check=False)
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert result.stdout.strip() == b"redaction-completed"
