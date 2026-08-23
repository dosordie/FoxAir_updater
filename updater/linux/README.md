# Linux and Raspberry Pi host

The current laboratory workflow runs on Linux/Raspberry Pi and uses the shared
ADB transport from `updater/common`.

Planned responsibilities of this directory:

- locate system `adb`;
- install the build-specific runtime helper temporarily;
- provide service/udev instructions where required;
- package a command-line launcher after the laboratory interface stabilizes.

The current executable tools remain under `tools/phnix_ota/`.
