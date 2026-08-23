# Linux and Raspberry Pi host

The current laboratory workflow runs on Linux/Raspberry Pi and uses the shared
ADB transport from `updater/common`.

Planned responsibilities of this directory:

- locate system `adb`;
- install the build-specific runtime helper temporarily;
- provide service/udev instructions where required;
- package a command-line launcher after the laboratory interface stabilizes.

The current executable tools remain under `tools/phnix_ota/`.

Firmware metadata is shared with the future Windows frontend through
`updater/common/firmware_manifest.py`. Linux, Raspberry Pi and Windows must
consume the same hash-pinned manifest and must not duplicate or hard-code
firmware-specific values.
