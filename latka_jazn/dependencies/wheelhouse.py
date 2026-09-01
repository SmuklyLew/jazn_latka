from __future__ import annotations

from datetime import datetime, timezone
from email.parser import Parser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Sequence
import uuid
import zipfile

from .common import (
    DEFAULT_TIMEOUT_SECONDS, MANIFEST_NAME, WHEELHOUSE_SCHEMA, DependencyStudioError,
    TargetSpec, default_wheelhouse_root, expand_profile_names, normalize_python_version,
    resolve_profile_requirements, runtime_version, target_spec,
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def sha256_json(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def build_download_command(*, python_executable: str, destination: Path,
                           requirements: Sequence[str], target: TargetSpec) -> list[str]:
    cmd = [python_executable, '-m', 'pip', 'download', '--disable-pip-version-check',
           '--dest', str(destination), '--only-binary=:all:']
    if target.pip_platform:
        cmd += ['--platform', target.pip_platform, '--python-version', target.python_version,
                '--implementation', target.implementation]
        if target.abi:
            cmd += ['--abi', target.abi]
    return [*cmd, *requirements]


def wheel_metadata(path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad:
                raise DependencyStudioError(f'Wheel CRC failed: {path.name}:{bad}')
            metas = [n for n in zf.namelist() if n.endswith('.dist-info/METADATA')]
            wheels = [n for n in zf.namelist() if n.endswith('.dist-info/WHEEL')]
            if len(metas) != 1 or len(wheels) != 1:
                raise DependencyStudioError(f'Wheel metadata layout invalid: {path.name}')
            message = Parser().parsestr(zf.read(metas[0]).decode('utf-8', errors='replace'))
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise DependencyStudioError(f'Invalid wheel {path}: {exc}') from exc
    classifiers = message.get_all('Classifier') or []
    return {
        'name': message.get('Name'), 'version': message.get('Version'),
        'requires_python': message.get('Requires-Python'),
        'license_expression': message.get('License-Expression'), 'license': message.get('License'),
        'license_classifiers': [c for c in classifiers if str(c).startswith('License ::')],
    }


def _wheel_row(path: Path) -> dict[str, Any]:
    return {'filename': path.name, 'size_bytes': path.stat().st_size,
            'sha256': sha256_file(path), 'metadata': wheel_metadata(path)}


def verify_bundle(bundle_dir: Path | str) -> dict[str, Any]:
    directory = Path(bundle_dir).resolve()
    manifest_path = directory / MANIFEST_NAME
    manifest = read_manifest(manifest_path)
    if manifest is None:
        return {'ok': False, 'bundle_dir': str(directory), 'errors': [{'code': 'manifest_unreadable'}]}
    errors: list[dict[str, Any]] = []
    if manifest.get('schema_version') != WHEELHOUSE_SCHEMA:
        errors.append({'code': 'manifest_schema_unsupported'})
    files = manifest.get('files')
    if not isinstance(files, list):
        files = []
    expected: set[str] = set()
    verified = 0
    for row in files:
        if not isinstance(row, dict):
            errors.append({'code': 'manifest_file_entry_invalid'}); continue
        name = str(row.get('filename') or '')
        p = Path(name)
        if not name or p.name != name or p.suffix.lower() != '.whl' or name in expected:
            errors.append({'code': 'wheel_filename_unsafe_or_duplicate', 'filename': name}); continue
        expected.add(name); target = directory / name
        if not target.is_file() or target.is_symlink():
            errors.append({'code': 'wheel_missing_or_not_regular', 'filename': name}); continue
        mismatch = False
        if target.stat().st_size != int(row.get('size_bytes', -1)):
            errors.append({'code': 'wheel_size_mismatch', 'filename': name}); mismatch = True
        if sha256_file(target) != str(row.get('sha256') or '').lower():
            errors.append({'code': 'wheel_sha256_mismatch', 'filename': name}); mismatch = True
        if mismatch:
            continue
        try:
            actual = wheel_metadata(target)
        except DependencyStudioError as exc:
            errors.append({'code': 'wheel_structure_invalid', 'filename': name, 'detail': str(exc)}); continue
        declared = row.get('metadata')
        if not isinstance(declared, dict):
            declared = {}
        if any(str(actual.get(k) or '') != str(declared.get(k) or '') for k in ('name', 'version')):
            errors.append({'code': 'wheel_metadata_mismatch', 'filename': name}); continue
        verified += 1
    actual_names = {p.name for p in directory.glob('*.whl') if p.is_file()}
    for extra in sorted(actual_names - expected):
        errors.append({'code': 'unlisted_wheel', 'filename': extra})
    return {
        'ok': not errors, 'bundle_dir': str(directory), 'manifest_path': str(manifest_path),
        'manifest_sha256': sha256_file(manifest_path) if manifest_path.is_file() else None,
        'profiles': list(manifest.get('profiles') or []),
        'resolved_profiles': list(manifest.get('resolved_profiles') or manifest.get('profiles') or []),
        'requirements': list(manifest.get('requirements') or []), 'target': manifest.get('target') or {},
        'wheel_count': len(expected), 'verified_wheel_count': verified, 'errors': errors,
        'truth_boundary': 'SHA-256, wheel ZIP structure and declared Name/Version metadata are verified; this is not a security or legal certification.',
    }


def _manifest(root: Path, profiles: Sequence[str], requirements: Sequence[str],
              target: TargetSpec, wheels: Sequence[Path], command: Sequence[str]) -> dict[str, Any]:
    rows = [_wheel_row(p) for p in sorted(wheels, key=lambda p: p.name.lower())]
    request = {'profiles': sorted(profiles), 'requirements': sorted(requirements), 'target': target.to_dict()}
    resolution = [{'filename': r['filename'], 'sha256': r['sha256']} for r in rows]
    return {
        'schema_version': WHEELHOUSE_SCHEMA, 'runtime_version': runtime_version(),
        'created_at_utc': datetime.now(timezone.utc).isoformat(), 'project_root_name': root.name,
        'profiles': list(profiles), 'resolved_profiles': list(expand_profile_names(root, profiles)),
        'requirements': list(requirements), 'target': target.to_dict(),
        'request_fingerprint': sha256_json(request), 'resolution_fingerprint': sha256_json(resolution),
        'wheel_count': len(rows), 'total_size_bytes': sum(int(r['size_bytes']) for r in rows),
        'files': rows, 'download_command': list(command), 'network_used_for_download': True,
        'install_policy': 'offline_no_index_find_links_only',
    }


def download_bundle(root: Path | str, *, profile_names: Sequence[str], python_version: str | None = None,
                    platform_alias: str | None = None, python_executable: str | None = None,
                    wheelhouse_root: Path | str | None = None,
                    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS, dry_run: bool = False) -> dict[str, Any]:
    project_root = Path(root).resolve(); target = target_spec(platform_alias, python_version)
    requirements = resolve_profile_requirements(project_root, profile_names)
    executable = str(python_executable or sys.executable)
    wheelhouse = Path(wheelhouse_root).resolve() if wheelhouse_root else default_wheelhouse_root(project_root)
    stage = wheelhouse / f'.download-{uuid.uuid4().hex}'
    command = build_download_command(python_executable=executable, destination=stage,
                                     requirements=requirements, target=target)
    if dry_run:
        return {'ok': True, 'dry_run': True, 'profiles': list(profile_names), 'requirements': requirements,
                'target': target.to_dict(), 'wheelhouse_root': str(wheelhouse), 'command': command}
    wheelhouse.mkdir(parents=True, exist_ok=True); stage.mkdir(parents=True, exist_ok=False)
    try:
        cp = subprocess.run(command, cwd=project_root, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', timeout=max(30, int(timeout_seconds)), check=False)
        if cp.returncode:
            raise DependencyStudioError('pip download failed: ' + (cp.stderr.strip() or cp.stdout.strip() or f'exit={cp.returncode}'))
        wheels = sorted(stage.glob('*.whl'))
        if not wheels:
            raise DependencyStudioError('pip download produced no wheel files')
        unexpected = [p.name for p in stage.iterdir() if p.is_file() and p.suffix.lower() != '.whl']
        if unexpected:
            raise DependencyStudioError('Wheel-only download produced unexpected files: ' + ', '.join(sorted(unexpected)))
        manifest = _manifest(project_root, profile_names, requirements, target, wheels, command)
        slug = '+'.join(re.sub(r'[^a-z0-9._+-]+', '-', p.lower()) for p in profile_names) or 'default'
        name = f"{slug}__{target.alias}__py{target.python_version.replace('.', '')}__{manifest['resolution_fingerprint'][:12]}"
        manifest['bundle_name'] = name
        (stage / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        checked = verify_bundle(stage)
        if checked.get('ok') is not True:
            raise DependencyStudioError(f"Downloaded bundle verification failed: {checked.get('errors')}")
        destination = wheelhouse / name
        if destination.exists():
            existing = verify_bundle(destination); em = read_manifest(destination / MANIFEST_NAME)
            if existing.get('ok') is True and em and em.get('resolution_fingerprint') == manifest.get('resolution_fingerprint') and em.get('request_fingerprint') == manifest.get('request_fingerprint'):
                shutil.rmtree(stage)
                return {'ok': True, 'state': 'bundle_reused', 'bundle_dir': str(destination), 'manifest': em, 'verification': existing}
            raise DependencyStudioError(f'Immutable bundle path already exists with different contents: {destination}')
        os.replace(stage, destination)
        final = verify_bundle(destination)
        return {'ok': bool(final.get('ok')), 'state': 'bundle_downloaded', 'bundle_dir': str(destination),
                'manifest': manifest, 'verification': final, 'pip_stdout_tail': cp.stdout.splitlines()[-20:]}
    finally:
        if stage.exists(): shutil.rmtree(stage, ignore_errors=True)


def discover_bundles(root: Path | str, *, wheelhouse_root: Path | str | None = None,
                     required_profiles: Sequence[str] | None = None,
                     python_version: str | None = None, platform_alias: str | None = None,
                     verify: bool = True) -> list[dict[str, Any]]:
    project_root = Path(root).resolve()
    wheelhouse = Path(wheelhouse_root).resolve() if wheelhouse_root else default_wheelhouse_root(project_root)
    if not wheelhouse.is_dir(): return []
    wanted_profiles = set(str(x) for x in (required_profiles or []))
    wanted_python = normalize_python_version(python_version) if python_version else None
    wanted_platform = target_spec(platform_alias, wanted_python).alias if platform_alias else None
    out: list[dict[str, Any]] = []
    for mp in wheelhouse.glob(f'*/{MANIFEST_NAME}'):
        m = read_manifest(mp)
        if not m or m.get('schema_version') != WHEELHOUSE_SCHEMA: continue
        coverage = set(str(x) for x in (m.get('resolved_profiles') or m.get('profiles') or []))
        target = m.get('target')
        if not isinstance(target, dict):
            target = {}
        if wanted_profiles and not wanted_profiles.issubset(coverage): continue
        if wanted_python and str(target.get('python_version') or '') != wanted_python: continue
        if wanted_platform and str(target.get('alias') or '') != wanted_platform: continue
        out.append({'bundle_dir': str(mp.parent), 'manifest_path': str(mp), 'manifest': m,
                    'verification': verify_bundle(mp.parent) if verify else {'ok': None},
                    'created_at_utc': m.get('created_at_utc')})
    out.sort(key=lambda x: str(x.get('created_at_utc') or ''), reverse=True)
    return out
