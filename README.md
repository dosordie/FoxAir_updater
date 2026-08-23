# FoxAir Updater

Firmware research, reverse engineering and update tooling for FoxAir / PHNIX heat-pump systems.

This repository intentionally separates firmware-related work from [`FoxAir_Control`](https://github.com/dosordie/FoxAir_Control), which remains focused on the FoxAir Control application and normal operational control/diagnostics.

## Repository layout

```text
FoxAir_updater/
├─ docs/
│  ├─ mainboard/            # Mainboard firmware analysis (e.g. V3.3, IAP, flash/recovery)
│  ├─ ota/                  # OTA protocol, state machine, transfer and safety analysis
│  └─ modem/                # PHNIX LTE modem firmware/runtime reverse engineering
├─ firmware_images/
│  ├─ mainboard/            # Original/read-out mainboard firmware images
│  ├─ modem/                # LTE modem firmware images / OTA payloads
│  └─ display/              # HMI/DGUS/display firmware images where relevant
├─ tools/
│  ├─ common/               # Platform-independent updater/protocol code
│  ├─ linux/                # Linux/Raspberry Pi updater and lab tooling
│  └─ windows/              # Windows updater/launcher tooling
├─ tests/                   # Simulator, protocol and regression tests
└─ samples/                 # Captures, frame examples and sanitized test material
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

The updater should keep protocol/firmware logic in `tools/common/` wherever possible. Windows- and Linux-specific launchers, serial-port discovery, driver/setup instructions and packaging belong in their respective `tools/windows/` and `tools/linux/` directories.

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
