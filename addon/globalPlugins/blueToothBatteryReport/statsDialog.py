# BlueToothBatteryReport add-on for NVDA
# Copyright (C) 2026 haitun001 <476947039@qq.com>, cary-rowen <manchen_0528@outlook.com>
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

"""The window with the statistics of the connection times of the Bluetooth devices."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import addonHandler
import api
from gui.message import MessageDialog, displayDialogAsModal
import ui
import wx

from .formatting import formatDuration
from .usage import DeviceStats, UsageTracker

addonHandler.initTranslation()

# Cycles that used fewer battery points than this are too coarse for runtime estimates.
_MIN_DROP = 10
# The latest cycles are compared with the earlier ones for the trend.
_TREND_RECENT = 3
# A change smaller than this (as a fraction) is reported as "stable".
_STABLE_RANGE = 0.05


def _formatBatteryRange(startLevel: int | None, lowestLevel: int | None) -> str:
	if startLevel is None or lowestLevel is None:
		return ""
	# Translators: Battery level range of one cycle, from the level at its start to the lowest level,
	# for example "100% to 23%".
	return _("{start}% to {end}%").format(start=startLevel, end=lowestLevel)


def _formatLongDuration(seconds: float) -> str:
	"""Like formatDuration, but in days from two days on."""
	if seconds >= 2 * 86400:
		days = round(seconds / 86400, 1)
		# Translators: A duration in days, for example "2.5 days".
		return _("{days} days").format(days=int(days) if days == int(days) else days)
	return formatDuration(seconds)


def _formatTimestamp(epoch: float | None) -> str:
	if epoch is None:
		return ""
	return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")


def _fullChargeSeconds(seconds: float, startLevel: int | None, lowestLevel: int | None) -> float | None:
	"""Estimate the runtime on a full charge from the battery points used during `seconds` seconds."""
	if startLevel is None or lowestLevel is None or seconds <= 0:
		return None
	drop = startLevel - lowestLevel
	if drop < _MIN_DROP:
		return None
	return seconds * 100 / drop


def _formatFullCharge(seconds: float, startLevel: int | None, lowestLevel: int | None) -> str:
	runtime = _fullChargeSeconds(seconds, startLevel, lowestLevel)
	return formatDuration(runtime) if runtime is not None else ""


def _describeStatus(statusRank: int | None) -> str:
	"""Return the text of a connection status, empty if the device was not in the latest scan."""
	# The status classes are in the package, which is fully loaded when this runs.
	from . import ConnectionStatus

	if statusRank == ConnectionStatus.CONNECTED:
		# Translators: A connection status shown in the statistics.
		return _("connected")
	if statusRank == ConnectionStatus.UNKNOWN:
		# Translators: A connection status shown in the statistics.
		return _("unknown")
	if statusRank == ConnectionStatus.DISCONNECTED:
		# Translators: A connection status shown in the statistics.
		return _("disconnected")
	return ""


def _describeTrend(runtimes: list[float]) -> str:
	"""Compare the latest cycles with the earlier ones (full charge runtimes, oldest first)."""
	if len(runtimes) <= _TREND_RECENT:
		return ""
	recent = runtimes[-_TREND_RECENT:]
	earlier = runtimes[:-_TREND_RECENT]
	change = (sum(recent) / len(recent)) / (sum(earlier) / len(earlier)) - 1
	if abs(change) < _STABLE_RANGE:
		# Translators: Battery life trend. The latest cycles are about as long as the earlier ones.
		return _("stable")
	percent = round(abs(change) * 100)
	if change < 0:
		# Translators: Battery life trend. The latest cycles are shorter than the earlier ones,
		# for example "12% shorter".
		return _("{percent}% shorter").format(percent=percent)
	# Translators: Battery life trend. The latest cycles are longer than the earlier ones,
	# for example "8% longer".
	return _("{percent}% longer").format(percent=percent)


def _estimateTimeLeft(stats: DeviceStats) -> str:
	"""Estimate the connected time left at the usual drain rate, from the battery level seen last."""
	if stats.level is None or stats.level <= 0:
		return ""
	usable: list[tuple[float, int]] = []
	for record in stats.history:
		if _fullChargeSeconds(record.seconds, record.startLevel, record.lowestLevel) is not None:
			assert record.startLevel is not None and record.lowestLevel is not None
			usable.append((record.seconds, record.startLevel - record.lowestLevel))
	if not usable and _fullChargeSeconds(stats.currentSeconds, stats.startLevel, stats.lowestLevel):
		assert stats.startLevel is not None and stats.lowestLevel is not None
		usable.append((stats.currentSeconds, stats.startLevel - stats.lowestLevel))
	if not usable:
		return ""
	seconds = sum(s for s, _drop in usable)
	drop = sum(d for _s, d in usable)
	return formatDuration(stats.level * seconds / drop)


def buildCycleRows(devices: Sequence[DeviceStats]) -> list[tuple[str, ...]]:
	"""Return the text rows (device, cycle, duration, battery, full charge, ended) of the cycle list.

	For each device the cycle in progress comes first, then the finished cycles, newest first.
	"""
	rows: list[tuple[str, ...]] = []
	for stats in devices:
		rows.append(
			(
				stats.name,
				# Translators: Value in the "Cycle" column for the cycle that has not finished yet.
				_("current"),
				formatDuration(stats.currentSeconds),
				_formatBatteryRange(stats.startLevel, stats.lowestLevel),
				_formatFullCharge(stats.currentSeconds, stats.startLevel, stats.lowestLevel),
				"",
			),
		)
		for number in range(len(stats.history), 0, -1):
			record = stats.history[number - 1]
			rows.append(
				(
					stats.name,
					str(number),
					formatDuration(record.seconds),
					_formatBatteryRange(record.startLevel, record.lowestLevel),
					_formatFullCharge(record.seconds, record.startLevel, record.lowestLevel),
					_formatTimestamp(record.end),
				),
			)
	return rows


def buildSummaryRows(devices: Sequence[DeviceStats]) -> list[tuple[str, ...]]:
	"""Return the text rows of the summary list, one per device."""
	rows: list[tuple[str, ...]] = []
	for stats in devices:
		durations = [record.seconds for record in stats.history]
		runtimes = [
			runtime
			for runtime in (
				_fullChargeSeconds(record.seconds, record.startLevel, record.lowestLevel)
				for record in stats.history
			)
			if runtime is not None
		]
		ends = [record.end for record in stats.history if record.end is not None]
		average = shortest = longest = fullCharge = interval = lastRecharge = ""
		if durations:
			average = formatDuration(sum(durations) / len(durations))
			shortest = formatDuration(min(durations))
			longest = formatDuration(max(durations))
		if runtimes:
			fullCharge = formatDuration(sum(runtimes) / len(runtimes))
		if len(ends) >= 2:
			interval = _formatLongDuration((ends[-1] - ends[0]) / (len(ends) - 1))
		if ends:
			lastRecharge = _formatTimestamp(ends[-1])
		rows.append(
			(
				stats.name,
				_describeStatus(stats.statusRank),
				str(len(stats.history)),
				average,
				shortest,
				longest,
				fullCharge,
				interval,
				lastRecharge,
				_describeTrend(runtimes),
				_estimateTimeLeft(stats),
			),
		)
	return rows


def formatRowText(headers: Sequence[str], row: Sequence[str]) -> str:
	"""Return the text of one row, as "Header: value" pairs. Empty values are left out."""
	return "; ".join(f"{header}: {value}" for header, value in zip(headers, row, strict=True) if value)


def formatDeviceText(
	name: str,
	summaryData: tuple[Sequence[str], Sequence[tuple[str, ...]]],
	cyclesData: tuple[Sequence[str], Sequence[tuple[str, ...]]],
) -> str:
	"""Return everything the statistics show about a device: its name, its summary line and every cycle."""
	summaryHeaders, summaryRows = summaryData
	cyclesHeaders, cyclesRows = cyclesData
	lines = [name]
	lines += [formatRowText(summaryHeaders[1:], row[1:]) for row in summaryRows if row[0] == name]
	lines += [formatRowText(cyclesHeaders[1:], row[1:]) for row in cyclesRows if row[0] == name]
	return "\n".join(lines)


class UsageStatsDialog(wx.Dialog):
	"""A per-device summary and the list of the recorded battery cycles."""

	def __init__(self, parent: wx.Window | None, devices: Sequence[DeviceStats]) -> None:
		# Translators: The title of the window that shows the recorded battery cycles.
		super().__init__(parent, title=_("Bluetooth battery statistics"))
		mainSizer = wx.BoxSizer(wx.VERTICAL)
		# For each list: its column headers and its text rows, to copy the current row or device.
		self._listData: dict[wx.ListCtrl, tuple[tuple[str, ...], Sequence[tuple[str, ...]]]] = {}
		self._summaryList = self._addList(
			mainSizer,
			# Translators: The label of the list with one summary line per device.
			_("&Summary per device:"),
			(
				# Translators: The column headers of the summary list.
				(_("Device"), 200),
				(_("Status"), 100),
				(_("Cycles"), 70),
				(_("Average"), 100),
				(_("Shortest"), 100),
				(_("Longest"), 100),
				(_("Full charge (est.)"), 130),
				(_("Recharged every"), 130),
				(_("Last recharge"), 150),
				(_("Trend"), 110),
				(_("Left now (est.)"), 130),
			),
			buildSummaryRows(devices),
			150,
		)
		self._cyclesList = self._addList(
			mainSizer,
			# Translators: The label of the list with every recorded battery cycle.
			_("&Cycles:"),
			(
				# Translators: The column headers of the cycle list.
				(_("Device"), 200),
				(_("Cycle"), 80),
				(_("Duration"), 110),
				(_("Battery"), 140),
				(_("Full charge (est.)"), 130),
				(_("Ended"), 150),
			),
			buildCycleRows(devices),
			260,
		)

		closeButton = wx.Button(self, wx.ID_CLOSE, label=_("&Close"))
		closeButton.SetDefault()
		closeButton.Bind(wx.EVT_BUTTON, lambda evt: self.EndModal(wx.ID_CLOSE))
		self.SetEscapeId(wx.ID_CLOSE)
		mainSizer.Add(closeButton, 0, wx.ALIGN_RIGHT | wx.ALL, 8)

		self.SetSizerAndFit(mainSizer)
		self.CentreOnScreen()
		self._summaryList.SetFocus()

	def _addList(
		self,
		mainSizer: wx.BoxSizer,
		labelText: str,
		columns: Sequence[tuple[str, int]],
		rows: Sequence[tuple[str, ...]],
		height: int,
	) -> wx.ListCtrl:
		# The label is created right before the list, so screen readers use it as the name of the list.
		mainSizer.Add(wx.StaticText(self, label=labelText), 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)
		statsList = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL, size=(1000, height))
		for index, (label, width) in enumerate(columns):
			statsList.InsertColumn(index, label, width=width)
		for row in rows:
			index = statsList.InsertItem(statsList.GetItemCount(), row[0])
			for column, text in enumerate(row[1:], start=1):
				statsList.SetItem(index, column, text)
		if statsList.GetItemCount():
			statsList.Select(0)
			statsList.Focus(0)
		mainSizer.Add(statsList, 1, wx.EXPAND | wx.ALL, 8)
		self._listData[statsList] = (tuple(label for label, _width in columns), rows)
		statsList.Bind(wx.EVT_KEY_DOWN, self._onKeyDown)
		statsList.Bind(wx.EVT_CONTEXT_MENU, self._onContextMenu)
		return statsList

	def _onKeyDown(self, evt: wx.KeyEvent) -> None:
		# Control+C copies the current row, Control+Shift+C everything about the current device.
		statsList = evt.GetEventObject()
		if isinstance(statsList, wx.ListCtrl) and evt.GetKeyCode() == ord("C") and evt.ControlDown():
			if not evt.AltDown():
				self._copyCurrent(statsList, wholeDevice=evt.ShiftDown())
				return
		evt.Skip()

	def _onContextMenu(self, evt: wx.ContextMenuEvent) -> None:
		statsList = evt.GetEventObject()
		if not isinstance(statsList, wx.ListCtrl):
			return
		menu = wx.Menu()
		# Translators: An item of the context menu of the statistics lists, followed by its key.
		copyRowItem = menu.Append(wx.ID_ANY, _("Copy &row\tCtrl+C"))
		# Translators: An item of the context menu of the statistics lists, followed by its key.
		copyDeviceItem = menu.Append(wx.ID_ANY, _("Copy &device\tCtrl+Shift+C"))
		self.Bind(wx.EVT_MENU, lambda e: self._copyCurrent(statsList, wholeDevice=False), copyRowItem)
		self.Bind(wx.EVT_MENU, lambda e: self._copyCurrent(statsList, wholeDevice=True), copyDeviceItem)
		statsList.PopupMenu(menu)
		menu.Destroy()

	def _copyCurrent(self, statsList: wx.ListCtrl, wholeDevice: bool) -> None:
		"""Copy the current row of a list, or everything about its device, to the clipboard."""
		index = statsList.GetFocusedItem()
		if index < 0:
			return
		headers, rows = self._listData[statsList]
		row = rows[index]
		if wholeDevice:
			text = formatDeviceText(
				row[0], self._listData[self._summaryList], self._listData[self._cyclesList]
			)
		else:
			text = formatRowText(headers, row)
		if not api.copyToClip(text):
			# Translators: Reported when copying statistics to the clipboard failed.
			ui.message(_("Failed to copy to the clipboard."))
		elif wholeDevice:
			# Translators: Reported after everything about a device was copied from the statistics.
			ui.message(_("Device copied"))
		else:
			# Translators: Reported after a row was copied from the statistics.
			ui.message(_("Row copied"))


_openDialog: UsageStatsDialog | None = None


def showStatistics(parent: wx.Window | None = None) -> None:
	"""Show the statistics window, or tell that nothing has been recorded yet."""
	global _openDialog
	if _openDialog is not None:
		# It is already open (for example from the settings): bring it forward instead of opening another one.
		_openDialog.Raise()
		return
	tracker = UsageTracker.current
	devices = tracker.getStats() if tracker is not None else []
	if not devices:
		MessageDialog.alert(
			# Translators: Message shown when no battery statistics have been recorded yet.
			_("No battery statistics have been recorded yet."),
			# Translators: The title of the window that shows the recorded battery cycles.
			_("Bluetooth battery statistics"),
			parent,
		)
		return
	dialog = _openDialog = UsageStatsDialog(parent, devices)
	try:
		displayDialogAsModal(dialog)
	finally:
		dialog.Destroy()
		_openDialog = None
