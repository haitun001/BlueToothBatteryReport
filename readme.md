# BlueToothBatteryReport

`BlueToothBatteryReport` reports battery levels for local Bluetooth devices.

It supports multi-device battery reporting and sequentially announces all Bluetooth devices whose battery levels can be detected.

Devices are announced in this order: connected, unknown, disconnected.

## Hotkey

- `NVDA+Control+Shift+B`

The command that opens the battery statistics (see below) has no gesture by default. You can assign one in NVDA Input Gestures dialog, in the Bluetooth Battery Report category.

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
- **Measure total connection time between recharges**: Measure for how long each device is connected between two recharges, in the background. This is used for the connection duration and for the statistics. It is disabled by default. See below.
- **View battery statistics**: Open the window with the battery statistics. It also shows the data that was measured before.
- **Enable low battery alert**: Give an alert when the battery of a connected device is low (disabled by default). See below.
- **Low battery threshold**: The battery percentage at or below which the alert is given, from 5 to 50 (20 by default).
- **Alert sound**: Choose a beep, or a custom .wav file that you select with the **Browse** button. If the file cannot be played, a beep is used.

The three report options are enabled by default. Earlier versions had a single "Only report connected devices" option. If it was enabled, the unknown and disconnected options are turned off automatically.

## Connection Time and Statistics

If **Measure total connection time between recharges** is enabled, the add-on checks the devices in the background every 5 minutes and keeps, for each device, the total time it was connected since it was last recharged. While **Show connection duration** is also enabled, this total is announced instead of the time reported by Windows, for example `device name battery xx percent (connected 5 hr 20 min)`. It also works for Bluetooth LE devices, for which Windows reports no connection time.

- A device is measured from the first time the add-on sees it, at any battery level. The first cycle of a device can therefore be shorter than the real one.
- Only the time the device is seen as connected is counted. The total is kept while the device is disconnected and when NVDA restarts. Gaps of more than 15 minutes between two checks, for example while the computer sleeps, are not counted.
- A recharge is detected when the battery level is at least 15 percentage points above the lowest level of the current cycle. This also works for devices that never reach 100%. The finished cycle is saved and counting restarts from zero. Time is not counted while the battery level is rising.
- For Bluetooth Classic devices, if Windows reports a longer connection than the add-on has counted, the longer time is used.
- Devices are identified by their name. Two devices with the same name share the same record.

The data is saved in `blueToothBatteryReport_usage.json` in the NVDA user configuration folder, with at most 500 finished cycles per device. Delete the file while NVDA is not running to start over.

### Battery statistics

**View battery statistics** in the settings opens a window with two lists. Devices are listed in the same order as in the spoken report: connected, unknown, disconnected, then by name. Devices that were not in the latest check come last.

The summary list has one row per device: its status, the number of finished cycles, the average, shortest and longest connected time, the estimated runtime on a full charge, how often it is recharged, when it was last recharged, the trend (the latest 3 cycles compared with the earlier ones, from 4 cycles on) and the estimated time left at the usual drain rate.

The cycle list has one row per cycle, newest first, with the cycle in progress at the top of each device: the cycle number, the connected time, the battery level at the start and the lowest level, the estimated runtime on a full charge and when the cycle ended.

In both lists, press Control+C to copy the current row, or Control+Shift+C to copy everything about the current device (its summary and all of its cycles). The same commands are in the context menu of the lists. The text is made of "Header: value" pairs.

Estimates ignore cycles that used fewer than 10 battery points, because battery levels are often reported in coarse steps. An empty cell means that there is not enough data yet.

## Low Battery Alert

When the low battery alert is enabled, the add-on checks the battery levels in the background every 5 minutes. If the battery of a connected device is at or below the threshold, the alert sound is played and a warning dialog is shown. Each device only triggers one alert until its battery is above the threshold again.

## Contact

- Email: `haitun940624zx@gmail.com`
- QQ/WeChat: `476947039`
- Website: `https://www.zxrjy.net/`

## Supported NVDA Versions

- Minimum version: `2025.1.0`
- Tested up to: `2026.1.0`
