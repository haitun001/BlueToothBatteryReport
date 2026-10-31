# BlueToothBatteryReport

`BlueToothBatteryReport` reports battery levels for local Bluetooth devices.

It supports multi-device battery reporting and sequentially announces all Bluetooth devices whose battery levels can be detected.

Devices are announced in this order: connected, unknown, disconnected.

## Hotkey

- `NVDA+Control+Shift+B`

## Spoken Format

When battery information is available, each device is announced as:

- `device name battery xx percent`

If **Show connection type** is enabled, the connection type is added after the device name:

- `device name (Classic) battery xx percent`
- `device name (LE) battery xx percent`

If **Show connection duration** is enabled, the time a connected device has been connected is added at the end:

- `device name battery xx percent (connected 1 hr 25 min)`

## Settings

The settings are in the Bluetooth Battery Report category of the NVDA Settings dialog.

- **Report connected devices**: Announce devices that are currently connected.
- **Report unknown status devices**: Announce devices whose connection status cannot be determined.
- **Report disconnected devices**: Announce paired devices that are not connected.
- **Show connection type (Classic or LE)**: Announce whether each device uses Bluetooth Classic or Bluetooth Low Energy (LE).
- **Show connection duration**: Announce for how long a connected device has been connected, as reported by Windows. Windows only provides this for Bluetooth Classic devices, not for Bluetooth LE devices.

The three report options are enabled by default. Earlier versions had a single "Only report connected devices" option. If it was enabled, the unknown and disconnected options are turned off automatically.

## Contact

- Email: `haitun940624zx@gmail.com`
- QQ/WeChat: `476947039`
- Website: `https://www.zxrjy.net/`

## Supported NVDA Versions

- Minimum version: `2025.1.0`
- Tested up to: `2026.1.0`
