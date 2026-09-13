from __future__ import annotations

"""Jaźń - Studio Pamięci: source audit, staged rebuild and configuration."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence
import argparse
import json
import os
import sqlite3
import uuid
import zipfile
import hashlib

from latka_jazn.version import PACKAGE_VERSION
from .studio_audit import scan_sources, sha256_file, canonical_hash
from .studio_links import correlate_file, search_catalog
from .unified_memory import UnifiedMemoryDatabase
from .protocol_engine import ProtocolEngine


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def snapshot_database(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


@dataclass(frozen=True)
class StudioConfig:
    source_root: str
    workspace: str
    database: str
    backup_root: str
    export_root: str
    report_root: str
    catalog: str
    benchmark: str = ''
    correlation_window_seconds: int = 300
    base_commit: str = 'unrecorded'
    repair_missing_commas: bool = False

    def validate(self) -> None:
        if not isinstance(self.repair_missing_commas, bool):
            raise ValueError('repair_missing_commas musi być wartością logiczną')
        for key in ('source_root', 'workspace', 'database', 'backup_root', 'export_root', 'report_root', 'catalog'):
            if not Path(getattr(self, key)).expanduser().is_absolute():
                raise ValueError(f'{key}: wymagana jest ścieżka bezwzględna')
        source = Path(self.source_root).expanduser().resolve()
        if not source.is_dir():
            raise ValueError('Folder źródeł nie istnieje')
        targets = [Path(getattr(self, key)).expanduser().resolve() for key in
                   ('workspace', 'database', 'backup_root', 'export_root', 'report_root', 'catalog')]
        if any(p == source or p.is_relative_to(source) for p in targets):
            raise ValueError('Ścieżki zapisu muszą być poza folderem źródeł')
        if len(set(targets)) != len(targets):
            raise ValueError('Ścieżki robocze, bazy, katalogu i raportów muszą być różne')
        if Path(self.database).suffix.lower() not in {'.db', '.sqlite', '.sqlite3'}:
            raise ValueError('Wskaż konkretny plik bazy SQLite')
        if isinstance(self.correlation_window_seconds, bool) or not isinstance(self.correlation_window_seconds, int) or not 0 <= self.correlation_window_seconds <= 86400:
            raise ValueError('Okno korelacji musi wynosić 0..86400 sekund')

    @classmethod
    def load(cls, path: Path) -> 'StudioConfig':
        config = cls(**json.loads(path.read_text(encoding='utf-8-sig')))
        config.validate()
        return config


class MemoryStudio:
    def __init__(self, config: StudioConfig):
        config.validate()
        self.config = config
        self.report = Path(config.report_root) / 'source_audit.json'

    def scan(self) -> dict[str, Any]:
        result = scan_sources(Path(self.config.source_root), Path(self.config.catalog),
                              repair_missing_commas=self.config.repair_missing_commas)
        write_json(self.report, result)
        return result

    def sources(self) -> list[Path]:
        report = json.loads(self.report.read_text(encoding='utf-8'))
        if Path(report['root']).resolve() != Path(self.config.source_root).resolve() or Path(report['catalog']).resolve() != Path(self.config.catalog).resolve():
            raise ValueError('Raport dotyczy innych źródeł lub katalogu')
        if not report['ok']:
            raise ValueError('Najpierw rozwiąż błędy audytu źródeł')
        con = sqlite3.connect(Path(self.config.catalog).resolve().as_uri() + '?mode=ro', uri=True)
        try:
            expected = dict(con.execute('SELECT path,sha FROM files'))
            fingerprint = canonical_hash([tuple(r) for r in con.execute('SELECT path,sha,role FROM files ORDER BY path')])
            if fingerprint != report['fingerprint']:
                raise ValueError('Katalog i raport pochodzą z różnych skanów')
        finally:
            con.close()
        found = {str(p) for p in Path(self.config.source_root).resolve().rglob('*') if p.is_file() and not p.is_symlink()}
        if found != set(expected):
            raise ValueError('Zestaw plików zmienił się po audycie; ponów skan')
        for name, expected_sha in expected.items():
            if sha256_file(Path(name)) != expected_sha:
                raise ValueError(f'Źródło zmieniło się po audycie: {name}')
        paths = [Path(p) for p in report['selected_sources']]
        if not paths:
            raise ValueError('Audyt nie znalazł źródeł do importu')
        for path in paths:
            if sha256_file(path) != expected.get(str(path)):
                raise ValueError(f'Źródło zmieniło się po audycie: {path}')
        materialized = Path(self.config.workspace) / 'embedded_sources'
        seen = set()
        checked_archives = set()
        for item in report.get('embedded_sources', []):
            archive = Path(item['archive'])
            if archive not in checked_archives:
                if sha256_file(archive) != item['archive_sha256']:
                    raise ValueError(f'Archiwum zmieniło się po audycie: {archive}')
                checked_archives.add(archive)
            if item['sha256'] in seen:
                continue
            seen.add(item['sha256'])
            with zipfile.ZipFile(archive) as z:
                info = z.getinfo(item['member'])
                if info.file_size > 32 * 1024 * 1024:
                    raise ValueError('Za duży plik pamięci wewnątrz ZIP')
                data = z.read(info)
            if hashlib.sha256(data).hexdigest() != item['sha256']:
                raise ValueError('Niezgodny hash pliku wewnątrz ZIP')
            if item.get('repair'):
                from .studio_repair import repair_missing_object_comma
                original = data
                data, recipe = repair_missing_object_comma(data)
                if recipe != item['repair']:
                    raise ValueError('Niezgodny plan naprawy składni JSON')
                original_dir = materialized / item['sha256']
                original_dir.mkdir(parents=True, exist_ok=True)
                (original_dir / 'original.bin').write_bytes(original)
            materialized.mkdir(parents=True, exist_ok=True)
            # Fixed basename and hash directory: never extract a member path.
            dest = materialized / item['sha256'] / ('dziennik.json' if item['role'] == 'journal' else 'analizy_utworow.json')
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_bytes(data)
            elif sha256_file(dest) != hashlib.sha256(data).hexdigest():
                raise ValueError('Zmieniona kopia źródła ZIP')
            write_json(dest.with_suffix('.provenance.json'), item)
            paths.append(dest)
        return paths

    def build(self, *, update: bool = False) -> dict[str, Any]:
        sources = self.sources()
        target = Path(self.config.database).resolve()
        if target.exists() != update:
            raise ValueError('Nowa baza wymaga wolnej ścieżki; aktualizacja istniejącej bazy')
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.with_name(target.stem + '.staging-' + uuid.uuid4().hex + '.sqlite3')
        backup = None
        original_sha = None
        if update:
            # Replacing an active WAL database is unsafe; select an offline copy.
            if any(Path(str(target) + ext).exists() for ext in ('-wal', '-shm')):
                raise ValueError('Baza ma WAL/SHM. Wskaż zamkniętą kopię roboczą')
            original_sha = sha256_file(target)
            backup = Path(self.config.backup_root) / (target.stem + '-' + uuid.uuid4().hex + '.sqlite3')
            snapshot_database(target, backup)
            snapshot_database(backup, staging)
        store = UnifiedMemoryDatabase(staging)
        imported = store.import_sources(sources, full_validation=True)
        if not imported.get('ok'):
            raise ValueError(f'Import nie przeszedł walidacji; zachowano staging: {staging}')
        validation = store.validate(full=True)
        if not validation.get('ok'):
            raise ValueError(f'Niepoprawna baza staging: {staging}')
        store.checkpoint()
        connection = sqlite3.connect(staging)
        try:
            connection.execute('PRAGMA journal_mode=DELETE')
        finally:
            connection.close()
        if update and (sha256_file(target) != original_sha or any(Path(str(target) + ext).exists() for ext in ('-wal', '-shm'))):
            raise ValueError('Baza docelowa zmieniła się w trakcie operacji')
        if not update and target.exists():
            raise FileExistsError(target)
        os.replace(staging, target)
        result = {'ok': True, 'database': str(target), 'backup': str(backup) if backup else None,
                  'validation': validation, 'import': imported, 'release_acceptance': 'NOT RUN',
                  'automatic_activation': False}
        write_json(Path(self.config.report_root) / 'build.json', result)
        return result

    def stage(self, name: str, run_id: str) -> dict[str, Any]:
        if not run_id or Path(run_id).name != run_id or run_id in {'.', '..'} or '/' in run_id or '\\' in run_id:
            raise ValueError('Nieprawidłowy identyfikator sesji testów')
        output = Path(self.config.workspace)
        engine = (ProtocolEngine.resume(output, system_version=PACKAGE_VERSION, base_commit=self.config.base_commit, run_id=run_id)
                  if (output / run_id).exists() else
                  ProtocolEngine(output, system_version=PACKAGE_VERSION, base_commit=self.config.base_commit, run_id=run_id))
        self.sources()  # Verify the immutable source inventory before cached or new stages.
        if name in engine.results and engine.results[name].get('ok'):
            return {**engine.results[name], 'reused_completed_stage': True}
        def finish(result: dict[str, Any]) -> dict[str, Any]:
            engine.checkpoint_manifest()
            return result
        if name == 'test00':
            return finish(engine.run_test00(self.sources()))
        if name == 'test01':
            return finish(engine.run_test01(self.sources()))
        database = (engine.results.get('test02') or engine.results.get('test01') or {}).get('artifacts', {}).get('database')
        if not database:
            raise ValueError('Najpierw ukończ Test01')
        if name == 'test02':
            return finish(engine.run_test02(database))
        if name == 'test03':
            return finish(engine.run_test03(self.sources()))
        if name == 'test04':
            if not self.config.benchmark:
                raise ValueError('W ustawieniach wskaż benchmark recall')
            return finish(engine.run_test04(database, self.config.benchmark))
        if name == 'final':
            return finish(engine.run_final(database, Path(self.config.export_root) / run_id,
                                    test04_result=engine.results.get('test04', {}), sources=self.sources()))
        raise ValueError(name)


def text_studio(path: Path) -> int:
    while True:
        print('\nJaźń - Studio Pamięci\n1. Źródła i statystyki\n2. Utwórz nową bazę\n3. Aktualizuj bazę\n4. Testy etapowe\n5. Powiąż dziennik / analizy\n6. Ustawienia i ścieżki\n7. Przegląd pamięci i kandydatów\n0. Wyjście')
        choice = input('Wybór: ').strip()
        if choice == '0':
            return 0
        try:
            config = StudioConfig.load(path)
            app = MemoryStudio(config)
            result: Any = None
            if choice == '1':
                result = app.scan()
            elif choice in {'2', '3'}:
                result = app.build(update=choice == '3')
            elif choice == '4':
                result = app.stage(input('Etap (test00..test04/final): '), input('Id sesji: '))
            elif choice == '5':
                result = correlate_file(Path(config.catalog), Path(input('Plik JSON dziennika / analiz: ')), window_seconds=config.correlation_window_seconds)
                write_json(Path(config.report_root) / 'correlations.json', result)
            elif choice == '6':
                values = asdict(config)
                for key, current in values.items():
                    value = input(f'{key} [{current}]: ').strip()
                    if value:
                        values[key] = value.lower() in {'true', 'tak', '1'} if isinstance(current, bool) else int(value) if isinstance(current, int) else value
                updated = StudioConfig(**values)
                updated.validate()
                write_json(path, asdict(updated))
                result = {'ok': True, 'settings': str(path)}
            elif choice == '7':
                from .studio import run_studio
                run_studio(database=config.database, project_root=config.workspace, text_ui=True)
            if result is not None:
                print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        except (ValueError, OSError, sqlite3.Error) as exc:
            print(f'Błąd: {exc}')


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Jaźń - Studio Pamięci', allow_abbrev=False)
    parser.add_argument('--config', required=True, type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('configure', allow_abbrev=False)
    init.add_argument('--source-root', required=True, type=Path)
    init.add_argument('--workspace', required=True, type=Path)
    init.add_argument('--base-commit', default='unrecorded')
    for name in ('studio', 'scan', 'create', 'update', 'settings'):
        sub.add_parser(name, allow_abbrev=False)
    stage = sub.add_parser('stage', allow_abbrev=False)
    stage.add_argument('name', choices=('test00', 'test01', 'test02', 'test03', 'test04', 'final'))
    stage.add_argument('--run-id', required=True)
    links = sub.add_parser('link', allow_abbrev=False)
    links.add_argument('source', type=Path)
    search = sub.add_parser('search', allow_abbrev=False)
    search.add_argument('query')
    search.add_argument('--year', type=int)
    search.add_argument('--limit', type=int, default=20)
    args = parser.parse_args(argv)
    try:
        if args.command == 'configure':
            if args.config.exists():
                raise FileExistsError(args.config)
            w = args.workspace.resolve()
            config = StudioConfig(str(args.source_root.resolve()), str(w / 'tests'), str(w / 'database' / 'memory_jazn.sqlite3'),
                                  str(w / 'backups'), str(w / 'exports'), str(w / 'reports'), str(w / 'catalog.sqlite3'), base_commit=args.base_commit)
            config.validate()
            write_json(args.config, asdict(config))
            result = asdict(config)
        else:
            config = StudioConfig.load(args.config)
            app = MemoryStudio(config)
            if args.command == 'studio':
                return text_studio(args.config)
            if args.command == 'settings':
                result = asdict(config)
            elif args.command == 'scan':
                result = app.scan()
            elif args.command in {'create', 'update'}:
                result = app.build(update=args.command == 'update')
            elif args.command == 'link':
                result = correlate_file(Path(config.catalog), args.source, window_seconds=config.correlation_window_seconds)
                write_json(Path(config.report_root) / 'correlations.json', result)
            elif args.command == 'search':
                result = search_catalog(Path(config.catalog), args.query, year=args.year, limit=args.limit)
            else:
                result = app.stage(args.name, args.run_id)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get('ok', True) else 2
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
