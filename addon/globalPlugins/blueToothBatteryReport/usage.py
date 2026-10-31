# BlueToothBatteryReport add-on for NVDA
# Copyright (C) 2026 haitun001 <476947039@qq.com>, cary-rowen <manchen_0528@outlook.com>
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

"""Remembers how long each Bluetooth device is connected between two recharges.

Counting starts the first time a device is seen, at any battery level. Only time during which the device
was seen as connected is counted. The total is kept (as JSON in the NVDA configuration folder) while the
device is disconnected and when NVDA restarts. Gaps longer than _MAX_GAP_SECONDS between two observations
are skipped, so a sleeping computer does not inflate the result.

A recharge is detected when the battery level is at least _RECHARGE_RISE points above the lowest level of
the current cycle. The finished cycle is stored in the history and counting restarts from zero. Time is
not counted while the battery level is rising (the device is charging).

For Bluetooth Classic devices Windows reports how long the current connection has lasted. The counted
total of the current cycle is never smaller than that, so a device that was already connected for hours
when first seen is not under-reported. Bluetooth LE devices have no such value, so their total only covers
the time that was observed.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from logHandler import log

USAGE_FILE_NAME = "blueToothBatteryReport_usage.json"
# Gaps between two observations longer than this are not counted (computer asleep, NVDA closed, ...).
_MAX_GAP_SECONDS = 15 * 60
# A device counts as recharged when its battery is at least this many points above the lowest level seen in
# the current cycle. This also works for devices that never reach 100%.
_RECHARGE_RISE = 15
# A finished cycle shorter than this is not kept (for example the steps seen while charging).
_MIN_CYCLE_SECONDS = 30 * 60
# Finished cycles kept per device. The oldest are dropped.
_HISTORY_LIMIT = 500
# Sort rank of devices that were not in the latest scan, after every real connection status.
_NOT_SCANNED_RANK = 99


@dataclass(frozen=True)
class DeviceObservation:
	"""What the tracker needs to know about one device from one scan."""

	name: str
	battery: int
	# Position of the connection status in the report order (lower means more connected).
	statusRank: int
	# Whether the device is known to be disconnected. Time is only counted for other devices.
	disconnected: bool
	# For how long Windows says the current connection lasted, if it reports it.
	windowsConnectionSeconds: float | None = None


@dataclass(frozen=True)
class CycleRecord:
	"""A finished cycle, from one recharge to the next."""

	# When the recharge that ended the cycle was detected (epoch seconds), if known.
	end: float | None
	# Connected seconds of the cycle.
	seconds: float
	startLevel: int | None
	lowestLevel: int | None


@dataclass(frozen=True)
class DeviceStats:
	"""A snapshot of what is known about a device, for the statistics."""

	name: str
	history: list[CycleRecord]
	currentSeconds: float
	startLevel: int | None
	lowestLevel: int | None
	level: int | None
	# None if the device was not in the latest scan.
	statusRank: int | None


def _optional(value: Any, cast: type[int] | type[float]) -> Any:
	return cast(value) if value is not None else None


@dataclass
class _DeviceUsage:
	# Connected seconds counted in the current cycle.
	active: float = 0.0
	# Battery level at the previous observation.
	level: int | None = None
	# Lowest battery level seen in the current cycle.
	minLevel: int | None = None
	# Battery level when the current cycle started.
	startLevel: int | None = None
	# Epoch time at which the current cycle started. It may precede the first observation.
	cycleStart: float | None = None
	# Epoch time of the previous observation while connected, None while disconnected.
	lastSeen: float | None = None
	history: list[CycleRecord] = field(default_factory=list)

	@classmethod
	def fromJson(cls, data: dict[str, Any]) -> _DeviceUsage:
		history = [
			CycleRecord(
				end=_optional(record.get("end"), float),
				seconds=float(record["secs"]),
				startLevel=_optional(record.get("from"), int),
				lowestLevel=_optional(record.get("to"), int),
			)
			for record in data.get("history") or []
			if isinstance(record, dict) and record.get("secs") is not None
		]
		return cls(
			active=float(data.get("active") or 0.0),
			level=_optional(data.get("level"), int),
			minLevel=_optional(data.get("min_level"), int),
			startLevel=_optional(data.get("start_level"), int),
			cycleStart=_optional(data.get("cycle_start"), float),
			lastSeen=_optional(data.get("last_seen"), float),
			history=history,
		)

	def toJson(self) -> dict[str, Any]:
		return {
			"active": self.active,
			"level": self.level,
			"min_level": self.minLevel,
			"start_level": self.startLevel,
			"cycle_start": self.cycleStart,
			"last_seen": self.lastSeen,
			"history": [
				{"end": r.end, "secs": r.seconds, "from": r.startLevel, "to": r.lowestLevel}
				for r in self.history
			],
		}


class UsageTracker:
	# The running instance, so the settings panel can show its statistics.
	current: UsageTracker | None = None

	def __init__(self, path: str) -> None:
		UsageTracker.current = self
		self._path = path
		self._lock = threading.Lock()
		self._usages: dict[str, _DeviceUsage] = self._load()
		# Connection status rank of the devices in the latest scan, for the order of the statistics.
		self._ranks: dict[str, int] = {}

	def _load(self) -> dict[str, _DeviceUsage]:
		try:
			with open(self._path, encoding="utf-8") as f:
				data = json.load(f)
		except FileNotFoundError:
			return {}
		except Exception:
			log.exception("Could not load the connection time data")
			return {}
		usages: dict[str, _DeviceUsage] = {}
		if isinstance(data, dict):
			for name, entry in data.items():
				if not isinstance(entry, dict):
					continue
				try:
					usages[name] = _DeviceUsage.fromJson(entry)
				except (TypeError, ValueError, KeyError):
					log.debugWarning(f"Ignoring invalid connection time data of {name!r}", exc_info=True)
		return usages

	def _save(self) -> None:
		tempPath = self._path + ".tmp"
		try:
			with open(tempPath, "w", encoding="utf-8") as f:
				json.dump({name: usage.toJson() for name, usage in self._usages.items()}, f, indent=1)
			os.replace(tempPath, self._path)
		except Exception:
			log.exception("Could not save the connection time data")

	def noteStatus(self, observations: Iterable[DeviceObservation]) -> None:
		"""Remember the connection status of the devices of the latest scan, for the order of the statistics.

		This is meant for every scan, whether the connection time is measured or not.
		"""
		with self._lock:
			self._ranks = {observation.name: observation.statusRank for observation in observations}

	def update(self, observations: Iterable[DeviceObservation], now: float | None = None) -> None:
		"""Add one scan to the measured connection times."""
		now = time.time() if now is None else now
		changed = False
		with self._lock:
			for observation in observations:
				changed = self._observe(observation, now) or changed
			if changed:
				self._save()

	def _observe(self, observation: DeviceObservation, now: float) -> bool:
		"""Add one observation. Return whether the stored data changed."""
		usage = self._usages.get(observation.name)
		if observation.disconnected:
			# The connection is over. The time counted so far is kept.
			if usage is not None and usage.lastSeen is not None:
				usage.lastSeen = None
				return True
			return False

		battery = observation.battery
		windowsSeconds = observation.windowsConnectionSeconds
		if usage is None:
			# First time this device is seen: start counting from here, whatever its battery level.
			self._usages[observation.name] = _DeviceUsage(
				active=windowsSeconds or 0.0,
				level=battery,
				minLevel=battery,
				startLevel=battery,
				cycleStart=now - (windowsSeconds or 0.0),
				lastSeen=now,
			)
			return True

		lastSeen = usage.lastSeen
		seconds = now - lastSeen if lastSeen is not None and 0 <= now - lastSeen <= _MAX_GAP_SECONDS else 0.0
		usage.lastSeen = now
		minLevel = battery if usage.minLevel is None else usage.minLevel
		previousLevel = battery if usage.level is None else usage.level
		if battery >= minLevel + _RECHARGE_RISE:
			# Clearly higher than the lowest level of this cycle: the device was recharged.
			if usage.active >= _MIN_CYCLE_SECONDS:
				usage.history.append(
					CycleRecord(
						end=now,
						seconds=usage.active,
						startLevel=usage.startLevel,
						lowestLevel=minLevel,
					),
				)
				del usage.history[:-_HISTORY_LIMIT]
			usage.active = 0.0
			usage.cycleStart = now
			usage.minLevel = usage.startLevel = battery
		else:
			if battery <= previousLevel:
				usage.active += seconds
			usage.minLevel = min(minLevel, battery)
			if usage.startLevel is None:
				usage.startLevel = battery
		if windowsSeconds is not None:
			# Windows knows that the current connection lasted at least this long, so the total of this
			# cycle cannot be smaller (unless a recharge just started a new cycle).
			if usage.cycleStart is None:
				usage.cycleStart = now - max(usage.active, windowsSeconds)
			usage.active = max(usage.active, min(windowsSeconds, now - usage.cycleStart))
		usage.level = battery
		return True

	def getTotalSeconds(self, name: str) -> float | None:
		"""Return the connected seconds counted in the current cycle of a device, if it is known."""
		with self._lock:
			usage = self._usages.get(name)
			return usage.active if usage is not None else None

	def getStats(self) -> list[DeviceStats]:
		"""Return the stats of all devices, in the order of the spoken report.

		That is connected, unknown and disconnected devices, each group by name. Devices that were not in
		the latest scan come last.
		"""
		with self._lock:
			ordered = sorted(
				self._usages.items(),
				key=lambda item: (self._ranks.get(item[0], _NOT_SCANNED_RANK), item[0].lower()),
			)
			return [
				DeviceStats(
					name=name,
					history=list(usage.history),
					currentSeconds=usage.active,
					startLevel=usage.startLevel,
					lowestLevel=usage.minLevel,
					level=usage.level,
					statusRank=self._ranks.get(name),
				)
				for name, usage in ordered
			]
