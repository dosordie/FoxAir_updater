# Planned Windows updater

This directory reserves the Windows frontend. No Windows updater or GUI is
implemented yet.

## Target workflow

```text
Windows PC
  -> USB cable
  -> ADB / adb.exe
  -> original PHNIX LTE modem
  -> original phnixIot4G service
  -> RS485
  -> heat-pump mainboard
```

The user should later be able to connect the LTE modem via USB, select a
firmware file and run preflight, update, status and recovery without a
Raspberry Pi.

## Planned implementation

- Python 3 application, packaged as a signed standalone executable;
- shared `updater/common` validation and state-machine code;
- selected or bundled, version-pinned `adb.exe`;
- automatic ADB device discovery with explicit selection if multiple devices
  are connected;
- driver/setup diagnostics without silently installing drivers;
- structured log export and state backup in the user's application-data
  directory;
- CLI first, optional GUI only after the live protocol is stable;
- no duplicated safety logic in the GUI.

## Packaging boundary

Windows-specific code may handle executable discovery, USB/driver guidance,
paths, elevation messages and packaging. It must call the same common updater
core used on Linux. The modem-side paths such as `/data/phnix_local_ota` remain
unchanged because they belong to the Linux LTE modem, not to the Windows host.

## Explicitly not built yet

- no GUI;
- no installer;
- no bundled ADB binary;
- no driver package;
- no live update button.

These pieces wait until cancel/recovery and the first controlled live transfer
are validated.
