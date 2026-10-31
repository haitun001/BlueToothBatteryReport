# BlueToothBatteryReport add-on for NVDA
# Copyright (C) 2026 haitun001 <476947039@qq.com>, cary-rowen <manchen_0528@outlook.com>
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from __future__ import annotations

import addonHandler

addonHandler.initTranslation()


def formatDuration(seconds: float) -> str:
	"""Return a spoken duration such as '45 min', '2 hr' or '1 hr 25 min'."""
	totalMinutes = int(seconds // 60)
	hours, minutes = divmod(totalMinutes, 60)
	if hours == 0:
		# Translators: A duration in minutes only, for example "45 min".
		return _("{minutes} min").format(minutes=minutes)
	if minutes == 0:
		# Translators: A duration in whole hours only, for example "2 hr".
		return _("{hours} hr").format(hours=hours)
	# Translators: A duration in hours and minutes, for example "1 hr 25 min".
	return _("{hours} hr {minutes} min").format(hours=hours, minutes=minutes)
