# BlueToothBatteryReport add-on for NVDA
# Copyright (C) 2026 haitun001 <476947039@qq.com>, cary-rowen <manchen_0528@outlook.com>
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from __future__ import annotations

import addonHandler
import config
from gui import guiHelper
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

config.conf.spec[CONF_SECTION] = {
	CONF_KEY_ONLY_REPORT_CONNECTED: "boolean(default=false)",
	CONF_KEY_REPORT_CONNECTED: "boolean(default=true)",
	CONF_KEY_REPORT_UNKNOWN: "boolean(default=true)",
	CONF_KEY_REPORT_DISCONNECTED: "boolean(default=true)",
	CONF_KEY_SHOW_CONNECTION_TYPE: "boolean(default=false)",
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

	def onSave(self) -> None:
		config.conf[CONF_SECTION][CONF_KEY_REPORT_CONNECTED] = self._reportConnectedCheckbox.GetValue()
		config.conf[CONF_SECTION][CONF_KEY_REPORT_UNKNOWN] = self._reportUnknownCheckbox.GetValue()
		config.conf[CONF_SECTION][CONF_KEY_REPORT_DISCONNECTED] = self._reportDisconnectedCheckbox.GetValue()
		config.conf[CONF_SECTION][CONF_KEY_SHOW_CONNECTION_TYPE] = self._showConnectionTypeCheckbox.GetValue()
