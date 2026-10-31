# BlueToothBatteryReport add-on for NVDA
# Copyright (C) 2026 haitun001 <476947039@qq.com>, cary-rowen <manchen_0528@outlook.com>
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from __future__ import annotations

import ctypes
import os
import re
import threading
from ctypes import POINTER, Structure, byref, c_void_p, sizeof, windll
from ctypes.wintypes import BOOL, DWORD, HANDLE, ULONG
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, IntEnum

import addonHandler
from comtypes import GUID
import config
import core
import globalPluginHandler
import globalVars
from gui.message import MessageDialog
from gui.settingsDialogs import NVDASettingsDialog
import inputCore
from logHandler import log
import nvwave
from scriptHandler import script
import tones
import ui
from winAPI.constants import SystemErrorCodes
from winBindings.bthprops import BLUETOOTH_DEVICE_INFO
from winBindings.kernel32 import SYSTEMTIME, CloseHandle
from winBindings.setupapi import (
	DEVPROPKEY,
	DIGCF,
	HDEVINFO,
	SP_DEVINFO_DATA,
	SPDRP,
	SetupDiDestroyDeviceInfoList,
	SetupDiEnumDeviceInfo,
	SetupDiGetClassDevs,
	SetupDiGetDeviceProperty,
	SetupDiGetDeviceRegistryProperty,
)
import wx

from .settings import (
	ALERT_SOUND_CUSTOM,
	BluetoothBatterySettingsPanel,
	CONF_KEY_ALERT_SOUND_MODE,
	CONF_KEY_ALERT_SOUND_PATH,
	CONF_KEY_ENABLE_LOW_BATTERY_ALERT,
	CONF_KEY_LOW_BATTERY_THRESHOLD,
	CONF_KEY_REPORT_CONNECTED,
	CONF_KEY_REPORT_DISCONNECTED,
	CONF_KEY_REPORT_UNKNOWN,
	CONF_KEY_SHOW_CONNECTION_DURATION,
	CONF_KEY_SHOW_CONNECTION_TYPE,
	CONF_KEY_TRACK_CONNECTION_TIME,
	CONF_SECTION,
)
from .formatting import formatDuration
from .statsDialog import showStatistics
from .usage import USAGE_FILE_NAME, DeviceObservation, UsageTracker

addonHandler.initTranslation()

CR_SUCCESS = 0
MAX_DEVICE_ID_LEN = 200

CM_Get_Device_ID = windll.cfgmgr32.CM_Get_Device_IDW
CM_Get_Device_ID.argtypes = (DWORD, ctypes.c_wchar_p, ULONG, ULONG)
CM_Get_Device_ID.restype = DWORD


# Translators: The name of a category of NVDA commands.
SCRIPT_CATEGORY: str = _("Bluetooth Battery Report")

_DIGCF_ALLCLASSES = 0x00000004
_BLUETOOTH_INSTANCE_ID_PREFIXES: tuple[str, ...] = (
	"BTHENUM\\",
	"BTHLE\\",
	"BTHLEDEVICE\\",
)
_BLUETOOTH_ROOT_INSTANCE_ID_PREFIXES: tuple[str, ...] = ("BTHENUM\\DEV_", "BTHLE\\DEV_")

_DEVPROP_TYPE_BYTE = 0x00000003
_DEVPROP_TYPE_UINT32 = 0x00000007
_DEVPROP_TYPE_STRING = 0x00000012
_DN_DEVICE_DISCONNECTED = 0x02000000
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
# The last used time of a device can be stale or reset by Windows, so longer times are not reported.
_MAX_CONNECTION_SECONDS = 7 * 24 * 60 * 60
# How often the battery levels are checked in the background for the low battery alert.
_MONITOR_INTERVAL_MS = 5 * 60 * 1000


class ConnectionStatus(IntEnum):
	CONNECTED = 0
	UNKNOWN = 1
	DISCONNECTED = 2


_STATUS_REPORT_CONF_KEYS: dict[ConnectionStatus, str] = {
	ConnectionStatus.CONNECTED: CONF_KEY_REPORT_CONNECTED,
	ConnectionStatus.UNKNOWN: CONF_KEY_REPORT_UNKNOWN,
	ConnectionStatus.DISCONNECTED: CONF_KEY_REPORT_DISCONNECTED,
}


class ConnectionType(Enum):
	"""The kind of Bluetooth connection a device uses."""

	CLASSIC = "Classic"
	LE = "LE"


@dataclass(frozen=True)
class BluetoothDevice:
	name: str
	battery: int
	status: ConnectionStatus
	instanceId: str
	address: str | None = None
	connectionType: ConnectionType | None = None
	# When the current connection started, as reported by Windows (Bluetooth Classic devices only).
	lastConnected: datetime | None = None


@dataclass(frozen=True)
class _ClassicDeviceState:
	connected: bool
	lastUsed: datetime | None


@dataclass(frozen=True)
class _BluetoothBatteryCandidate:
	name: str
	battery: int
	instanceId: str
	devInst: int
	address: str | None
	connectionType: ConnectionType | None


class BLUETOOTH_FIND_RADIO_PARAMS(Structure):
	_fields_ = (("dwSize", DWORD),)

	def __init__(self) -> None:
		super().__init__(dwSize=sizeof(self))


class BLUETOOTH_DEVICE_SEARCH_PARAMS(Structure):
	_fields_ = (
		("dwSize", DWORD),
		("fReturnAuthenticated", BOOL),
		("fReturnRemembered", BOOL),
		("fReturnUnknown", BOOL),
		("fReturnConnected", BOOL),
		("fIssueInquiry", BOOL),
		("cTimeoutMultiplier", ctypes.c_ubyte),
		("hRadio", HANDLE),
	)

	def __init__(self, radioHandle: HANDLE) -> None:
		super().__init__(
			dwSize=sizeof(self),
			fReturnAuthenticated=True,
			fReturnRemembered=True,
			fReturnUnknown=True,
			fReturnConnected=True,
			fIssueInquiry=False,
			cTimeoutMultiplier=0,
			hRadio=radioHandle,
		)


_cfgMgr32 = windll.cfgmgr32
_CM_Get_DevNode_Property = _cfgMgr32.CM_Get_DevNode_PropertyW
_CM_Get_DevNode_Property.argtypes = (
	DWORD,
	POINTER(DEVPROPKEY),
	POINTER(ULONG),
	c_void_p,
	POINTER(ULONG),
	ULONG,
)
_CM_Get_DevNode_Property.restype = DWORD

_bthprops = windll["bthprops.cpl"]
_BluetoothFindFirstRadio = _bthprops.BluetoothFindFirstRadio
_BluetoothFindFirstRadio.argtypes = (
	POINTER(BLUETOOTH_FIND_RADIO_PARAMS),
	POINTER(HANDLE),
)
_BluetoothFindFirstRadio.restype = c_void_p

_BluetoothFindNextRadio = _bthprops.BluetoothFindNextRadio
_BluetoothFindNextRadio.argtypes = (c_void_p, POINTER(HANDLE))
_BluetoothFindNextRadio.restype = BOOL

_BluetoothFindRadioClose = _bthprops.BluetoothFindRadioClose
_BluetoothFindRadioClose.argtypes = (c_void_p,)
_BluetoothFindRadioClose.restype = BOOL

_BluetoothFindFirstDevice = _bthprops.BluetoothFindFirstDevice
_BluetoothFindFirstDevice.argtypes = (
	POINTER(BLUETOOTH_DEVICE_SEARCH_PARAMS),
	POINTER(BLUETOOTH_DEVICE_INFO),
)
_BluetoothFindFirstDevice.restype = c_void_p

_BluetoothFindNextDevice = _bthprops.BluetoothFindNextDevice
_BluetoothFindNextDevice.argtypes = (c_void_p, POINTER(BLUETOOTH_DEVICE_INFO))
_BluetoothFindNextDevice.restype = BOOL

_BluetoothFindDeviceClose = _bthprops.BluetoothFindDeviceClose
_BluetoothFindDeviceClose.argtypes = (c_void_p,)
_BluetoothFindDeviceClose.restype = BOOL

DEVPKEY_Bluetooth_Battery = DEVPROPKEY(GUID("{104EA319-6EE2-4701-BD47-8DDBF425BBE5}"), 2)
DEVPKEY_NAME = DEVPROPKEY(GUID("{B725F130-47EF-101A-A5F1-02608C9EEBAC}"), 10)
DEVPKEY_Device_FriendlyName = DEVPROPKEY(GUID("{A45C254E-DF1C-4EFD-8020-67D146A850E0}"), 14)
DEVPKEY_Device_DevNodeStatus = DEVPROPKEY(GUID("{4340A6C5-93FA-4706-972C-7B648008A5A7}"), 2)


def _getInstanceId(devInfo: SP_DEVINFO_DATA) -> str | None:
	buffer = ctypes.create_unicode_buffer(MAX_DEVICE_ID_LEN + 1)
	result = CM_Get_Device_ID(devInfo.DevInst, buffer, len(buffer), 0)
	if result != CR_SUCCESS:
		log.debugWarning(f"CM_Get_Device_ID failed for devInst {devInfo.DevInst}: {result}")
		return None
	return buffer.value or None


def _readRegistryString(
	deviceInfoSet: HDEVINFO,
	devInfo: SP_DEVINFO_DATA,
	propertyId: SPDRP,
) -> str | None:
	propType = DWORD()
	requiredSize = DWORD()
	SetupDiGetDeviceRegistryProperty(
		deviceInfoSet,
		byref(devInfo),
		propertyId,
		byref(propType),
		None,
		0,
		byref(requiredSize),
	)
	lastError = ctypes.GetLastError()
	if lastError != SystemErrorCodes.INSUFFICIENT_BUFFER or requiredSize.value == 0:
		return None
	buffer = ctypes.create_unicode_buffer(max(1, requiredSize.value // sizeof(ctypes.c_wchar)))
	if not SetupDiGetDeviceRegistryProperty(
		deviceInfoSet,
		byref(devInfo),
		propertyId,
		byref(propType),
		byref(buffer),
		requiredSize,
		byref(requiredSize),
	):
		return None
	return buffer.value or None


def _readDevicePropertyString(
	deviceInfoSet: HDEVINFO,
	devInfo: SP_DEVINFO_DATA,
	propertyKey: DEVPROPKEY,
) -> str | None:
	propType = ULONG()
	requiredSize = DWORD()
	SetupDiGetDeviceProperty(
		deviceInfoSet,
		byref(devInfo),
		byref(propertyKey),
		byref(propType),
		None,
		0,
		byref(requiredSize),
		0,
	)
	lastError = ctypes.GetLastError()
	if lastError != SystemErrorCodes.INSUFFICIENT_BUFFER or requiredSize.value == 0:
		return None
	buffer = ctypes.create_unicode_buffer(max(1, requiredSize.value // sizeof(ctypes.c_wchar)))
	if not SetupDiGetDeviceProperty(
		deviceInfoSet,
		byref(devInfo),
		byref(propertyKey),
		byref(propType),
		byref(buffer),
		requiredSize,
		byref(requiredSize),
		0,
	):
		return None
	if propType.value != _DEVPROP_TYPE_STRING:
		return None
	return buffer.value or None


def _readDeviceName(deviceInfoSet: HDEVINFO, devInfo: SP_DEVINFO_DATA) -> str | None:
	return (
		_readDevicePropertyString(deviceInfoSet, devInfo, DEVPKEY_Device_FriendlyName)
		or _readDevicePropertyString(deviceInfoSet, devInfo, DEVPKEY_NAME)
		or _readRegistryString(deviceInfoSet, devInfo, SPDRP.FRIENDLYNAME)
		or _readRegistryString(deviceInfoSet, devInfo, SPDRP.DEVICEDESC)
	)


def _readBatteryPercentFromDevInst(devInst: int) -> int | None:
	propType = ULONG(_DEVPROP_TYPE_BYTE)
	value = ctypes.c_ubyte()
	size = ULONG(sizeof(value))
	result = _CM_Get_DevNode_Property(
		devInst,
		byref(DEVPKEY_Bluetooth_Battery),
		byref(propType),
		byref(value),
		byref(size),
		0,
	)
	if result != CR_SUCCESS or propType.value != _DEVPROP_TYPE_BYTE:
		return None
	battery = int(value.value)
	return battery if 0 <= battery <= 100 else None


def _readDevNodeStatusFromDevInst(devInst: int) -> int | None:
	propType = ULONG(_DEVPROP_TYPE_UINT32)
	value = ULONG()
	size = ULONG(sizeof(value))
	result = _CM_Get_DevNode_Property(
		devInst,
		byref(DEVPKEY_Device_DevNodeStatus),
		byref(propType),
		byref(value),
		byref(size),
		0,
	)
	if result != CR_SUCCESS or propType.value != _DEVPROP_TYPE_UINT32:
		return None
	return int(value.value)


def _extractBluetoothAddress(instanceId: str) -> str | None:
	"""Extract a 12-character Bluetooth address from a device instance ID."""
	upperId = instanceId.upper()
	for pattern in (
		r"DEV_([0-9A-F]{12})",
		r"&0&([0-9A-F]{12})_C",
		r"_([0-9A-F]{12})\\[^\\]+$",
	):
		if match := re.search(pattern, upperId):
			return match.group(1)
	return None


def _getConnectionType(instanceId: str) -> ConnectionType | None:
	"""Return the connection type implied by a device instance ID."""
	upperId = instanceId.upper()
	if upperId.startswith("BTHENUM\\"):
		return ConnectionType.CLASSIC
	if upperId.startswith(("BTHLE\\", "BTHLEDEVICE\\")):
		return ConnectionType.LE
	return None


def _systemTimeToDatetime(systemTime: SYSTEMTIME) -> datetime | None:
	"""Convert a SYSTEMTIME to a naive local datetime, or None if it is zeroed (never used).

	Despite the Windows documentation, the stLastUsed value of the classic Bluetooth API holds local time,
	not UTC.
	"""
	if systemTime.wYear == 0:
		return None
	try:
		return datetime(
			systemTime.wYear,
			systemTime.wMonth,
			systemTime.wDay,
			systemTime.wHour,
			systemTime.wMinute,
			systemTime.wSecond,
		)
	except ValueError:
		return None


def _collectClassicConnectionStates() -> dict[str, _ClassicDeviceState]:
	"""Return connection states reported by the classic Bluetooth API."""
	results: dict[str, _ClassicDeviceState] = {}
	radioParams = BLUETOOTH_FIND_RADIO_PARAMS()
	radioHandle = HANDLE()
	radioFindHandle = _BluetoothFindFirstRadio(byref(radioParams), byref(radioHandle))
	if not radioFindHandle:
		return results
	try:
		while True:
			searchParams = BLUETOOTH_DEVICE_SEARCH_PARAMS(radioHandle)
			deviceInfo = BLUETOOTH_DEVICE_INFO()
			deviceFindHandle = _BluetoothFindFirstDevice(byref(searchParams), byref(deviceInfo))
			if deviceFindHandle:
				try:
					while True:
						results[f"{deviceInfo.address:012X}"] = _ClassicDeviceState(
							connected=bool(deviceInfo.fConnected),
							lastUsed=_systemTimeToDatetime(deviceInfo.stLastUsed),
						)
						if not _BluetoothFindNextDevice(deviceFindHandle, byref(deviceInfo)):
							break
				finally:
					_BluetoothFindDeviceClose(deviceFindHandle)
			CloseHandle(radioHandle)
			radioHandle = HANDLE()
			if not _BluetoothFindNextRadio(radioFindHandle, byref(radioHandle)):
				break
	finally:
		if radioHandle:
			CloseHandle(radioHandle)
		_BluetoothFindRadioClose(radioFindHandle)
	return results


def _getConnectionStatus(
	address: str | None,
	nodeDevInst: int,
	rootDevInst: int | None,
	classicConnectionStates: dict[str, _ClassicDeviceState],
) -> ConnectionStatus:
	"""Return the best known connection status for a device."""
	if address is not None and address in classicConnectionStates:
		if classicConnectionStates[address].connected:
			return ConnectionStatus.CONNECTED
		return ConnectionStatus.DISCONNECTED

	devInsts: list[int] = []
	if rootDevInst is not None:
		devInsts.append(rootDevInst)
	if nodeDevInst not in devInsts:
		devInsts.append(nodeDevInst)

	foundStatus = False
	for devInst in devInsts:
		status = _readDevNodeStatusFromDevInst(devInst)
		if status is None:
			continue
		foundStatus = True
		if status & _DN_DEVICE_DISCONNECTED:
			return ConnectionStatus.DISCONNECTED
	return ConnectionStatus.CONNECTED if foundStatus else ConnectionStatus.UNKNOWN


def _getConnectionSeconds(device: BluetoothDevice, now: datetime) -> float | None:
	"""Return for how many seconds a connected device has been connected, if Windows reports it."""
	if device.status != ConnectionStatus.CONNECTED or device.lastConnected is None:
		return None
	elapsed = (now - device.lastConnected).total_seconds()
	return elapsed if 0 < elapsed < _MAX_CONNECTION_SECONDS else None


def _formatDeviceReport(device: BluetoothDevice, now: datetime, totalSeconds: float | None = None) -> str:
	"""Return the spoken report of a device, according to the user's settings.

	:param totalSeconds: The total connection time since the last recharge, if it is measured.
		It is announced instead of the connection time reported by Windows.
	"""
	if config.conf[CONF_SECTION][CONF_KEY_SHOW_CONNECTION_TYPE] and device.connectionType is not None:
		# Translators: Reported for each Bluetooth device when the connection type is shown.
		# {name} is the device name, {connectionType} is the connection type (Classic or LE)
		# and {battery} is the battery percentage.
		report = _("{name} ({connectionType}) battery {battery} percent").format(
			name=device.name,
			connectionType=device.connectionType.value,
			battery=device.battery,
		)
	else:
		# Translators: Reported for each Bluetooth device.
		# {name} is the device name and {battery} is the battery percentage.
		report = _("{name} battery {battery} percent").format(name=device.name, battery=device.battery)
	if config.conf[CONF_SECTION][CONF_KEY_SHOW_CONNECTION_DURATION]:
		seconds = totalSeconds if totalSeconds is not None else _getConnectionSeconds(device, now)
		if seconds is not None:
			# Translators: Appended to the report of a device when the connection duration is shown.
			# {report} is the report of the device and {duration} is for example "1 hr 25 min".
			report = _("{report} (connected {duration})").format(
				report=report,
				duration=formatDuration(seconds),
			)
	return report


def _isStatusReported(status: ConnectionStatus) -> bool:
	"""Return whether the user wants devices with this connection status to be reported."""
	return config.conf[CONF_SECTION][_STATUS_REPORT_CONF_KEYS[status]]


def collectBluetoothBattery() -> list[BluetoothDevice]:
	"""
	Collect Bluetooth devices with reported battery percentages.

	The result is not filtered by the "report ... devices" settings, see :func:`_isStatusReported`.

	:return: Bluetooth devices sorted by connection status and name.
	:raises OSError: If SetupAPI device enumeration fails.
	"""
	flags = int(DIGCF.PRESENT) | _DIGCF_ALLCLASSES
	deviceInfoSet = SetupDiGetClassDevs(None, None, None, flags)
	if deviceInfoSet == _INVALID_HANDLE_VALUE:
		raise ctypes.WinError()

	rootNames: dict[str, str] = {}
	rootDevInsts: dict[str, int] = {}
	rootConnectionTypes: dict[str, ConnectionType | None] = {}
	batteryCandidates: list[_BluetoothBatteryCandidate] = []
	try:
		index = 0
		while True:
			devInfo = SP_DEVINFO_DATA()
			devInfo.cbSize = sizeof(devInfo)
			if not SetupDiEnumDeviceInfo(deviceInfoSet, index, byref(devInfo)):
				if ctypes.GetLastError() == SystemErrorCodes.NO_MORE_ITEMS:
					break
				raise ctypes.WinError()
			index += 1

			instanceId = _getInstanceId(devInfo)
			if instanceId is None:
				continue
			upperId = instanceId.upper()
			if not upperId.startswith(_BLUETOOTH_INSTANCE_ID_PREFIXES):
				continue

			address = _extractBluetoothAddress(instanceId)
			name = _readDeviceName(deviceInfoSet, devInfo) or instanceId
			devInst = int(devInfo.DevInst)
			if upperId.startswith(_BLUETOOTH_ROOT_INSTANCE_ID_PREFIXES) and address is not None:
				rootNames[address] = name
				rootDevInsts[address] = devInst
				rootConnectionTypes[address] = _getConnectionType(instanceId)

			battery = _readBatteryPercentFromDevInst(devInst)
			if battery is None:
				continue
			batteryCandidates.append(
				_BluetoothBatteryCandidate(
					name=name,
					battery=battery,
					instanceId=instanceId,
					devInst=devInst,
					address=address,
					connectionType=_getConnectionType(instanceId),
				),
			)
	finally:
		SetupDiDestroyDeviceInfoList(deviceInfoSet)

	classicConnectionStates = _collectClassicConnectionStates()
	finalDevices: dict[str, BluetoothDevice] = {}
	for candidate in batteryCandidates:
		name = rootNames.get(candidate.address or "", candidate.name)
		status = _getConnectionStatus(
			candidate.address,
			candidate.devInst,
			rootDevInsts.get(candidate.address or ""),
			classicConnectionStates,
		)
		classicState = classicConnectionStates.get(candidate.address or "")
		key = candidate.address or candidate.instanceId
		finalDevices[key] = BluetoothDevice(
			name=name,
			battery=candidate.battery,
			status=status,
			instanceId=candidate.instanceId,
			address=candidate.address,
			connectionType=rootConnectionTypes.get(candidate.address or "", candidate.connectionType),
			lastConnected=classicState.lastUsed if classicState is not None else None,
		)
	return sorted(
		finalDevices.values(),
		key=lambda device: (int(device.status), device.name.lower()),
	)


def _toObservation(device: BluetoothDevice, now: datetime) -> DeviceObservation:
	"""Return what the usage tracker needs to know about a device."""
	return DeviceObservation(
		name=device.name,
		battery=device.battery,
		statusRank=int(device.status),
		disconnected=device.status == ConnectionStatus.DISCONNECTED,
		windowsConnectionSeconds=_getConnectionSeconds(device, now),
	)


def _updateLowBatteryAlerts(
	devices: list[BluetoothDevice],
	threshold: int,
	alertedKeys: set[str],
) -> list[BluetoothDevice]:
	"""Return the connected devices whose battery just became low, and update `alertedKeys`.

	A device is only returned once, until its battery recovers above the threshold or it is gone.
	"""
	lowDevices: list[BluetoothDevice] = []
	currentKeys: set[str] = set()
	for device in devices:
		key = device.address or device.instanceId
		currentKeys.add(key)
		if device.battery > threshold:
			alertedKeys.discard(key)
		elif device.status == ConnectionStatus.CONNECTED and key not in alertedKeys:
			alertedKeys.add(key)
			lowDevices.append(device)
	alertedKeys.intersection_update(currentKeys)
	return lowDevices


def _playAlertSound() -> None:
	"""Play the configured low battery alert sound. A beep is played if there is no usable sound file."""
	section = config.conf[CONF_SECTION]
	if section[CONF_KEY_ALERT_SOUND_MODE] == ALERT_SOUND_CUSTOM:
		path = section[CONF_KEY_ALERT_SOUND_PATH]
		if path and os.path.isfile(path):
			try:
				nvwave.playWaveFile(path)
				return
			except Exception:
				log.debugWarning(f"Could not play the alert sound {path!r}", exc_info=True)
	tones.beep(500, 400)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self) -> None:
		super().__init__()
		if BluetoothBatterySettingsPanel not in NVDASettingsDialog.categoryClasses:
			NVDASettingsDialog.categoryClasses.append(BluetoothBatterySettingsPanel)
		self._usageTracker = UsageTracker(os.path.join(globalVars.appArgs.configPath, USAGE_FILE_NAME))
		self._alertedDeviceKeys: set[str] = set()
		self._monitorLock = threading.Lock()
		self._monitorTimer: wx.CallLater | None = core.callLater(_MONITOR_INTERVAL_MS, self._monitorTick)

	def _monitorTick(self) -> None:
		"""Start a background check, if needed, and schedule the next one."""
		self._monitorTimer = core.callLater(_MONITOR_INTERVAL_MS, self._monitorTick)
		section = config.conf[CONF_SECTION]
		alert: bool = section[CONF_KEY_ENABLE_LOW_BATTERY_ALERT]
		track: bool = section[CONF_KEY_TRACK_CONNECTION_TIME]
		if not alert and not track:
			return
		if not self._monitorLock.acquire(blocking=False):
			# The previous check is still running.
			return
		threshold: int = section[CONF_KEY_LOW_BATTERY_THRESHOLD]
		threading.Thread(
			target=self._monitorScan,
			args=(alert, track, threshold),
			name="BluetoothBatteryReport.monitor",
			daemon=True,
		).start()

	def _updateUsage(self, devices: list[BluetoothDevice], track: bool) -> None:
		"""Give a scan to the usage tracker: the statuses, and the connection times if they are measured."""
		now = datetime.now()
		observations = [_toObservation(device, now) for device in devices]
		self._usageTracker.noteStatus(observations)
		if track:
			self._usageTracker.update(observations)

	def _getTotalSeconds(self, device: BluetoothDevice, track: bool) -> float | None:
		"""Return the measured total connection time of a device, if it is measured and known."""
		if not track or device.status == ConnectionStatus.DISCONNECTED:
			return None
		return self._usageTracker.getTotalSeconds(device.name) or None

	def _monitorScan(self, alert: bool, track: bool, threshold: int) -> None:
		"""Check the battery levels (runs in a background thread): measure times and alert about low batteries."""
		try:
			devices = collectBluetoothBattery()
			self._updateUsage(devices, track)
			lowDevices = _updateLowBatteryAlerts(devices, threshold, self._alertedDeviceKeys) if alert else []
		except Exception:
			log.exception("Error checking Bluetooth battery levels")
			return
		finally:
			self._monitorLock.release()
		if lowDevices:
			wx.CallAfter(self._showLowBatteryAlert, lowDevices)

	def _showLowBatteryAlert(self, devices: list[BluetoothDevice]) -> None:
		_playAlertSound()
		lines = [
			# Translators: Part of the low battery alert, one line per device.
			# {name} is the device name and {battery} is the battery percentage.
			_("{name} battery low: {battery} percent").format(name=device.name, battery=device.battery)
			for device in devices
		]
		MessageDialog.alert(
			"\n".join(lines),
			# Translators: The title of the low battery alert dialog.
			_("Bluetooth Battery Low"),
		)

	def terminate(self) -> None:
		if self._monitorTimer is not None:
			self._monitorTimer.Stop()
			self._monitorTimer = None
		try:
			NVDASettingsDialog.categoryClasses.remove(BluetoothBatterySettingsPanel)
		except ValueError:
			pass
		super().terminate()

	@script(
		# Translators: Description for the command that opens the window with the battery statistics.
		description=_("Opens the Bluetooth battery statistics."),
		category=SCRIPT_CATEGORY,
		# No gesture is assigned by default. Users can assign one in the Input Gestures dialog.
	)
	def script_openBatteryStatistics(self, gesture: inputCore.InputGesture) -> None:
		# The window is modal, so it is not opened directly from the script.
		wx.CallAfter(showStatistics)

	@script(
		# Translators: Description for the command to report Bluetooth battery levels.
		description=_("Reports the battery percentage of all local Bluetooth devices."),
		category=SCRIPT_CATEGORY,
		gesture="kb:NVDA+control+shift+b",
		speakOnDemand=True,
	)
	def script_reportBluetoothBattery(self, gesture: inputCore.InputGesture) -> None:
		track: bool = config.conf[CONF_SECTION][CONF_KEY_TRACK_CONNECTION_TIME]
		try:
			allDevices = collectBluetoothBattery()
			self._updateUsage(allDevices, track)
		except Exception:
			log.exception("Error reporting Bluetooth battery levels")
			# Translators: Message reported when Bluetooth battery detection fails.
			ui.message(_("Bluetooth battery detection failed."))
			return
		devices = [device for device in allDevices if _isStatusReported(device.status)]

		if not devices:
			# Translators: Message reported when no Bluetooth battery information is available.
			ui.message(_("No Bluetooth battery information is available."))
			return

		now = datetime.now()
		deviceReports = [
			_formatDeviceReport(device, now, self._getTotalSeconds(device, track)) for device in devices
		]
		ui.message("; ".join(deviceReports))
