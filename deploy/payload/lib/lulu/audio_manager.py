"""Normalized session-audio adapter using PipeWire's Pulse compatibility API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from typing import Any

LOGGER = logging.getLogger(__name__)


class AudioManagerAdapter:
    """PipeWire owns devices, defaults, volume, mute, and persistence."""

    def __init__(self, runner: Any | None = None) -> None:
        self._runner = runner or self._run

    @staticmethod
    def _run(*args: str) -> str:
        result = subprocess.run(
            ("pactl", *args), check=True, capture_output=True, text=True, timeout=3,
            env=os.environ.copy(),
        )
        return result.stdout

    async def _json(self, kind: str) -> list[dict[str, Any]]:
        output = await asyncio.to_thread(self._runner, "--format=json", "list", kind)
        value = json.loads(output)
        return value if isinstance(value, list) else []

    @staticmethod
    def _percent(item: dict[str, Any]) -> int:
        volumes = item.get("volume", {})
        values = []
        for channel in volumes.values():
            text = str(channel.get("value_percent", "0")).rstrip("%")
            try:
                values.append(float(text))
            except ValueError:
                pass
        return max(0, min(100, round(sum(values) / len(values)))) if values else 0

    @staticmethod
    def _friendly(item: dict[str, Any], input_device: bool = False) -> tuple[str, str]:
        properties = item.get("properties", {})
        description = str(item.get("description") or properties.get("device.description") or item.get("name"))
        nick = str(properties.get("device.nick") or "")
        lowered = f"{description} {nick}".lower()
        if "hdmi" in lowered or "displayport" in lowered:
            kind = "HDMI / DisplayPort"
        elif "usb" in lowered:
            kind = "USB"
        elif "bluetooth" in lowered:
            kind = "Bluetooth"
        elif "fallback" in lowered or properties.get("media.class") == "Audio/Source":
            kind = "Virtual input" if input_device else "Virtual output"
        else:
            kind = "Audio input" if input_device else "Analog output"
        if description.startswith("Monitor of "):
            description = description.removeprefix("Monitor of ")
        return description, kind

    @classmethod
    def _device(cls, item: dict[str, Any], default: str, input_device: bool = False) -> dict[str, Any]:
        name = str(item.get("name", ""))
        label, kind = cls._friendly(item, input_device)
        return {
            "id": name,
            "name": label,
            "type": kind,
            "available": item.get("state") not in {"UNAVAILABLE", "UNKNOWN"},
            "active": name == default,
            "volume": cls._percent(item),
            "mute": bool(item.get("mute", False)),
        }

    async def snapshot(self) -> dict[str, Any]:
        try:
            info, sinks, sources = await asyncio.gather(
                asyncio.to_thread(self._runner, "--format=json", "info"),
                self._json("sinks"), self._json("sources"),
            )
            server = json.loads(info)
            default_sink = str(server.get("default_sink_name") or "")
            default_source = str(server.get("default_source_name") or "")
            outputs = [self._device(item, default_sink) for item in sinks]
            inputs = [self._device(item, default_source, True) for item in sources
                      if not str(item.get("name", "")).endswith(".monitor")]
            current_output = next((item for item in outputs if item["active"]), None)
            current_input = next((item for item in inputs if item["active"]), None)
            return {"available": True, "outputs": outputs, "inputs": inputs,
                    "current_output": current_output, "current_input": current_input,
                    "default_output": default_sink, "default_input": default_source,
                    "error": ""}
        except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as error:
            LOGGER.warning("audio snapshot unavailable: %s", error)
            return {"available": False, "outputs": [], "inputs": [],
                    "current_output": None, "current_input": None,
                    "default_output": "", "default_input": "", "error": str(error)}

    async def _mutate(self, *args: str) -> dict[str, Any]:
        try:
            await asyncio.to_thread(self._runner, *args)
        except (OSError, subprocess.SubprocessError) as error:
            state = await self.snapshot()
            state["error"] = str(error)
            return state
        return await self.snapshot()

    async def set_default_output(self, device_id: str) -> dict[str, Any]:
        return await self._mutate("set-default-sink", device_id)

    async def set_default_input(self, device_id: str) -> dict[str, Any]:
        return await self._mutate("set-default-source", device_id)

    async def set_volume(self, device_id: str, volume: int, input_device: bool = False) -> dict[str, Any]:
        volume = max(0, min(100, int(volume)))
        return await self._mutate("set-source-volume" if input_device else "set-sink-volume",
                                  device_id, f"{volume}%")

    async def set_mute(self, device_id: str, muted: bool, input_device: bool = False) -> dict[str, Any]:
        return await self._mutate("set-source-mute" if input_device else "set-sink-mute",
                                  device_id, "1" if muted else "0")
