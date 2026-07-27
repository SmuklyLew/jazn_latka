from __future__ import annotations

from pathlib import Path
import base64
import gzip
import hashlib
import json
import subprocess
import traceback

STATUS_PATH = Path('.github/runtime-hardening-recover-v4-status.json')
V3 = Path('.github/runtime-hardening-patch-v3')
V4 = Path('.github/runtime-hardening-patch-v4')
EXPECTED_GLOBAL = {
    'base64_chars': 90664,
    'base64_sha256': '71cb2baad8b8817d0d82eec189a48eb82b10bcd271be6e2776bd04bb65b56e32',
    'compressed_bytes': 67996,
    'compressed_sha256': '135e1bf73e3873992f2ace03f72d201e862c9489733f72971a7ed98724cbb429',
    'patch_bytes': 294562,
    'patch_sha256': '80f0486c3d400d190fb6b98c7e0f8b607c9ac585409fcee0893862e37c99d754',
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_ascii(path: Path) -> str:
    return path.read_text(encoding='ascii').strip()


def write_status(payload: dict) -> None:
    STATUS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main() -> int:
    V4.mkdir(parents=True, exist_ok=True)
    manifest3 = json.loads((V3 / 'manifest.json').read_text(encoding='utf-8'))
    expected = next(item for item in manifest3['parts'] if item['name'] == 'part-0005.b64')
    target_rel = '.github/runtime-hardening-patch-v3/part-0005.b64'
    commits = subprocess.check_output(
        ['git', 'log', '--all', '--format=%H', '--', target_rel], text=True
    ).splitlines()
    candidates: list[dict] = []
    recovered: str | None = None
    source_commit: str | None = None
    for commit in commits:
        try:
            raw = subprocess.check_output(['git', 'show', f'{commit}:{target_rel}']).strip()
        except subprocess.CalledProcessError:
            continue
        candidate = {'commit': commit, 'chars': len(raw), 'sha256': sha(raw)}
        candidates.append(candidate)
        if candidate['chars'] == int(expected['chars']) and candidate['sha256'] == expected['sha256']:
            recovered = raw.decode('ascii')
            source_commit = commit
            break
    if recovered is None:
        raise RuntimeError(json.dumps({
            'error_code': 'part_0005_not_in_history',
            'expected': expected,
            'candidates': candidates,
        }, sort_keys=True))

    (V3 / 'part-0005.b64').write_text(recovered, encoding='ascii')
    parts = [read_ascii(V3 / f'part-{index:04d}.b64') for index in range(3)]
    parts.extend(read_ascii(V4 / f'part-{index:04d}.b64') for index in range(3, 6))
    if any(len(item) != 8000 for item in parts):
        raise RuntimeError('invalid known-good v4 prefix')

    tail = (
        read_ascii(V3 / 'part-0004.b64')[9000:]
        + recovered
        + read_ascii(V3 / 'part-0006.b64')
        + read_ascii(V3 / 'part-0007.b64')
    )
    if len(tail) != 42664:
        raise RuntimeError(f'unexpected tail length: {len(tail)}')
    tail_parts = [tail[offset:offset + 8000] for offset in range(0, len(tail), 8000)]
    for index, data in enumerate(tail_parts, start=6):
        (V4 / f'part-{index:04d}.b64').write_text(data, encoding='ascii')
    parts.extend(tail_parts)

    encoded = ''.join(parts)
    if len(encoded) != EXPECTED_GLOBAL['base64_chars']:
        raise RuntimeError(f'base64 length mismatch: {len(encoded)}')
    if sha(encoded.encode('ascii')) != EXPECTED_GLOBAL['base64_sha256']:
        raise RuntimeError('base64 sha256 mismatch')
    compressed = base64.b64decode(encoded, validate=True)
    if len(compressed) != EXPECTED_GLOBAL['compressed_bytes'] or sha(compressed) != EXPECTED_GLOBAL['compressed_sha256']:
        raise RuntimeError('compressed payload mismatch')
    patch = gzip.decompress(compressed)
    if len(patch) != EXPECTED_GLOBAL['patch_bytes'] or sha(patch) != EXPECTED_GLOBAL['patch_sha256']:
        raise RuntimeError('patch mismatch')

    manifest4 = {
        'schema_version': 'runtime_hardening_patch_transport/v4',
        'base_sha': '30a30593901e0b8d24ba6f443f8f67d91d5078e1',
        'target_branch': 'update/v15.1.0.3.90-runtime-hardening',
        **EXPECTED_GLOBAL,
        'part_count': len(parts),
        'parts': [
            {
                'name': f'part-{index:04d}.b64',
                'chars': len(data),
                'sha256': sha(data.encode('ascii')),
            }
            for index, data in enumerate(parts)
        ],
        'recovered_part_0005_from_commit': source_commit,
    }
    (V4 / 'manifest.json').write_text(
        json.dumps(manifest4, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    write_status({
        'ok': True,
        'source_commit': source_commit,
        'part_count': len(parts),
        'patch_bytes': len(patch),
        'patch_sha256': EXPECTED_GLOBAL['patch_sha256'],
    })
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        write_status({
            'ok': False,
            'error_type': type(exc).__name__,
            'error': str(exc),
            'traceback': traceback.format_exc(),
        })
        print(STATUS_PATH.read_text(encoding='utf-8'))
        raise
