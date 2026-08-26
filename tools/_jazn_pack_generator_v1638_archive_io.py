from __future__ import annotations

import contextlib
import contextvars
import json
import os
import re
import shutil
import sys
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Iterator, Sequence

from latka_jazn.archive import (
    ArchiveError,
    ArchiveExtractionService,
    ArchiveSecurityLimits,
    ArchiveWriteEntry,
    normalize_archive_format,
)

ARCHIVE_IO_EXTENSION_VERSION = "1.0"
ARCHIVE_IO_CONTRACT = "jazn_archive_io/v1"
CONTAINER_FORMAT_CHOICES = ("zip", "7z", "aes_zip", "pyzip", "pyzipfile")
DEFAULT_PASSWORD_ENV = "JAZN_ARCHIVE_PASSWORD"


@dataclass(frozen=True, slots=True)
class GeneratorArchiveSettings:
    container_format: str = "zip"
    aes_bits: int = 256
    password_env: str = DEFAULT_PASSWORD_ENV
    encrypt_7z: bool = False
    max_members: int = 200_000
    max_total_gib: float = 64.0
    max_member_gib: float = 16.0
    max_ratio: float = 500.0
    require_free_space: bool = True

    def normalized(self) -> "GeneratorArchiveSettings":
        fmt = normalize_archive_format(self.container_format)
        if fmt == "auto":
            fmt = "zip"
        if int(self.aes_bits) not in {128, 192, 256}:
            raise ValueError("aes_bits_must_be_128_192_or_256")
        if not str(self.password_env).strip():
            raise ValueError("password_env_must_not_be_empty")
        if int(self.max_members) <= 0:
            raise ValueError("max_members_must_be_positive")
        if float(self.max_total_gib) <= 0 or float(self.max_member_gib) <= 0:
            raise ValueError("archive_size_limits_must_be_positive")
        if float(self.max_ratio) <= 0:
            raise ValueError("max_ratio_must_be_positive")
        return replace(
            self,
            container_format=fmt,
            aes_bits=int(self.aes_bits),
            password_env=str(self.password_env).strip(),
            max_members=int(self.max_members),
            max_total_gib=float(self.max_total_gib),
            max_member_gib=float(self.max_member_gib),
            max_ratio=float(self.max_ratio),
        )

    def limits(self) -> ArchiveSecurityLimits:
        value = self.normalized()
        return ArchiveSecurityLimits(
            max_members=value.max_members,
            max_total_uncompressed_bytes=int(value.max_total_gib * 1024**3),
            max_member_bytes=int(value.max_member_gib * 1024**3),
            max_compression_ratio=value.max_ratio,
            require_free_space=value.require_free_space,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.normalized())


_ARCHIVE_CONTEXT: contextvars.ContextVar[GeneratorArchiveSettings | None] = contextvars.ContextVar(
    "jazn_pack_generator_archive_io_settings", default=None
)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _settings_from_mapping(raw: Any) -> GeneratorArchiveSettings:
    if not isinstance(raw, dict):
        return GeneratorArchiveSettings()
    defaults = GeneratorArchiveSettings()
    allowed = {field: raw.get(field, getattr(defaults, field)) for field in asdict(defaults)}
    try:
        return GeneratorArchiveSettings(**allowed).normalized()
    except (TypeError, ValueError):
        return defaults


def _archive_settings_path(core: Any) -> Path:
    return Path(core.settings_path())


def load_archive_settings(core: Any) -> GeneratorArchiveSettings:
    payload = _read_json(_archive_settings_path(core))
    return _settings_from_mapping(payload.get("archive_io"))


def save_archive_settings(core: Any, settings: GeneratorArchiveSettings) -> Path:
    settings = settings.normalized()
    path = _archive_settings_path(core)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _read_json(path)
    payload.setdefault("schema_version", getattr(core, "SETTINGS_SCHEMA", "jazn_pack_generator_settings/v8.5"))
    payload["archive_io"] = settings.to_dict()
    temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return path


def current_archive_settings(core: Any) -> GeneratorArchiveSettings:
    explicit = _ARCHIVE_CONTEXT.get()
    return explicit.normalized() if explicit is not None else load_archive_settings(core)


@contextlib.contextmanager
def archive_settings_override(settings: GeneratorArchiveSettings) -> Iterator[None]:
    token = _ARCHIVE_CONTEXT.set(settings.normalized())
    try:
        yield
    finally:
        _ARCHIVE_CONTEXT.reset(token)


def _password(settings: GeneratorArchiveSettings) -> str | None:
    return os.environ.get(settings.password_env)


def _replace_archive_extension(base_zip_name: str, container_format: str) -> str:
    extension = ".7z" if container_format == "7z" else ".zip"
    name = str(base_zip_name)
    if name.lower().endswith(".zip"):
        return name[:-4] + extension
    if name.lower().endswith(".7z"):
        return name[:-3] + extension
    return name + extension


def _independent_volume_name(base_archive_name: str, number: int) -> str:
    if number == 1:
        return base_archive_name
    suffix = Path(base_archive_name).suffix or ".archive"
    stem = base_archive_name[: -len(suffix)] if suffix else base_archive_name
    return f"{stem}.part{number:03d}{suffix}"


def _write_entries(plan_entries: Sequence[Any]) -> list[ArchiveWriteEntry]:
    rows: list[ArchiveWriteEntry] = []
    for entry in plan_entries:
        if entry.virtual_bytes is not None:
            rows.append(ArchiveWriteEntry(entry.relative, data=entry.virtual_bytes))
        elif entry.source is not None:
            rows.append(ArchiveWriteEntry(entry.relative, source=Path(entry.source)))
        else:
            raise ArchiveError(f"plan_entry_has_no_source:{entry.relative}")
    return rows


def _known_output_paths(out_dir: Path, base_archive_name: str) -> list[Path]:
    if not out_dir.exists():
        return []
    suffix = Path(base_archive_name).suffix
    stem = base_archive_name[: -len(suffix)] if suffix else base_archive_name
    patterns = (
        re.compile(rf"^{re.escape(base_archive_name)}$", re.I),
        re.compile(rf"^{re.escape(stem)}\.part\d{{3}}{re.escape(suffix)}$", re.I),
        re.compile(rf"^{re.escape(base_archive_name)}\.\d{{3,4}}$", re.I),
        re.compile(rf"^{re.escape(base_archive_name)}\.(?:package\.json|join\.ps1|parts\.sha256|sha256)$", re.I),
    )
    return sorted(path for path in out_dir.iterdir() if path.is_file() and any(p.match(path.name) for p in patterns))


def _settings_from_cli(settings: GeneratorArchiveSettings, argv: Sequence[str]) -> GeneratorArchiveSettings:
    values = list(argv)

    def option(name: str) -> str | None:
        try:
            index = values.index(name)
        except ValueError:
            return None
        if index + 1 >= len(values):
            return None
        return values[index + 1]

    updates: dict[str, Any] = {}
    raw = option("--container-format")
    if raw is not None:
        updates["container_format"] = raw
    raw = option("--aes-bits")
    if raw is not None:
        updates["aes_bits"] = int(raw)
    raw = option("--password-env")
    if raw is not None:
        updates["password_env"] = raw
    raw = option("--extract-max-members")
    if raw is not None:
        updates["max_members"] = int(raw)
    raw = option("--extract-max-total-gib")
    if raw is not None:
        updates["max_total_gib"] = float(raw)
    raw = option("--extract-max-member-gib")
    if raw is not None:
        updates["max_member_gib"] = float(raw)
    raw = option("--extract-max-ratio")
    if raw is not None:
        updates["max_ratio"] = float(raw)
    if "--encrypt-7z" in values:
        updates["encrypt_7z"] = True
    if "--no-encrypt-7z" in values:
        updates["encrypt_7z"] = False
    if "--no-archive-free-space-check" in values:
        updates["require_free_space"] = False
    if "--archive-free-space-check" in values:
        updates["require_free_space"] = True
    return replace(settings, **updates).normalized()


def apply(impl: Any) -> None:
    """Attach v16.3.8 archive I/O without rewriting the stable v8.5 UI core."""

    if getattr(impl, "_JAZN_V1638_ARCHIVE_IO_APPLIED", False):
        return
    core = impl._core
    original_parser = core.parser
    original_main = core.main
    original_package_one = core.package_one
    original_sidecar_payload = core.sidecar_payload
    original_verify = core.verify_package_sidecar
    original_extract = core.extract_package_sidecar
    original_save_state = core.save_interactive_state
    original_settings_preview = core.settings_preview_lines
    original_text_options = core._text_options_menu

    def parser() -> Any:
        parsed = original_parser()
        sub_action = next(
            (
                action
                for action in getattr(parsed, "_actions", [])
                if isinstance(getattr(action, "choices", None), dict)
            ),
            None,
        )
        if sub_action is None:
            return parsed
        for command in ("pack", "verify", "extract"):
            command_parser = sub_action.choices.get(command)
            if command_parser is None:
                continue
            existing = {getattr(action, "dest", "") for action in command_parser._actions}
            if "container_format" not in existing:
                command_parser.add_argument(
                    "--container-format",
                    choices=CONTAINER_FORMAT_CHOICES,
                    default=None,
                    help="Kontener: zip (domyślnie), 7z albo aes_zip; pyzip/PyZipFile są aliasami ZIP.",
                )
            if "archive_password_env" not in existing:
                command_parser.add_argument("--password-env", dest="archive_password_env", default=None)
            if "archive_aes_bits" not in existing:
                command_parser.add_argument("--aes-bits", dest="archive_aes_bits", type=int, choices=(128, 192, 256), default=None)
            if "archive_max_members" not in existing:
                command_parser.add_argument("--extract-max-members", dest="archive_max_members", type=int, default=None)
                command_parser.add_argument("--extract-max-total-gib", dest="archive_max_total_gib", type=float, default=None)
                command_parser.add_argument("--extract-max-member-gib", dest="archive_max_member_gib", type=float, default=None)
                command_parser.add_argument("--extract-max-ratio", dest="archive_max_ratio", type=float, default=None)
                command_parser.add_argument("--encrypt-7z", action="store_true")
                command_parser.add_argument("--no-encrypt-7z", action="store_true")
                command_parser.add_argument("--archive-free-space-check", action="store_true")
                command_parser.add_argument("--no-archive-free-space-check", action="store_true")
        if "archive-settings" not in sub_action.choices:
            settings_parser = sub_action.add_parser(
                "archive-settings",
                help="Pokaż lub zmień trwałe ustawienia kontenera i bezpiecznej ekstrakcji.",
                allow_abbrev=False,
            )
            settings_parser.add_argument("--container-format", choices=CONTAINER_FORMAT_CHOICES)
            settings_parser.add_argument("--aes-bits", type=int, choices=(128, 192, 256))
            settings_parser.add_argument("--password-env")
            settings_parser.add_argument("--extract-max-members", type=int)
            settings_parser.add_argument("--extract-max-total-gib", type=float)
            settings_parser.add_argument("--extract-max-member-gib", type=float)
            settings_parser.add_argument("--extract-max-ratio", type=float)
            settings_parser.add_argument("--encrypt-7z", action="store_true")
            settings_parser.add_argument("--no-encrypt-7z", action="store_true")
            settings_parser.add_argument("--archive-free-space-check", action="store_true")
            settings_parser.add_argument("--no-archive-free-space-check", action="store_true")
        return parsed

    def sidecar_payload(*args: Any, **kwargs: Any) -> dict[str, Any]:
        payload = original_sidecar_payload(*args, **kwargs)
        settings = current_archive_settings(core)
        container = normalize_archive_format(settings.container_format)
        logical = payload.get("logical_zip_sha256")
        payload["container_format"] = container
        payload["archive_io_contract"] = ARCHIVE_IO_CONTRACT
        payload["archive_io_extension_version"] = ARCHIVE_IO_EXTENSION_VERSION
        payload["logical_archive_sha256"] = logical
        if container == "7z":
            payload["compression"] = "7Z_LZMA2"
            payload["logical_zip_sha256"] = None
        elif container == "aes_zip":
            payload["compression"] = "ZIP_DEFLATED+WZ_AES"
        payload["encryption"] = {
            "enabled": container == "aes_zip" or (container == "7z" and settings.encrypt_7z),
            "method": (
                f"WZ_AES_{settings.aes_bits}" if container == "aes_zip"
                else "7Z_AES256" if container == "7z" and settings.encrypt_7z
                else "none"
            ),
            "password_source": "environment" if container == "aes_zip" or settings.encrypt_7z else "none",
            "password_env": settings.password_env if container == "aes_zip" or settings.encrypt_7z else None,
            "secret_persisted": False,
        }
        payload["extraction_limits"] = settings.limits().to_dict()
        return payload

    def package_one(plan: Any, options: Any, base_zip_name: str) -> Any:
        settings = current_archive_settings(core)
        container = normalize_archive_format(settings.container_format)
        if container == "zip":
            return original_package_one(plan, options, base_zip_name)
        password = _password(settings)
        if container == "aes_zip" and password is None:
            raise core.PackError(f"Brak hasła AES-ZIP w zmiennej środowiskowej {settings.password_env!r}.")
        if container == "7z" and settings.encrypt_7z and password is None:
            raise core.PackError(f"Włączono szyfrowanie 7z, ale brak hasła w {settings.password_env!r}.")
        archive_password = password if container == "aes_zip" or settings.encrypt_7z else None
        service = ArchiveExtractionService(settings.limits())
        core.validate_system_plan_release_metadata(plan)
        part_size = int(options.part_size_mb) * 1024 * 1024
        volume_format = core.choose_format(options.archive_format, plan, part_size)
        archive_name = _replace_archive_extension(base_zip_name, container)
        options.out_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = core.create_pack_staging_dir(options.out_dir, archive_name)
        try:
            outputs: list[Any] = []
            logical_hash: str | None = None
            if volume_format == "independent":
                accepted: list[Path] = []

                def emit(entries: list[Any]) -> None:
                    candidate = temp_dir / f".candidate-{uuid.uuid4().hex}{Path(archive_name).suffix}"
                    service.create_archive(
                        _write_entries(entries),
                        candidate,
                        archive_format=container,
                        compression_level=options.compression_level,
                        password=archive_password,
                        aes_bits=settings.aes_bits,
                    )
                    if candidate.stat().st_size > part_size and len(entries) > 1:
                        candidate.unlink()
                        left, right = core.split_group_by_size(entries)
                        emit(left)
                        emit(right)
                        return
                    accepted.append(candidate)

                for group in core.initial_groups(plan.entries, part_size):
                    emit(group)
                for index, candidate in enumerate(accepted, start=1):
                    name = _independent_volume_name(archive_name, index)
                    target = temp_dir / name
                    os.replace(candidate, target)
                    outputs.append(
                        core.OutputPart(
                            filename=name,
                            size_bytes=target.stat().st_size,
                            sha256=core.sha256_file(target),
                            part_no=index,
                            is_complete_zip=True,
                        )
                    )
            elif volume_format == "binary":
                logical = temp_dir / f".logical-{uuid.uuid4().hex}{Path(archive_name).suffix}"
                service.create_archive(
                    _write_entries(plan.entries),
                    logical,
                    archive_format=container,
                    compression_level=options.compression_level,
                    password=archive_password,
                    aes_bits=settings.aes_bits,
                )
                rows, logical_hash = service.split_file(logical, temp_dir, archive_name, part_size)
                logical.unlink(missing_ok=True)
                outputs = [
                    core.OutputPart(
                        filename=str(row["filename"]),
                        size_bytes=int(row["size_bytes"]),
                        sha256=str(row["sha256"]),
                        part_no=int(row["part_no"]),
                        is_complete_zip=False,
                    )
                    for row in rows
                ]
            else:
                raise core.PackError(f"Nieobsługiwany układ woluminów: {volume_format}")

            payload = sidecar_payload(
                archive_name,
                plan,
                volume_format,
                part_size,
                options.compression_level,
                outputs,
                logical_hash,
                {"ok": None, "status": "pending_archive_io_verification"},
            )
            if container == "7z":
                payload["logical_archive_sha256"] = logical_hash
                payload["logical_zip_sha256"] = None
            sidecar_name = f"{archive_name}.package.json"
            sidecar_temp = temp_dir / sidecar_name
            sidecar_temp.write_bytes(core.serialize_json(payload))

            verify_dir = temp_dir / ".verification-extract"
            try:
                verification = service.extract_package_sidecar(
                    sidecar_temp,
                    verify_dir,
                    password=archive_password,
                    replace_existing=False,
                )
            except ArchiveError as exc:
                raise core.PackError(f"Weryfikacja {container} nie przeszła: {exc}") from exc
            finally:
                shutil.rmtree(verify_dir, ignore_errors=True)
            verification["compatibility"] = {
                "ok": True,
                "results": [
                    {
                        "tool": "ArchiveExtractionService",
                        "backend": "py7zr" if container == "7z" else "pyzipper",
                        "status": "passed",
                    }
                ],
                "external_password_on_command_line": False,
            }
            payload["verification"] = verification
            sidecar_temp.write_bytes(core.serialize_json(payload))

            extra_names = [sidecar_name]
            if options.sidecars:
                parts_name = f"{archive_name}.parts.sha256"
                (temp_dir / parts_name).write_text(
                    "".join(f"{item.sha256}  {item.filename}\n" for item in outputs),
                    encoding="ascii",
                )
                extra_names.append(parts_name)
                if logical_hash:
                    hash_name = f"{archive_name}.sha256"
                    (temp_dir / hash_name).write_text(f"{logical_hash}  {archive_name}\n", encoding="ascii")
                    extra_names.append(hash_name)
                    join_path = core.write_join_ps1(temp_dir, archive_name, outputs, logical_hash)
                    extra_names.append(join_path.name)
            filenames = [item.filename for item in outputs] + extra_names
            committed = core.commit_transaction(
                temp_dir,
                options.out_dir,
                filenames,
                archive_name,
                options.force,
            )
            return core.PackageResult(
                package_name=archive_name,
                profile=plan.profile,
                archive_format=volume_format,
                plan=plan,
                outputs=list(outputs),
                logical_zip_sha256=logical_hash,
                package_set_sha256=core.package_set_hash(outputs),
                sidecar_path=options.out_dir / sidecar_name,
                committed_paths=committed,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def verify_package_sidecar(sidecar: Path) -> dict[str, Any]:
        path = Path(sidecar).expanduser().resolve()
        payload = _read_json(path)
        container = normalize_archive_format(str(payload.get("container_format") or "zip")) if payload else "zip"
        if container == "zip" and path.name.endswith(".package.json"):
            return original_verify(path)
        settings = current_archive_settings(core)
        service = ArchiveExtractionService(settings.limits())
        password = _password(settings)
        try:
            if path.name.endswith(".package.json"):
                return service.verify_package_sidecar(path, password=password)
            inspection = service.inspect(path, archive_format=container, password=password, verify_crc=True)
            return {"ok": True, "source": str(path), **inspection.to_dict()}
        except ArchiveError as exc:
            raise core.PackError(str(exc)) from exc

    def extract_package_sidecar(
        sidecar: Path,
        destination: Path,
        *,
        clean: bool = False,
        force: bool = False,
    ) -> dict[str, Any]:
        path = Path(sidecar).expanduser().resolve()
        payload = _read_json(path) if path.name.endswith(".package.json") else {}
        container = normalize_archive_format(str(payload.get("container_format") or "zip")) if payload else "auto"
        if container == "zip" and path.name.endswith(".package.json"):
            return original_extract(path, destination, clean=clean, force=force)
        settings = current_archive_settings(core)
        service = ArchiveExtractionService(settings.limits())
        password = _password(settings)
        try:
            return service.extract_source(
                path,
                destination,
                archive_format=container,
                password=password,
                replace_existing=bool(clean or force),
            )
        except ArchiveError as exc:
            raise core.PackError(str(exc)) from exc

    def save_interactive_state(state: Any) -> Path:
        settings = current_archive_settings(core)
        path = Path(original_save_state(state))
        payload = _read_json(path)
        payload["archive_io"] = settings.to_dict()
        temp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, path)
        return path

    def settings_preview_lines(state: Any) -> list[str]:
        lines = list(original_settings_preview(state))
        settings = current_archive_settings(core)
        lines.extend(
            [
                "",
                "Archive I/O:",
                f"  Kontener: {settings.container_format}",
                f"  AES: {settings.aes_bits} bit",
                f"  Szyfrowanie 7z: {'TAK' if settings.encrypt_7z else 'NIE'}",
                f"  Zmienna hasła: {settings.password_env} (wartość NIE jest zapisywana)",
                f"  Limity: {settings.max_members} plików / {settings.max_member_gib:g} GiB plik / {settings.max_total_gib:g} GiB razem / ratio {settings.max_ratio:g}",
                "  Edycja: jazn_pack_generator.py archive-settings",
            ]
        )
        return lines

    def _archive_settings_text() -> None:
        settings = current_archive_settings(core)
        while True:
            print("\nARCHIVE I/O")
            print(f"  1. Kontener: [{settings.container_format}]")
            print(f"  2. AES: [{settings.aes_bits} bit]")
            print(f"  3. Szyfrowanie 7z: [{'TAK' if settings.encrypt_7z else 'NIE'}]")
            print(f"  4. Zmienna hasła: [{settings.password_env}]")
            print(f"  5. Maks. wpisów: [{settings.max_members}]")
            print(f"  6. Maks. rozmiar pliku: [{settings.max_member_gib:g} GiB]")
            print(f"  7. Maks. rozmiar łącznie: [{settings.max_total_gib:g} GiB]")
            print(f"  8. Maks. współczynnik kompresji: [{settings.max_ratio:g}]")
            print(f"  9. Kontrola wolnego miejsca: [{'TAK' if settings.require_free_space else 'NIE'}]")
            print("  10. Wróć")
            raw = input("Wybór: ").strip()
            if raw == "10":
                return
            try:
                choice = int(raw)
                if choice == 1:
                    value = input(f"Kontener {CONTAINER_FORMAT_CHOICES} [{settings.container_format}]: ").strip()
                    if value:
                        settings = replace(settings, container_format=value).normalized()
                elif choice == 2:
                    value = input(f"AES 128/192/256 [{settings.aes_bits}]: ").strip()
                    if value:
                        settings = replace(settings, aes_bits=int(value)).normalized()
                elif choice == 3:
                    settings = replace(settings, encrypt_7z=not settings.encrypt_7z)
                elif choice == 4:
                    value = input(f"Nazwa zmiennej [{settings.password_env}]: ").strip()
                    if value:
                        settings = replace(settings, password_env=value).normalized()
                elif choice == 5:
                    settings = replace(settings, max_members=int(input("Limit: ").strip())).normalized()
                elif choice == 6:
                    settings = replace(settings, max_member_gib=float(input("GiB: ").strip())).normalized()
                elif choice == 7:
                    settings = replace(settings, max_total_gib=float(input("GiB: ").strip())).normalized()
                elif choice == 8:
                    settings = replace(settings, max_ratio=float(input("Ratio: ").strip())).normalized()
                elif choice == 9:
                    settings = replace(settings, require_free_space=not settings.require_free_space)
                else:
                    continue
                save_archive_settings(core, settings)
                _ARCHIVE_CONTEXT.set(settings)
            except (ValueError, OSError) as exc:
                print(f"BŁĄD: {exc}")

    def text_options_menu(state: Any) -> None:
        original_text_options(state)
        answer = input("Otworzyć dodatkowe ustawienia Archive I/O? [t/N]: ").strip().lower()
        if answer in {"t", "tak", "y", "yes"}:
            _archive_settings_text()

    def _archive_settings_command(argv: Sequence[str]) -> int:
        args = parser().parse_args(list(argv))
        settings = load_archive_settings(core)
        updates: dict[str, Any] = {}
        for attr, field in (
            ("container_format", "container_format"),
            ("aes_bits", "aes_bits"),
            ("password_env", "password_env"),
            ("extract_max_members", "max_members"),
            ("extract_max_total_gib", "max_total_gib"),
            ("extract_max_member_gib", "max_member_gib"),
            ("extract_max_ratio", "max_ratio"),
        ):
            value = getattr(args, attr, None)
            if value is not None:
                updates[field] = value
        if getattr(args, "encrypt_7z", False):
            updates["encrypt_7z"] = True
        if getattr(args, "no_encrypt_7z", False):
            updates["encrypt_7z"] = False
        if getattr(args, "archive_free_space_check", False):
            updates["require_free_space"] = True
        if getattr(args, "no_archive_free_space_check", False):
            updates["require_free_space"] = False
        if updates:
            settings = replace(settings, **updates).normalized()
            save_archive_settings(core, settings)
        print(json.dumps({"ok": True, "settings_path": str(_archive_settings_path(core)), "archive_io": settings.to_dict()}, ensure_ascii=False, indent=2))
        return 0

    def main(argv: Sequence[str] | None = None) -> int:
        raw = list(sys.argv[1:] if argv is None else argv)
        if raw and raw[0] == "archive-settings":
            return _archive_settings_command(raw)
        settings = _settings_from_cli(load_archive_settings(core), raw)
        token = _ARCHIVE_CONTEXT.set(settings)
        try:
            return int(original_main(raw))
        finally:
            _ARCHIVE_CONTEXT.reset(token)

    core.parser = parser
    impl.parser = parser
    core.main = main
    core.package_one = package_one
    impl.package_one = package_one
    core.sidecar_payload = sidecar_payload
    impl.sidecar_payload = sidecar_payload
    core.verify_package_sidecar = verify_package_sidecar
    impl.verify_package_sidecar = verify_package_sidecar
    core.extract_package_sidecar = extract_package_sidecar
    impl.extract_package_sidecar = extract_package_sidecar
    core.save_interactive_state = save_interactive_state
    impl.save_interactive_state = save_interactive_state
    core.settings_preview_lines = settings_preview_lines
    impl.settings_preview_lines = settings_preview_lines
    core._text_options_menu = text_options_menu
    impl._text_options_menu = text_options_menu
    core.known_output_paths = _known_output_paths
    impl.known_output_paths = _known_output_paths
    impl.ARCHIVE_IO_EXTENSION_VERSION = ARCHIVE_IO_EXTENSION_VERSION
    impl.ARCHIVE_IO_CONTRACT = ARCHIVE_IO_CONTRACT
    impl.CONTAINER_FORMAT_CHOICES = CONTAINER_FORMAT_CHOICES
    impl.GeneratorArchiveSettings = GeneratorArchiveSettings
    impl.load_archive_settings = lambda: load_archive_settings(core)
    impl.save_archive_settings = lambda settings: save_archive_settings(core, settings)
    impl.current_archive_settings = lambda: current_archive_settings(core)
    impl.archive_settings_override = archive_settings_override
    impl._ARCHIVE_CONTEXT = _ARCHIVE_CONTEXT
    impl._JAZN_V1638_ARCHIVE_IO_APPLIED = True
