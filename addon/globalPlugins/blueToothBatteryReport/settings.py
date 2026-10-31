# BlueToothBatteryReport add-on for NVDA
# Copyright (C) 2026 haitun001 <476947039@qq.com>, cary-rowen <manchen_0528@outlook.com>
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from __future__ import annotations

import addonHandler
import config
from gui import guiHelper, nvdaControls
from gui.settingsDialogs import SettingsPanel
import wx


addonHandler.initTranslation()

CONF_SECTION: str = "bluetoothBatteryReport"
# Replaced by the per-status options below, kept only to migrate its value.
CONF_KEY_ONLY_REPORT_CONNECTED: str = "onlyReportConnected"
CONF_KEY_REPORT_CONNECTED: str = "reportConnected"
CONF_KEY_REPORT_UNKNOWN: str = "reportUnknown"
CONF_KEY_REPORT_DISCONNECTED: str = "reportDisconnected"
CONF_KEY_SHOW_CONNECTION_TYPE: str = "showConnectionType"
CONF_KEY_SHOW_CONNECTION_DURATION: str = "showConnectionDuration"
CONF_KEY_ENABLE_LOW_BATTERY_ALERT: str = "enableLowBatteryAlert"
CONF_KEY_LOW_BATTERY_THRESHOLD: str = "lowBatteryThreshold"
CONF_KEY_ALERT_SOUND_MODE: str = "alertSoundMode"
CONF_KEY_ALERT_SOUND_PATH: str = "alertSoundPath"

ALERT_SOUND_BEEP: str = "beep"
ALERT_SOUND_CUSTOM: str = "custom"
_ALERT_SOUND_MODES: tuple[str, ...] = (ALERT_SOUND_BEEP, ALERT_SOUND_CUSTOM)

config.conf.spec[CONF_SECTION] = {
	CONF_KEY_ONLY_REPORT_CONNECTED: "boolean(default=false)",
	CONF_KEY_REPORT_CONNECTED: "boolean(default=true)",
	CONF_KEY_REPORT_UNKNOWN: "boolean(default=true)",
	CONF_KEY_REPORT_DISCONNECTED: "boolean(default=true)",
	CONF_KEY_SHOW_CONNECTION_TYPE: "boolean(default=false)",
	CONF_KEY_SHOW_CONNECTION_DURATION: "boolean(default=false)",
	CONF_KEY_ENABLE_LOW_BATTERY_ALERT: "boolean(default=false)",
	CONF_KEY_LOW_BATTERY_THRESHOLD: "integer(default=20, min=5, max=50)",
	CONF_KEY_ALERT_SOUND_MODE: f"option({ALERT_SOUND_BEEP!r}, {ALERT_SOUND_CUSTOM!r}, default={ALERT_SOUND_BEEP!r})",
	CONF_KEY_ALERT_SOUND_PATH: "string(default='')",
}


def _migrateOnlyReportConnected() -> None:
	"""Convert the former "only report connected devices" option into the per-status options."""
	section = config.conf[CONF_SECTION]
	if section[CONF_KEY_ONLY_REPORT_CONNECTED]:
		section[CONF_KEY_REPORT_UNKNOWN] = False
		section[CONF_KEY_REPORT_DISCONNECTED] = False
		section[CONF_KEY_ONLY_REPORT_CONNECTED] = False


_migrateOnlyReportConnected()


class BluetoothBatterySettingsPanel(SettingsPanel):
	# Translators: The title of the Bluetooth Battery Report settings panel.
	title: str = _("Bluetooth Battery Report")

	def makeSettings(self, sizer: wx.BoxSizer) -> None:
		helper = guiHelper.BoxSizerHelper(self, sizer=sizer)
		self._reportConnectedCheckbox: wx.CheckBox = helper.addItem(
			# Translators: A checkbox to toggle whether connected Bluetooth devices are reported.
			wx.CheckBox(self, label=_("Report &connected devices")),
		)
		self._reportConnectedCheckbox.SetValue(config.conf[CONF_SECTION][CONF_KEY_REPORT_CONNECTED])

		self._reportUnknownCheckbox: wx.CheckBox = helper.addItem(
			# Translators: A checkbox to toggle whether Bluetooth devices with an unknown connection status
			# are reported.
			wx.CheckBox(self, label=_("Report &unknown status devices")),
		)
		self._reportUnknownCheckbox.SetValue(config.conf[CONF_SECTION][CONF_KEY_REPORT_UNKNOWN])

		self._reportDisconnectedCheckbox: wx.CheckBox = helper.addItem(
			# Translators: A checkbox to toggle whether disconnected Bluetooth devices are reported.
			wx.CheckBox(self, label=_("Report &disconnected devices")),
		)
		self._reportDisconnectedCheckbox.SetValue(config.conf[CONF_SECTION][CONF_KEY_REPORT_DISCONNECTED])

		self._showConnectionTypeCheckbox: wx.CheckBox = helper.addItem(
			# Translators: A checkbox to toggle whether the connection type (Classic or LE) of each device is reported.
			wx.CheckBox(self, label=_("Show connection &type (Classic or LE)")),
		)
		self._showConnectionTypeCheckbox.SetValue(config.conf[CONF_SECTION][CONF_KEY_SHOW_CONNECTION_TYPE])

		self._showConnectionDurationCheckbox: wx.CheckBox = helper.addItem(
			# Translators: A checkbox to toggle whether the time a device has been connected is reported.
			wx.CheckBox(self, label=_("Show connection &duration")),
		)
		self._showConnectionDurationCheckbox.SetValue(
			config.conf[CONF_SECTION][CONF_KEY_SHOW_CONNECTION_DURATION],
		)

		self._enableLowBatteryAlertCheckbox: wx.CheckBox = helper.addItem(
			# Translators: A checkbox to toggle the alert that is given when the battery of a connected
			# Bluetooth device is low.
			wx.CheckBox(self, label=_("Enable &low battery alert")),
		)
		self._enableLowBatteryAlertCheckbox.SetValue(
			config.conf[CONF_SECTION][CONF_KEY_ENABLE_LOW_BATTERY_ALERT],
		)
		self._enableLowBatteryAlertCheckbox.Bind(wx.EVT_CHECKBOX, self._onAlertSettingChanged)

		self._thresholdSpin: nvdaControls.SelectOnFocusSpinCtrl = helper.addLabeledControl(
			# Translators: The label of a spin box to set the battery percentage at or below which the
			# low battery alert is given.
			_("Low battery &threshold (%):"),
			nvdaControls.SelectOnFocusSpinCtrl,
			min=5,
			max=50,
			initial=config.conf[CONF_SECTION][CONF_KEY_LOW_BATTERY_THRESHOLD],
		)

		self._soundModeChoice: wx.Choice = helper.addLabeledControl(
			# Translators: The label of a list to choose the sound of the low battery alert.
			_("Alert &sound:"),
			wx.Choice,
			# Translators: The choices of the alert sound list: a beep, or a sound file chosen by the user.
			choices=[_("Beep"), _("Custom sound file")],
		)
		self._soundModeChoice.SetSelection(
			_ALERT_SOUND_MODES.index(config.conf[CONF_SECTION][CONF_KEY_ALERT_SOUND_MODE]),
		)
		self._soundModeChoice.Bind(wx.EVT_CHOICE, self._onAlertSettingChanged)

		self._soundPathEdit: wx.TextCtrl = helper.addLabeledControl(
			# Translators: The label of an edit field with the path of the custom alert sound file.
			_("Custom sound &file (.wav):"),
			wx.TextCtrl,
		)
		self._soundPathEdit.SetValue(config.conf[CONF_SECTION][CONF_KEY_ALERT_SOUND_PATH])

		self._browseButton: wx.Button = helper.addItem(
			# Translators: The label of a button to browse for the custom alert sound file.
			wx.Button(self, label=_("&Browse...")),
		)
		self._browseButton.Bind(wx.EVT_BUTTON, self._onBrowse)
		self._updateAlertControls()

	def _updateAlertControls(self) -> None:
		enabled = self._enableLowBatteryAlertCheckbox.GetValue()
		custom = _ALERT_SOUND_MODES[self._soundModeChoice.GetSelection()] == ALERT_SOUND_CUSTOM
		self._thresholdSpin.Enable(enabled)
		self._soundModeChoice.Enable(enabled)
		self._soundPathEdit.Enable(enabled and custom)
		self._browseButton.Enable(enabled and custom)

	def _onAlertSettingChanged(self, evt: wx.CommandEvent) -> None:
		self._updateAlertControls()

	def _onBrowse(self, evt: wx.CommandEvent) -> None:
		with wx.FileDialog(
			self,
			# Translators: The title of the dialog to choose the custom alert sound file.
			message=_("Select alert sound"),
			# Translators: The name of the wave file type in the dialog to choose the alert sound file.
			wildcard=_("Wave files (*.wav)") + "|*.wav",
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
		) as dialog:
			if dialog.ShowModal() == wx.ID_OK:
				self._soundPathEdit.SetValue(dialog.GetPath())

	def onSave(self) -> None:
		config.conf[CONF_SECTION][CONF_KEY_REPORT_CONNECTED] = self._reportConnectedCheckbox.GetValue()
		config.conf[CONF_SECTION][CONF_KEY_REPORT_UNKNOWN] = self._reportUnknownCheckbox.GetValue()
		config.conf[CONF_SECTION][CONF_KEY_REPORT_DISCONNECTED] = self._reportDisconnectedCheckbox.GetValue()
		config.conf[CONF_SECTION][CONF_KEY_SHOW_CONNECTION_TYPE] = self._showConnectionTypeCheckbox.GetValue()
		config.conf[CONF_SECTION][CONF_KEY_SHOW_CONNECTION_DURATION] = (
			self._showConnectionDurationCheckbox.GetValue()
		)
		config.conf[CONF_SECTION][CONF_KEY_ENABLE_LOW_BATTERY_ALERT] = (
			self._enableLowBatteryAlertCheckbox.GetValue()
		)
		config.conf[CONF_SECTION][CONF_KEY_LOW_BATTERY_THRESHOLD] = self._thresholdSpin.GetValue()
		config.conf[CONF_SECTION][CONF_KEY_ALERT_SOUND_MODE] = _ALERT_SOUND_MODES[
			self._soundModeChoice.GetSelection()
		]
		config.conf[CONF_SECTION][CONF_KEY_ALERT_SOUND_PATH] = self._soundPathEdit.GetValue()
