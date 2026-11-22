"""Read-only and fail-closed DTU build-selection regression tests."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from updater.common.firmware_manifest import FirmwareManifest
from updater.dtu_ota.build_profiles import (
    V10, V12, DtuBuildIdentificationError, identify_adb, lookup_build,
)
from updater.dtu_ota.client import DtuOtaClient, RunnerClientError
from updater.dtu_ota.package import DtuOtaPackage, PackageError


class FakeBuildAdb:
    def __init__(self, service_hash: str):
        self.service_hash = service_hash
        self.commands = []
        self.pushed = []

    def shell(self, command, check=True):
        self.commands.append(command)
        if "active.lock/run_id" in command:
            return ""
        if "sha256sum '/data/phnixIot4G'" in command:
            return self.service_hash
        raise AssertionError("unexpected command before preflight: " + command)

    def push(self, local, remote):
        self.pushed.append((str(local), remote))


class DtuBuildProfileTests(unittest.TestCase):
    def test_recognize_two_exact_service_hashes(self):
        self.assertIs(lookup_build(V12.service_sha256.upper()), V12)
        self.assertIs(lookup_build(V10.service_sha256.upper()), V10)
        self.assertTrue(V12.ota_enabled)
        self.assertFalse(V10.ota_enabled)
        self.assertEqual(V10.hook_filename, "phnix_ota_runtime_hook_v10")
        self.assertTrue(V12.has_statistics_file)
        self.assertFalse(V10.has_statistics_file)

    def test_unknown_or_malformed_hash_fails_closed(self):
        for sha in ("", "V1.0", "0" * 64, "a" * 65, "g" * 64):
            with self.subTest(sha=sha), self.assertRaises(DtuBuildIdentificationError):
                lookup_build(sha)

    def test_identify_is_read_only_for_v10(self):
        adb = FakeBuildAdb(V10.service_sha256)
        profile = identify_adb(adb)
        self.assertIs(profile, V10)
        info = DtuOtaClient(adb).identify_build()
        self.assertEqual(info["dtu_software_version"], "V1.0")
        self.assertFalse(info["ota_enabled"])
        self.assertEqual(len(adb.commands), 2)
        self.assertFalse(adb.pushed)
        self.assertTrue(all("sha256sum" in cmd for cmd in adb.commands))

    @staticmethod
    def manifest(root: Path):
        firmware = root / "FW3.4.bin"
        firmware.write_bytes(b"test fixture")
        manifest = FirmwareManifest(
            schema="foxair-firmware-v1",
            firmware_file=firmware.name,
            software_code="82400644",
            display_version="V3.4",
            wire_version="0034",
            target_ssid="0063",
            size=len(firmware.read_bytes()),
            md5=hashlib.md5(firmware.read_bytes()).hexdigest().upper(),
            sha256=hashlib.sha256(firmware.read_bytes()).hexdigest().upper(),
            image_base="0x08050000",
        )
        path = root / "manifest.json"
        path.write_text(json.dumps(asdict(manifest)), encoding="utf-8")
        return firmware, path, manifest

    def test_v10_prepare_never_creates_any_remote_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            firmware, path, _ = self.manifest(root)
            adb = FakeBuildAdb(V10.service_sha256)
            client = DtuOtaClient(adb, source_root=root)
            with self.assertRaisesRegex(RunnerClientError, "V1.0 erkannt"):
                client.prepare(manifest_path=path, firmware_path=firmware)
            self.assertFalse(adb.pushed)
            self.assertEqual(len(adb.commands), 2)
            self.assertFalse(any("mkdir" in cmd for cmd in adb.commands))

    def test_unknown_build_never_creates_any_remote_run(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            firmware, path, _ = self.manifest(root)
            adb = FakeBuildAdb("f" * 64)
            client = DtuOtaClient(adb, source_root=root)
            with self.assertRaisesRegex(RunnerClientError, "Unbekannter"):
                client.prepare(manifest_path=path, firmware_path=firmware)
            self.assertFalse(adb.pushed)
            self.assertEqual(len(adb.commands), 2)

    def test_package_is_restricted_to_v12_build_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            firmware, _, manifest = self.manifest(root)
            hook = root / "runtime_hook"
            hook.write_bytes(b"#!/bin/sh\n")
            runner = root / "supervisor.sh"
            runner.write_bytes(b"#!/bin/sh\n")
            common = {
                "run_id": "test-1", "manifest": manifest, "firmware": firmware,
                "hook": hook, "supervisor": runner,
            }
            package = DtuOtaPackage.build(**common)
            self.assertEqual(package.value["expected_service_build_id"], V12.elf_build_id)
            with self.assertRaises(PackageError):
                DtuOtaPackage.build(
                    **common,
                    expected_service_sha256=V10.service_sha256,
                    expected_service_build_id=V10.elf_build_id,
                )
            with self.assertRaises(PackageError):
                DtuOtaPackage.build(
                    **common,
                    expected_service_sha256="f" * 64,
                    expected_service_build_id=V12.elf_build_id,
                )
            with self.assertRaises(PackageError):
                DtuOtaPackage.build(
                    **common,
                    expected_service_sha256=V12.service_sha256,
                    expected_service_build_id=V10.elf_build_id,
                )


if __name__ == "__main__":
    unittest.main()
