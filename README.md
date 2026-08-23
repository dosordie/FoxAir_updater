# FoxAir Updater

Firmware research, reverse engineering and update tooling for FoxAir / PHNIX heat-pump systems.

This repository intentionally separates firmware-related work from [`FoxAir_Control`](https://github.com/dosordie/FoxAir_Control), which remains focused on the FoxAir Control application and normal operational control/diagnostics.

## Repository layout

```text
FoxAir_updater/
├─ docs/
│  ├─ reverse_engineering/  # Mainboard, OTA and LTE modem analysis
│  └─ HowTo/                # Operator-facing procedures
├─ firmware_images/
│  ├─ mainboard/            # Original/read-out mainboard firmware images
│  ├─ modem/                # LTE modem firmware images / OTA payloads
│  └─ display/              # HMI/DGUS/display firmware images where relevant
├─ updater/
│  ├─ common/               # Shared Python transport/core used by every host OS
│  ├─ linux/                # Linux/Raspberry Pi integration
│  └─ windows/              # Windows design; no Windows application yet
├─ tools/phnix_ota/         # Current guarded launcher, runtime hook and VM simulator
├─ devtools/                # Direct RS485 sender, board simulator and offline lab
└─ tests/                   # Protocol, controller and simulator regression tests
```

## Firmware images

Binary firmware dumps belong below `firmware_images/` and should be kept separate from source code and documentation. Prefer a subdirectory per device/firmware version, for example:

```text
firmware_images/mainboard/v3.3/
firmware_images/modem/phnixIot4G/
```

For every image, add a small `README.md` or metadata file containing at least source/device, observed version, file size, SHA-256 hash, acquisition method and whether the image is original, extracted or modified.

Do not overwrite known-good originals. Modified/test images should use clearly different filenames or a dedicated subdirectory.

## Platform split

The updater keeps host-independent transport and protocol logic in
`updater/common/`. Linux/Raspberry-Pi integration belongs in `updater/linux/`.
The future Windows frontend belongs in `updater/windows/` and will reuse the
same common Python code with a selected or bundled `adb.exe`.

The currently executable guarded laboratory launcher remains in
`tools/phnix_ota/` until its interfaces and live recovery path are stable.

## Current safety boundary

The VM simulator supports the complete cancel/recovery contract and the
C350/C357 handshake up to a hard stop before C5A8. The early C36A/C36C cancel
and return to terminal Step 12 have been validated once on the real build.

The new `pre-c5a8-vm-test` remains marker-locked to the simulator. A real
C350/C357 test and every C5A8 firmware-writing test require a separate explicit
approval and are not enabled by the VM command.

## Scope

Included here:
- firmware dumps and metadata
- firmware reverse engineering
- PHNIX modem firmware/runtime reverse engineering when relevant to update transport
- OTA/IAP protocol analysis
- firmware update, recovery and validation tooling
- simulators and lab/test scripts

Not included here:
- FoxAir Control GUI/application code
- normal end-user control logic
- general Modbus tooling that is independent of firmware/update development
