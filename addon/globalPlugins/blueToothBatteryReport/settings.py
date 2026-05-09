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
CONF_KEY_ONLY_REPORT_CONNECTED: str = "onlyReportConnected"

config.conf.spec[CONF_SECTION] = {
	CONF_KEY_ONLY_REPORT_CONNECTED: "boolean(default=false)",
}


class BluetoothBatterySettingsPanel(SettingsPanel):
	# Translators: The title of the Bluetooth Battery Report settings panel.
	title: str = _("Bluetooth Battery Report")

	def makeSettings(self, sizer: wx.BoxSizer) -> None:
		helper = guiHelper.BoxSizerHelper(self, sizer=sizer)
		self._onlyReportConnectedCheckbox: wx.CheckBox = helper.addItem(
			# Translators: A checkbox to toggle whether only connected Bluetooth devices should be reported.
			wx.CheckBox(self, label=_("Only report &connected devices")),
		)
		self._onlyReportConnectedCheckbox.SetValue(config.conf[CONF_SECTION][CONF_KEY_ONLY_REPORT_CONNECTED])

	def onSave(self) -> None:
		config.conf[CONF_SECTION][CONF_KEY_ONLY_REPORT_CONNECTED] = (
			self._onlyReportConnectedCheckbox.GetValue()
		)
