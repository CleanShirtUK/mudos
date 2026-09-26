"""Flatpak adapter; all Flatpak-specific imports and protocol details live here."""

from __future__ import annotations

import asyncio
import configparser
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET
from typing import AsyncIterator, Callable
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from ...job_manager import JobCancelled, JobExecutionError, JobReporter
from ...jobs import DownloadJob, JobOperation, JobState


class FlatpakError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _flatpak_operation_failure(application_id: str, output: list[str]) -> FlatpakError:
    """Translate known missing-runtime failures without hiding the requested ref."""
    text = "\n".join(output)
    runtime_ref = re.search(
        r"(?:runtime/)?(org\.freedesktop\.[A-Za-z0-9.]+/(?:x86_64|aarch64)/[A-Za-z0-9._-]+)", text)
    lowered = text.casefold()
    missing_dependency = ("not found", "not installed", "was not found", "no such ref",
                          "could not find", "couldn't find", "not available")
    if runtime_ref and "runtime" in lowered and any(phrase in lowered for phrase in missing_dependency):
        return FlatpakError(
            "runtime-unavailable",
            f"Cannot install {application_id}: required runtime {runtime_ref.group(1)} "
            "is unavailable from the configured Flathub metadata. Flatpak normally installs "
            "runtime dependencies automatically; refresh Flathub appstream metadata and verify "
            "that this exact runtime branch is published before retrying.", retryable=True)
    return FlatpakError(
        "operation-failed",
        f"Flatpak could not install {application_id}. Refresh Flathub metadata, then retry; "
        "if it fails again, inspect the application and required runtime refs.", retryable=True)


@dataclass(frozen=True, slots=True)
class FlatpakApplication:
    application_id: str
    name: str
    summary: str = ""
    version: str = ""
    branch: str = ""
    arch: str = ""
    remote: str = ""
    scope: str = "remote"
    installed: bool = False
    update_available: bool = False
    categories: tuple[str, ...] = ()
    icon: str = ""
    commit: str = ""

    @property
    def game(self) -> bool:
        categories = {item.casefold() for item in self.categories}
        return bool(categories & {"game", "games", "arcadegame", "strategygame", "actiongame"})

    @property
    def game_id(self) -> str:
        return f"flatpak:{self.application_id}"


class FlatpakAdapter:
    """Prefer libflatpak when present, with a safe CLI fallback."""

    provider_id = "flatpak"
    provider_ids = ("flatpak",)
    supports_pause = False

    def __init__(self, *, command: str | None = None,
                 runner: Callable[..., object] | None = None):
        self.command = command or shutil.which("flatpak")
        self._runner = runner
        self._gi = self._load_gi()

    @staticmethod
    def _load_gi():
        try:
            import gi
            gi.require_version("Flatpak", "1.0")
            from gi.repository import Flatpak
            return Flatpak
        except (ImportError, ValueError, AttributeError):
            return None

    @property
    def available(self) -> bool:
        return bool(self.command or self._gi)

    @property
    def api(self) -> str:
        return "libflatpak" if self._gi is not None else "flatpak-cli" if self.command else "unavailable"

    def _installation(self):
        if self._gi is None:
            return None
        return self._gi.Installation.new_user()

    @staticmethod
    def _appstream_records(path: str | None) -> dict[str, dict[str, object]]:
        """Read AppStream components without making AppStream a core dependency."""
        records: dict[str, dict[str, object]] = {}
        if not path:
            return records
        xml_path = Path(path) / "appstream.xml"
        if not xml_path.exists():
            xml_path = Path(path) / "appstream.xml.gz"
            if xml_path.exists():
                import gzip
                source = gzip.open(xml_path, "rb")
            else:
                return records
        else:
            source = xml_path.open("rb")
        try:
            for _, element in ET.iterparse(source, events=("end",)):
                if element.tag.rsplit("}", 1)[-1] != "component":
                    continue
                identifier = next((child.text or "" for child in element
                                   if child.tag.rsplit("}", 1)[-1] == "id"), "")
                values: dict[str, object] = {}
                for child in element:
                    tag = child.tag.rsplit("}", 1)[-1]
                    if tag in {"name", "summary", "description"}:
                        values[tag] = " ".join("".join(child.itertext()).split())
                    elif tag == "categories":
                        values["categories"] = tuple(
                            "".join(item.itertext()).strip() for item in child
                            if "".join(item.itertext()).strip()
                        )
                    elif tag == "icon":
                        values["icon"] = "".join(child.itertext()).strip()
                if identifier:
                    records[identifier] = values
                element.clear()
        finally:
            source.close()
        return records

    def _native_catalog(self, query: str = "") -> tuple[FlatpakApplication, ...]:
        installation = self._installation()
        if installation is None:
            return ()
        result: list[FlatpakApplication] = []
        for remote in installation.list_remotes():
            if remote.get_noenumerate() or remote.get_disabled():
                continue
            refs = installation.list_remote_refs_sync(remote.get_name())
            appstream = remote.get_appstream_dir()
            appstream_path = appstream.get_path() if appstream else None
            metadata_records = self._appstream_records(appstream_path)
            for ref in refs:
                if str(ref.get_kind()).casefold() not in {"0", "app"}:
                    continue
                application_id = ref.get_name()
                metadata = metadata_records.get(application_id, {})
                name = str(metadata.get("name") or application_id)
                summary = str(metadata.get("summary") or "")
                if query and query.casefold() not in " ".join((application_id, name, summary)).casefold():
                    continue
                result.append(FlatpakApplication(
                    application_id, name, summary=summary, branch=ref.get_branch(),
                    arch=ref.get_arch(), remote=remote.get_name(),
                    categories=tuple(metadata.get("categories", ())),
                    icon=str(metadata.get("icon") or ""), commit=ref.get_commit(),
                ))
        return tuple(result)

    def _native_installed(self, *, user: bool = True) -> tuple[FlatpakApplication, ...]:
        if not user:
            if self._gi is None:
                return ()
            installation = self._native_installation_for(False)
            result = []
            for ref in installation.list_installed_refs_by_kind(self._gi.RefKind.APP):
                result.append(FlatpakApplication(
                    ref.get_name(), ref.get_appdata_name() or ref.get_name(),
                    summary=ref.get_appdata_summary() or "", version=ref.get_appdata_version() or "",
                    branch=ref.get_branch(), arch=ref.get_arch(), remote=ref.get_origin(),
                    scope="system", installed=True, commit=ref.get_commit(),
                ))
            return tuple(result)
        installation = self._installation()
        if installation is None:
            return ()
        result = []
        for ref in installation.list_installed_refs_by_kind(self._gi.RefKind.APP):
            result.append(FlatpakApplication(
                ref.get_name(), ref.get_appdata_name() or ref.get_name(),
                summary=ref.get_appdata_summary() or "", version=ref.get_appdata_version() or "",
                branch=ref.get_branch(), arch=ref.get_arch(), remote=ref.get_origin(),
                scope="user", installed=True, commit=ref.get_commit(),
            ))
        return tuple(result)

    def _native_installation_for(self, user: bool):
        return self._gi.Installation.new_user() if user else self._gi.Installation.new_system()

    def _require(self) -> str:
        if not self.command:
            raise FlatpakError("flatpak-unavailable", "Flatpak is not installed", retryable=True)
        return self.command

    async def _lines(self, *args: str, user: bool = True) -> list[str]:
        command = [self._require()]
        if user:
            command.append("--user")
        command.extend(args)
        process = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "LANG": "C"},
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip()
            raise FlatpakError("flatpak-command-failed", detail or "Flatpak command failed", retryable=True)
        return stdout.decode(errors="replace").splitlines()

    async def remotes(self, *, user: bool = True) -> tuple[dict[str, str], ...]:
        rows = await self._lines("remotes", "--columns=name,url,options", user=user)
        result = []
        for row in rows:
            parts = row.split("\t")
            if parts and parts[0].strip():
                result.append({"name": parts[0].strip(), "url": parts[1].strip() if len(parts) > 1 else "",
                               "options": parts[2].strip() if len(parts) > 2 else "", "scope": "user" if user else "system"})
        return tuple(result)

    async def ensure_flathub(self) -> None:
        self._require()
        existing = await self.remotes(user=True)
        if any(item["name"].casefold() == "flathub" for item in existing):
            return
        await self._lines("remote-add", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo", user=True)

    async def installed(self, *, user: bool = True) -> tuple[FlatpakApplication, ...]:
        if self._gi is not None:
            return await asyncio.to_thread(self._native_installed, user=user)
        rows = await self._lines("list", "--app", "--columns=application,name,version,branch,origin", user=user)
        result = []
        for row in rows:
            parts = row.split("\t")
            if not parts or not parts[0].strip():
                continue
            values = (parts + [""] * 5)[:5]
            item = FlatpakApplication(values[0].strip(), values[1].strip(), version=values[2].strip(),
                                      branch=values[3].strip(), remote=values[4].strip(),
                                      scope="user" if user else "system", installed=True)
            try:
                metadata = await self._metadata(item.application_id, user=user)
                item = replace(item, summary=metadata.get("summary", ""), categories=tuple(
                    value for value in metadata.get("categories", "").replace(",", ";").split(";") if value
                ), icon=metadata.get("icon", ""), commit=metadata.get("commit", ""))
            except FlatpakError:
                pass
            result.append(item)
        return tuple(result)

    async def _metadata(self, application_id: str, *, user: bool) -> dict[str, str]:
        rows = await self._lines("info", "--show-metadata", application_id, user=user)
        result: dict[str, str] = {}
        for row in rows:
            key, separator, value = row.partition("=")
            if separator and key.strip().casefold() in {"summary", "categories", "icon", "commit"}:
                result[key.strip().casefold()] = value.strip()
        return result

    async def catalog(self, query: str = "") -> tuple[FlatpakApplication, ...]:
        if self._gi is not None:
            return await asyncio.to_thread(self._native_catalog, query)
        rows = await self._lines("search", "--columns=application,name,summary,version,branch,arch,origin", query)
        result = []
        for row in rows:
            parts = row.split("\t")
            values = (parts + [""] * 7)[:7]
            if not values[0].strip() or values[0].casefold() in {"application", "name"}:
                continue
            result.append(FlatpakApplication(*(value.strip() for value in values)))
        return tuple(result)

    async def updates(self) -> tuple[FlatpakApplication, ...]:
        """Compare immutable Flatpak commits, never human-readable versions."""
        if self._gi is not None:
            def native_updates():
                installation = self._installation()
                current = {item.application_id: item for item in self._native_installed()}
                remote_refs = {
                    ref.get_name(): ref
                    for ref in installation.list_remote_refs_sync("flathub")
                    if str(ref.get_kind()).casefold() in {"0", "app"}
                }
                return tuple(replace(item, update_available=True,
                                     commit=remote_refs[item.application_id].get_commit())
                             for item in current.values()
                             if item.application_id in remote_refs
                             and remote_refs[item.application_id].get_commit() != item.commit)
            return await asyncio.to_thread(native_updates)
        result = []
        for app in await self.installed(user=True):
            if not app.remote:
                continue
            try:
                rows = await self._lines("remote-info", "--show-commit", app.remote,
                                         app.application_id, user=True)
            except FlatpakError:
                continue
            remote_commit = next((row.split(":", 1)[1].strip() for row in rows
                                  if row.casefold().startswith("commit:")), "")
            if remote_commit and remote_commit != app.commit:
                result.append(replace(app, update_available=True, commit=remote_commit))
        return tuple(result)

    async def reconcile(self, query: str = "") -> tuple[FlatpakApplication, ...]:
        remote = {item.application_id: item for item in await self.catalog(query)}
        system = {item.application_id: item for item in await self.installed(user=False)}
        user = {item.application_id: item for item in await self.installed(user=True)}
        result = []
        for app_id in sorted(set(remote) | set(system) | set(user)):
            # AppStream is the authoritative source for presentation metadata;
            # installed refs are authoritative for scope, commit and state.
            # Merge them so installing an app does not discard its categories
            # or artwork merely because InstalledRef has no AppStream fields.
            item = remote.get(app_id) or user.get(app_id) or system[app_id]
            installed = user.get(app_id) or system.get(app_id)
            if installed is not None:
                item = replace(
                    item,
                    version=installed.version or item.version,
                    branch=installed.branch or item.branch,
                    arch=installed.arch or item.arch,
                    remote=installed.remote or item.remote,
                    scope=installed.scope,
                    installed=True,
                    commit=installed.commit or item.commit,
                )
            scopes = [scope for scope, values in (("user", user), ("system", system)) if app_id in values]
            result.append(replace(item, scope="+".join(scopes) or item.scope,
                                  installed=app_id in user or app_id in system))
        return tuple(result)

    def launch_command(self, application_id: str) -> list[str]:
        self._require()
        if not application_id or "/" in application_id or "." not in application_id:
            raise FlatpakError("invalid-application-id", "Flatpak application ID is invalid")
        # Gamescope selects the supervised application's X11 window. Prefer
        # SDL's X11 backend for Flatpak apps so Wayland-native clients do not
        # bypass that focusable-window registry.
        return [self.command, "run", "--socket=x11", "--env=SDL_VIDEODRIVER=x11",
                application_id]

    async def prepare_browser_handoff(self, uri: str) -> dict[str, str]:
        """Fetch and validate one claimed flatpak+https flatpakref."""
        if not uri.startswith("flatpak+https://"):
            raise FlatpakError("invalid-handoff-scheme", "Only flatpak+https handoffs are supported")
        destination = "https://" + uri.removeprefix("flatpak+https://")
        parsed = urlsplit(destination)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise FlatpakError("invalid-handoff-url", "Flatpak handoff destination must be a safe HTTPS URL")
        request = Request(destination, headers={"Accept": "application/vnd.flatpak.ref, text/plain"})

        def fetch() -> bytes:
            with urlopen(request, timeout=20) as response:
                if response.geturl().split(":", 1)[0].casefold() != "https":
                    raise FlatpakError("invalid-handoff-redirect", "Flatpakref redirect was not HTTPS")
                length = response.headers.get("Content-Length")
                if length and int(length) > 2 * 1024 * 1024:
                    raise FlatpakError("flatpakref-too-large", "Flatpakref exceeds the safe size limit")
                data = response.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024:
                    raise FlatpakError("flatpakref-too-large", "Flatpakref exceeds the safe size limit")
                return data

        try:
            data = await asyncio.to_thread(fetch)
        except FlatpakError:
            raise
        except Exception as error:
            raise FlatpakError("flatpakref-fetch-failed", str(error), retryable=True) from error
        parser = configparser.ConfigParser(interpolation=None)
        try:
            parser.read_string(data.decode("utf-8"))
            section = parser["Flatpak Ref"]
            application_id = section.get("Name", "").strip()
            repo_url = section.get("Url", "").strip()
        except (UnicodeDecodeError, configparser.Error, KeyError) as error:
            raise FlatpakError("invalid-flatpakref", "The downloaded file is not a valid flatpakref") from error
        if not application_id or "." not in application_id or "/" in application_id:
            raise FlatpakError("invalid-flatpakref", "Flatpakref has no valid application ID")
        if urlsplit(repo_url).scheme != "https":
            raise FlatpakError("invalid-flatpakref", "Flatpakref repository URL must be HTTPS")
        handoff_root = Path.home() / ".cache" / "lulu" / "flatpak-handoffs"
        handoff_root.mkdir(parents=True, exist_ok=True)
        path = handoff_root / (hashlib.sha256(uri.encode()).hexdigest() + ".flatpakref")
        path.write_bytes(data)
        return {"application_id": application_id, "title": section.get("Title", application_id),
                "path": str(path)}

    async def operation(self, job: DownloadJob, reporter: JobReporter) -> None:
        if self._gi is not None:
            await self._native_operation(job, reporter)
            return
        app_id = job.content_identity.removeprefix("flatpak:")
        if job.operation is JobOperation.REMOVE:
            args = ("uninstall", "--noninteractive", app_id)
        elif job.provider_job_id and Path(job.provider_job_id).suffix == ".flatpakref":
            args = ("install", "--noninteractive", job.provider_job_id)
        else:
            args = ("install", "--noninteractive", "--or-update", "flathub", app_id)
        self._require()
        await reporter.state(JobState.STARTING, stage="resolving")
        process = await asyncio.create_subprocess_exec(
            self.command, "--user", *args, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, env={**os.environ, "LANG": "C"},
        )
        diagnostic_lines: list[str] = []
        try:
            assert process.stdout is not None
            async for raw in process.stdout:
                line = raw.decode(errors="replace").strip()
                lowered = line.casefold()
                if "runtime" in lowered or "not found" in lowered or "not installed" in lowered:
                    diagnostic_lines.append(line[:500])
                    diagnostic_lines = diagnostic_lines[-8:]
                if "installing" in lowered or "deploying" in lowered:
                    await reporter.state(JobState.FINALIZING, stage="installing")
                elif "download" in lowered or "runtime" in lowered:
                    await reporter.state(JobState.TRANSFERRING, stage="transferring")
            code = await process.wait()
        except asyncio.CancelledError:
            if process.returncode is None:
                process.terminate()
                await process.wait()
            raise JobCancelled
        if code != 0:
            raise _flatpak_operation_failure(app_id, diagnostic_lines)
        await reporter.state(JobState.FINALIZING, stage="reconciling")
        actual = {item.application_id: item for item in await self.installed(user=True)}
        if job.operation is not JobOperation.REMOVE and app_id not in actual:
            raise FlatpakError("reconcile-mismatch", "Flatpak did not report the requested application installed")
        if job.operation is JobOperation.REMOVE and app_id in actual:
            raise FlatpakError("reconcile-mismatch", "Flatpak still reports the application installed")

    async def _native_operation(self, job: DownloadJob, reporter: JobReporter) -> None:
        """Run one FlatpakTransaction; CLI is used only when GI is unavailable."""
        app_id = job.content_identity.removeprefix("flatpak:")
        loop = asyncio.get_running_loop()
        cancellable = self._gi.Gio.Cancellable() if hasattr(self._gi, "Gio") else None
        # Gio is a dependency of the Flatpak typelib but is not exported from
        # it on every distro; import it only inside this adapter boundary.
        if cancellable is None:
            from gi.repository import Gio
            cancellable = Gio.Cancellable()
        await reporter.state(JobState.STARTING, stage="resolving")

        def worker() -> None:
            installation = self._installation()
            transaction = self._gi.Transaction.new_for_installation(installation, cancellable)
            try:
                transaction.props.no_interaction = True
            except (AttributeError, TypeError):
                pass

            def progress_changed(progress):
                percent = float(progress.get_progress()) / 100.0
                bytes_transferred = int(progress.get_bytes_transferred())
                stage = "transferring" if percent < 1.0 else "finalizing"
                loop.call_soon_threadsafe(asyncio.create_task, reporter.progress(
                    percent if not progress.get_is_estimating() else None,
                    downloaded_bytes=bytes_transferred, stage=stage))

            def new_operation(_transaction, operation, progress):
                progress.connect("changed", lambda changed: progress_changed(changed))
                loop.call_soon_threadsafe(asyncio.create_task, reporter.state(
                    JobState.TRANSFERRING, stage="transferring"))

            transaction.connect("new-operation", new_operation)
            if job.operation is JobOperation.REMOVE:
                ref = f"app/{app_id}/x86_64/stable"
                transaction.add_uninstall(ref)
            elif job.operation is JobOperation.UPDATE:
                installed = self._native_installed()
                target = next((item for item in installed if item.application_id == app_id), None)
                if target is None:
                    raise FlatpakError("not-installed", "Flatpak application is not installed")
                transaction.add_update(f"app/{target.application_id}/{target.arch}/{target.branch}")
            elif job.provider_job_id and Path(job.provider_job_id).suffix == ".flatpakref":
                from gi.repository import GLib
                transaction.add_install_flatpakref(GLib.Bytes.new(Path(job.provider_job_id).read_bytes()))
            else:
                transaction.add_install("flathub", f"app/{app_id}/x86_64/stable")
            try:
                transaction.run(cancellable)
            except Exception as error:
                if cancellable.is_cancelled():
                    raise JobCancelled from error
                translated = _flatpak_operation_failure(app_id, [str(error)])
                raise FlatpakError(translated.code, str(translated), retryable=True) from error

        task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            await task
        except asyncio.CancelledError:
            cancellable.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise JobCancelled
        actual = {item.application_id: item for item in await self.installed(user=True)}
        if job.operation is not JobOperation.REMOVE and app_id not in actual:
            raise FlatpakError("reconcile-mismatch", "Flatpak did not report the requested application installed")
        if job.operation is JobOperation.REMOVE and app_id in actual:
            raise FlatpakError("reconcile-mismatch", "Flatpak still reports the application installed")
        await reporter.state(JobState.FINALIZING, stage="reconciling")


class FlatpakJobExecutor:
    supports_pause = False
    supports_uninstall = True

    def __init__(self, adapter: FlatpakAdapter):
        self.adapter = adapter

    async def run(self, job: DownloadJob, reporter: JobReporter) -> None:
        try:
            await self.adapter.operation(job, reporter)
        except JobCancelled:
            raise
        except FlatpakError as error:
            raise JobExecutionError(error.code, str(error), retryable=error.retryable) from error

    async def cancel(self, job: DownloadJob) -> None:
        # JobManager cancellation terminates the adapter task and its owned
        # child process; reconciliation happens on the next provider refresh.
        return None
