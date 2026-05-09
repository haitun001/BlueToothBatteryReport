# BlueToothBatteryReport add-on for NVDA
# Copyright (C) 2026 haitun001 <476947039@qq.com>, cary-rowen <manchen_0528@outlook.com>
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.

from __future__ import annotations

import ctypes
import re
from ctypes import POINTER, Structure, byref, c_void_p, sizeof, windll
from ctypes.wintypes import BOOL, DWORD, HANDLE, ULONG
from dataclasses import dataclass
from enum import IntEnum

import addonHandler
from comtypes import GUID
import config
import globalPluginHandler
from gui.settingsDialogs import NVDASettingsDialog
import inputCore
from logHandler import log
from scriptHandler import script
import ui
from winAPI.constants import SystemErrorCodes
from winBindings.bthprops import BLUETOOTH_DEVICE_INFO
from winBindings.kernel32 import CloseHandle
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

from .settings import (
	BluetoothBatterySettingsPanel,
	CONF_KEY_ONLY_REPORT_CONNECTED,
	CONF_SECTION,
)

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


class ConnectionStatus(IntEnum):
	CONNECTED = 0
	UNKNOWN = 1
	DISCONNECTED = 2


@dataclass(frozen=True)
class BluetoothDevice:
	name: str
	battery: int
	status: ConnectionStatus
	instanceId: str
	address: str | None = None


@dataclass(frozen=True)
class _BluetoothBatteryCandidate:
	name: str
	battery: int
	instanceId: str
	devInst: int
	address: str | None


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


def _collectClassicConnectionStates() -> dict[str, bool]:
	"""Return connection states reported by the classic Bluetooth API."""
	results: dict[str, bool] = {}
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
						results[f"{deviceInfo.address:012X}"] = bool(deviceInfo.fConnected)
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
	classicConnectionStates: dict[str, bool],
) -> ConnectionStatus:
	"""Return the best known connection status for a device."""
	if address is not None and address in classicConnectionStates:
		if classicConnectionStates[address]:
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


def collectBluetoothBattery() -> list[BluetoothDevice]:
	"""
	Collect Bluetooth devices with reported battery percentages.

	:return: Bluetooth devices sorted by connection status and name.
	:raises OSError: If SetupAPI device enumeration fails.
	"""
	flags = int(DIGCF.PRESENT) | _DIGCF_ALLCLASSES
	deviceInfoSet = SetupDiGetClassDevs(None, None, None, flags)
	if deviceInfoSet == _INVALID_HANDLE_VALUE:
		raise ctypes.WinError()

	rootNames: dict[str, str] = {}
	rootDevInsts: dict[str, int] = {}
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
		if config.conf[CONF_SECTION][CONF_KEY_ONLY_REPORT_CONNECTED] and status != ConnectionStatus.CONNECTED:
			continue
		key = candidate.address or candidate.instanceId
		finalDevices[key] = BluetoothDevice(
			name=name,
			battery=candidate.battery,
			status=status,
			instanceId=candidate.instanceId,
			address=candidate.address,
		)
	return sorted(
		finalDevices.values(),
		key=lambda device: (int(device.status), device.name.lower()),
	)


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self) -> None:
		super().__init__()
		if BluetoothBatterySettingsPanel not in NVDASettingsDialog.categoryClasses:
			NVDASettingsDialog.categoryClasses.append(BluetoothBatterySettingsPanel)

	def terminate(self) -> None:
		try:
			NVDASettingsDialog.categoryClasses.remove(BluetoothBatterySettingsPanel)
		except ValueError:
			pass
		super().terminate()

	@script(
		# Translators: Description for the command to report Bluetooth battery levels.
		description=_("Reports the battery percentage of all local Bluetooth devices."),
		category=SCRIPT_CATEGORY,
		gesture="kb:NVDA+control+shift+b",
		speakOnDemand=True,
	)
	def script_reportBluetoothBattery(self, gesture: inputCore.InputGesture) -> None:
		try:
			devices = collectBluetoothBattery()
		except Exception:
			log.exception("Error reporting Bluetooth battery levels")
			# Translators: Message reported when Bluetooth battery detection fails.
			ui.message(_("Bluetooth battery detection failed."))
			return

		if not devices:
			# Translators: Message reported when no Bluetooth battery information is available.
			ui.message(_("No Bluetooth battery information is available."))
			return

		deviceReports: list[str] = []
		for device in devices:
			deviceReports.append(
				# Translators: Reported for each Bluetooth device.
				# {name} is the device name and {battery} is the battery percentage.
				_("{name} battery {battery} percent").format(name=device.name, battery=device.battery),
			)
		ui.message("; ".join(deviceReports))
