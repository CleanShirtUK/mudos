"""Safe multipart ingestion and registry-driven emulator setup files."""

from __future__ import annotations

from dataclasses import dataclass
import email.message
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tempfile
from typing import BinaryIO
import zipfile

from .paths import PATHS
from .platforms import load_platforms

MAX_UPLOAD_BYTES = 1024 * 1024 * 1024
MAX_PARTS = 128
MAX_FORM_FIELD_BYTES = 16 * 1024
_SAFE_ID = re.compile(r"^[a-z0-9_-]{1,48}$")


@dataclass(frozen=True, slots=True)
class UploadedPart:
    field: str
    filename: str
    path: Path


def read_multipart(stream: BinaryIO, content_type: str, content_length: int) -> tuple[dict[str, str], list[UploadedPart]]:
    """Stream a multipart request to temporary files without buffering payloads."""
    message = email.message.Message()
    message["content-type"] = content_type
    boundary = message.get_param("boundary", header="content-type")
    if not boundary or len(boundary) > 200:
        raise ValueError("Invalid multipart boundary")
    marker = b"\r\n--" + boundary.encode("ascii", "strict")
    if content_length < 0 or content_length > MAX_UPLOAD_BYTES:
        raise ValueError("Upload is too large (maximum 1 GiB)")
    remaining = content_length
    pending = bytearray()
    fields: dict[str, str] = {}
    uploads: list[UploadedPart] = []
    temporary_paths: list[Path] = []

    def read(size: int) -> bytes:
        nonlocal remaining
        prefix = b""
        if pending:
            count = min(size, len(pending))
            prefix = bytes(pending[:count])
            del pending[:count]
            size -= count
            if size == 0:
                return prefix
        size = min(size, remaining)
        value = stream.read(size)
        remaining -= len(value)
        if len(value) != size:
            raise ValueError("Multipart request ended unexpectedly")
        return prefix + value

    def readline(limit: int = 8192) -> bytes:
        value = bytearray()
        while len(value) <= limit:
            byte = read(1)
            if not byte:
                break
            value.extend(byte)
            if value.endswith(b"\r\n"):
                return bytes(value)
        raise ValueError("Malformed multipart headers")

    try:
        if read(len(boundary.encode()) + 4) != b"--" + boundary.encode() + b"\r\n":
            raise ValueError("Malformed multipart request")
        finished = False
        while not finished:
            if len(uploads) + len(fields) >= MAX_PARTS:
                raise ValueError("Too many uploaded files")
            headers: dict[str, str] = {}
            while True:
                line = readline()
                if line == b"\r\n":
                    break
                key, separator, value = line.decode("latin-1").partition(":")
                if not separator:
                    raise ValueError("Malformed multipart headers")
                headers[key.strip().casefold()] = value.strip()
            disposition = email.message.Message()
            disposition["content-disposition"] = headers.get("content-disposition", "")
            field = disposition.get_param("name", header="content-disposition")
            filename = disposition.get_filename()
            if not field:
                raise ValueError("Multipart field has no name")
            if filename is None:
                data = bytearray()
                final = _copy_until_boundary(read, marker, pending, data.extend, MAX_FORM_FIELD_BYTES)
                fields[str(field)] = data.decode("utf-8", "strict")
            else:
                descriptor, temporary = tempfile.mkstemp(prefix="mudos-upload-")
                path = Path(temporary)
                temporary_paths.append(path)
                size = 0

                def write(chunk: bytes) -> None:
                    nonlocal size
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise ValueError("Uploaded file is too large")
                    output.write(chunk)

                with os.fdopen(descriptor, "wb") as output:
                    final = _copy_until_boundary(read, marker, pending, write, MAX_UPLOAD_BYTES)
                if filename:
                    uploads.append(UploadedPart(str(field), str(filename), path))
                else:
                    path.unlink(missing_ok=True)
                    temporary_paths.remove(path)
                if final:
                    finished = True
            if filename is None and final:
                finished = True
        return fields, uploads
    except Exception:
        for path in temporary_paths:
            path.unlink(missing_ok=True)
        raise


def _copy_until_boundary(read, marker: bytes, pending: bytearray, write, max_bytes: int) -> bool:
    buffer = bytearray()
    written = 0
    while True:
        chunk = read(min(64 * 1024, max_bytes + len(marker) + 8))
        buffer.extend(chunk)
        position = buffer.find(marker)
        if position >= 0:
            if written + position > max_bytes:
                raise ValueError("Uploaded multipart field is too large")
            write(bytes(buffer[:position]))
            pending[:0] = buffer[position + len(marker):]
            suffix = read(2)
            if suffix == b"--":
                trailer = read(2)
                if trailer not in {b"", b"\r\n"}:
                    raise ValueError("Malformed final multipart delimiter")
                return True
            if suffix != b"\r\n":
                raise ValueError("Malformed multipart delimiter")
            return False
        flush = max(0, len(buffer) - len(marker) - 2)
        if flush:
            written += flush
            if written > max_bytes:
                raise ValueError("Uploaded multipart field is too large")
            write(bytes(buffer[:flush]))
            del buffer[:flush]


def file_setup_manifest(selected_providers: set[str] | None = None) -> list[dict[str, object]]:
    selected = selected_providers or set()
    result = []
    for platform, definition in load_platforms().items():
        if not definition.setup_files:
            continue
        provider = definition.default_provider or ""
        if selected and provider not in selected:
            continue
        requirements = []
        for requirement in definition.setup_files:
            target = PATHS.bios_root / requirement.destination
            present = sorted(path.name for path in target.iterdir() if path.is_file()) if target.is_dir() else []
            requirements.append({
                "id": requirement.requirement_id, "label": requirement.label,
                "description": requirement.description, "extensions": list(requirement.extensions),
                "multiple": requirement.multiple, "archive": requirement.archive,
                "required": requirement.required, "required_names": list(requirement.required_names),
                "present": present,
                "ready": (bool(present) and all(name.casefold() in {item.casefold() for item in present}
                                                 for name in requirement.required_names)),
            })
        result.append({"platform": platform, "platform_label": definition.name,
                       "provider": provider, "requirements": requirements})
    return result


def save_platform_files(platform: str, requirement_id: str,
                        uploads: list[UploadedPart]) -> list[str]:
    if not _SAFE_ID.fullmatch(platform) or not _SAFE_ID.fullmatch(requirement_id):
        raise ValueError("Invalid platform setup file selection")
    definition = load_platforms().get(platform)
    if definition is None:
        raise ValueError("Unknown platform")
    requirement = next((item for item in definition.setup_files
                       if item.requirement_id == requirement_id), None)
    if requirement is None:
        raise ValueError("Unknown platform file requirement")
    if not uploads:
        raise ValueError("Choose at least one file to upload")
    if not requirement.multiple and len(uploads) > 1:
        raise ValueError("Choose one file for this requirement")
    allowed = set(requirement.extensions)
    destination = (PATHS.bios_root / requirement.destination).resolve()
    root = PATHS.bios_root.resolve()
    if destination != root and root not in destination.parents:
        raise ValueError("Invalid file destination")
    destination.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    try:
        for upload in uploads:
            name = Path(upload.filename.replace("\\", "/")).name
            if (name in {"", ".", ".."} or "/" in upload.filename or "\\" in upload.filename):
                raise ValueError("Uploaded filename is invalid")
            if Path(name).suffix.casefold() not in allowed:
                raise ValueError(f"Unsupported file type: {name}")
            if requirement.archive:
                if Path(name).suffix.casefold() != ".zip":
                    raise ValueError("This requirement accepts a ZIP archive")
                saved.extend(_extract_firmware_zip(upload.path, destination))
            else:
                target = destination / name
                temporary = target.with_name(f".{target.name}.upload-{os.getpid()}")
                shutil.copyfile(upload.path, temporary)
                os.chmod(temporary, 0o600)
                os.replace(temporary, target)
                saved.append(name)
        os.chmod(destination, 0o700)
        return saved
    finally:
        for upload in uploads:
            upload.path.unlink(missing_ok=True)


def _extract_firmware_zip(archive: Path, destination: Path) -> list[str]:
    extracted: list[str] = []
    total = 0
    try:
        bundle = zipfile.ZipFile(archive)
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError("Firmware archive is invalid or unreadable") from error
    with bundle:
        members = [item for item in bundle.infolist() if not item.is_dir()]
        if not members or len(members) > 10000:
            raise ValueError("Firmware ZIP is empty or contains too many files")
        for item in members:
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or not path.parts or "\\" in item.filename:
                raise ValueError("Firmware ZIP contains an unsafe path")
            unix_mode = item.external_attr >> 16
            if unix_mode & 0o170000 == 0o120000:
                raise ValueError("Firmware ZIP may not contain symbolic links")
            total += item.file_size
            if total > MAX_UPLOAD_BYTES:
                raise ValueError("Expanded firmware archive is too large")
            target = destination.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            resolved = target.resolve()
            if destination.resolve() not in resolved.parents:
                raise ValueError("Firmware ZIP contains an unsafe path")
            with bundle.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, 1024 * 1024)
            os.chmod(target, 0o600)
            extracted.append(str(path))
    return extracted
