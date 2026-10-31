# PR 1: connection type label (Classic / LE)

## Branch name

    connection-type-label

## Commit message

    Add an option to announce the connection type (Classic or LE)

    Add a "Show connection type" setting, off by default. When enabled, the
    connection type is announced after the device name, for example
    "AULA-F75 (LE) battery 100 percent".

    The type is taken from the instance ID of the device's root node
    (BTHENUM is Classic, BTHLE and BTHLEDEVICE are LE), falling back to the
    node that reports the battery.

    Also document the settings in the readme.

## Pull request title

    Add an option to announce the connection type (Classic or LE)

## Pull request description

    Part of #3. As discussed there, I will send my changes as a series of small pull requests. This is the first and smallest one.

    ### What it does

    Adds a "Show connection type (Classic or LE)" checkbox to the Bluetooth Battery Report settings. It is off by default, so the spoken output does not change unless the user turns it on. When it is on, each device is announced with its connection type after the name:

    - `AULA-F75 (LE) battery 100 percent`
    - `FIIO BEATBOX (Classic) battery 60 percent`

    ### How it works

    - The type comes from the instance ID prefix of the device's root node (`BTHENUM\` is Classic, `BTHLE\` and `BTHLEDEVICE\` are LE). If a device has no root node, the node that reports the battery is used.
    - `BluetoothDevice` gets a new optional `connectionType` field (a small `ConnectionType` enum).
    - The readme now has a Settings section that describes this option and the existing "Only report connected devices" option.

    ### Not included

    - No translation files were changed. The new strings are untranslated for now.
    - No change to `changelog.md` or the version number. I am happy to add a line if you prefer.

    ### Testing

    - `ruff format --check` and `ruff check` pass with the repository configuration.
    - Tested manually on NVDA <FILL IN VERSION> with a Bluetooth Classic headset and a Bluetooth LE keyboard. <FILL IN AFTER TESTING>

## Manual test checklist (do this before opening the PR)

1. Build and install the add-on the way you usually do, then restart NVDA.
2. NVDA menu > Preferences > Settings > Bluetooth Battery Report. The new checkbox "Show connection type (Classic or LE)" must be there and unchecked.
3. With it unchecked, press NVDA+Control+Shift+B. The speech must be the same as before: `name battery N percent`.
4. Check the box, press OK, press NVDA+Control+Shift+B again. The headset must say (Classic) and the keyboard (LE).
5. Restart NVDA and check that the setting was kept.
6. Turn on "Only report connected devices" as well. Both options must work together.
7. Open the NVDA log (NVDA+F1 while NVDA runs) and check that there are no errors from the add-on.
