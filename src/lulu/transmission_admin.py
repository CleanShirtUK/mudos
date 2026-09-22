"""Narrow administrative boundary for Transmission RPC credentials."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile


CONFIG_PATH = Path(os.environ.get("LULU_TRANSMISSION_CONFIG", "/var/lib/lulu-transmission/settings.json"))


class TransmissionMutationError(RuntimeError):
    """A credential change failed and the previous state was restored."""


def apply_rpc_credentials(username: str, password: str,
                          path: Path = CONFIG_PATH) -> None:
    """Write credentials to Transmission's private config.

    Transmission salts ``rpc-password`` when it starts.  This function is
    called only after the daemon has stopped; callers must start it again and
    must not repeatedly rewrite the resulting salted value.
    """
    validate_rpc_credentials(username, password)
    values = json.loads(path.read_text())
    values["rpc-username"] = username
    values["rpc-password"] = password
    # The Admin service may write the existing settings file through its
    # narrow ACL, but it must not gain directory-wide create/rename access.
    # Stage outside Transmission's private directory, then copy over the
    # stopped daemon's existing file.
    with tempfile.TemporaryDirectory(prefix="mudos-transmission-") as directory:
        temporary = Path(directory) / "settings.json"
        temporary.write_text(json.dumps(values, indent=4, sort_keys=True) + "\n")
        shutil.copyfile(temporary, path)


def validate_rpc_credentials(username: str, password: str) -> None:
    if not username or not password or any(char in username + password for char in "\r\n"):
        raise ValueError("Transmission RPC credentials must be non-empty and single-line")


def replace_rpc_credentials(username: str, password: str, previous_username: str,
                            previous_password: str, *, stop, start, materialize,
                            health, commit, rollback_commit, refresh, reconcile) -> None:
    """Apply and verify a credential change, restoring the old state on error.

    Callbacks keep service authorization and SecretStore ownership at the
    caller boundary while making the lifecycle independently testable.
    """
    validate_rpc_credentials(username, password)
    validate_rpc_credentials(previous_username, previous_password)
    runtime_stopped = False
    committed = False
    try:
        stop()
        runtime_stopped = True
        materialize(username, password)
        start()
        health(username, password)
        commit()
        committed = True
        refresh()
        reconcile()
    except Exception as error:
        rollback_error = None
        if runtime_stopped:
            try:
                stop()
                materialize(previous_username, previous_password)
                start()
            except Exception as restore_error:  # pragma: no cover - catastrophic host failure
                rollback_error = restore_error
        if committed or runtime_stopped:
            try:
                rollback_commit()
            except Exception as restore_error:  # pragma: no cover - catastrophic host failure
                rollback_error = rollback_error or restore_error
        if committed:
            try:
                refresh()
                reconcile()
            except Exception as restore_error:  # pragma: no cover - degraded dependency
                rollback_error = rollback_error or restore_error
        detail = "previous credentials were restored" if rollback_error is None else "rollback requires operator attention"
        raise TransmissionMutationError(
            f"Could not update Transmission credentials; {detail}."
        ) from error
