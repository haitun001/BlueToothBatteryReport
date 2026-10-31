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

## Settings

The settings are in the Bluetooth Battery Report category of the NVDA Settings dialog.

- **Only report connected devices**: Only announce devices that are currently connected. By default, connected, unknown and disconnected devices are announced.
- **Show connection type (Classic or LE)**: Announce whether each device uses Bluetooth Classic or Bluetooth Low Energy (LE).

## Contact

- Email: `haitun940624zx@gmail.com`
- QQ/WeChat: `476947039`
- Website: `https://www.zxrjy.net/`

## Supported NVDA Versions

- Minimum version: `2025.1.0`
- Tested up to: `2026.1.0`
