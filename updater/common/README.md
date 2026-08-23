# Shared updater core

This package contains host-independent Python code. It must remain usable from
Linux, Raspberry Pi and a future Windows application.

Current components:

- `adb_transport.py`: binary-safe subprocess wrapper for `adb` or `adb.exe`.
- `phnix_frames.py`: streaming PHNIX frame decoder and fail-closed OTA run
  tracker, shared by Linux/VM tooling and a future Windows frontend.

Rules for this layer:

- no hard-coded Linux device paths on the host;
- no shell-specific quoting for host commands;
- firmware validation and state-machine decisions belong here;
- UI code may consume structured status events but must not duplicate safety
  decisions;
- the LTE modem remains the ADB target and may still use its own Linux paths.
