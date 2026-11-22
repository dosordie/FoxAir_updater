# LTE-DTU Build-Profile: V1.0 & V1.2 (Entwicklungsbranch)

Stand: 2026-11-22. Zugehörig: [Issue #66](https://github.com/dosordie/FoxAir_updater/issues/66).

## Ziel und Freigabestatus

Der Updater erkennt **vor dem Upload eines OTA-Pakets** den tatsächlich installierten
`/data/phnixIot4G`-Build anhand der vollständigen SHA256. Der Aufdruck `82300225`
(Hardwarecode) oder ein DTU-Versionsstring sind keine belastbaren Hook-Identifikatoren.

| DTU-Software | Build-ID (Anfang) | Implementierungsstatus | OTA |
|---|---|---|---|
| V1.2 | `af4dcae1` | unveränderter validierter Hook/Supervisor | **freigegeben** |
| V1.0 | `d25ea21f` | separater Hook/Supervisor eingebunden; VM-End-to-End-Test ausstehend | **experimentell aktiviert (nur Entwicklungsbranch)** |
| andere | unbekannt | keine Profilzuordnung | **gesperrt** |

**Wichtig: Die V1.0-Sperre ist nur in diesem Entwicklungsbranch aufgehoben.**
Ein echter V1.0-Firmwaretransfer kann aus der Windows-GUI gestartet werden.
Dieser Build ist ausschließlich für die isolierte Test-VM vorgesehen; GDB- und
Crash/Resume-Semantik sind nicht abschließend validiert. **Nicht auf Produktivgeräte
anwenden oder als Stable veröffentlichen.** `main` bleibt unverändert.
Die vollständigen SHA256/ELF-Build-IDs sind in
`updater/dtu_ota/build_profiles.py` fest hinterlegt.

Der Branch enthält jetzt `phnix_ota_runtime_hook_v10` und
`dtu_ota_supervisor_v10.sh`. Die Paketvorbereitung wählt die Payload-Dateien
anhand des erkannten Profils. Die V1.0-Dateien verwenden die 18 dokumentierten
Einstiegskandidaten, den JSON-Puffer bei `0xA2160` und die V1.0-RAM-Adressen.
Das UART-Sendeflag wird als ein Byte gelesen. V1.0 sichert und restauriert
OTA_INFO ohne Statistikdatei. Die unvalidierten Cancel-Probe-Aktionen sind
aus der V1.0-Hookdatei entfernt.

Der experimentelle V1.0-Hook kann jetzt direkt vom Windows-Build über die
normale Vorprüfung und den autonomen Runner gegen die VM getestet werden.
**Der bisherige MQTT-Simulatortest belegt nicht, dass diese Sequenz funktioniert.**
Die Validierung des tatsächlichen Runner-/GDB-Einstiegs und der Crash-Recovery
ist noch ausdrücklich offen.

## Benutzerprüfung: völlig read-only

Auf Windows mit installiertem ADB, Linux oder über den Remote-ADB-Server:

```sh
python3 updater/dtu_ota/cli.py --adb adb identify
```

Mit Remote-ADB:

```sh
python3 updater/dtu_ota/cli.py --adb adb \
    --adb-server-socket tcp:RPI_IP:5038 identify
```

`identify` liest ausschließlich SHA256 der Originaldatei. Das Ergebnis liefert
`dtu_software_version`, `elf_build_id`, `ota_enabled` und `ota_status`.
Für V1.0 lautet der Status **`experimental-vm-test`**. `prepare` (Windows-GUI
und Linux) wählt den separaten V1.0-Hook/Supervisor automatisch aus und
prüft deren Integrität. Unbekannte Builds werden weiterhin **vor** dem
Staging abgewiesen.

**Keine Aussage über den Mainboard-Firmwarestand:** V1.0/V1.2 betreffen die
LTE-DTU-Software `phnixIot4G`, nicht die Mainboard-Firmware V3.4/V3.5.

## Offlineprüfung der V1.0-Originaldatei

Der **rein statische** Checker benötigt die Originaldatei lokal, nicht im Repo:

```sh
python3 devtools/phnix_ota_v10/verify_static.py PFAD_ZU/phnixIot4G
```

Er vergleicht exakte SHA256, Bytezahl, ELF-Build-ID und 18 ARM-GDB-Stellen.
`PASS` ist **keine** Bestätigung für funktionierende GDB-Injektion/OTA-Resume.

Optionaler, lesender RAM-Test mit **laufender V1.0-DTU**:

```sh
python3 devtools/phnix_ota_v10/probe_runtime.py --adb adb
```

Der Probe liest aus dem genau identifizierten V1.0-Prozess vier **je 1 Byte**
lange RAM-Felder (`dtu_run_step`, `dtu_sta`, `board_ota_step`,
`uart_send_flag`). Die angenommene `11/4/12/0`-Idle-Semantik stammt
bisher aus V1.2 und ist **für V1.0 noch eine Hypothese**. Keine GDB-/OTA-Aktion.

## Dateien dieses Branches

- `updater/dtu_ota/build_profiles.py`: feste SHA-Pins, Build-ID-Metadaten und
  Freigabe-Flag; V1.0 nur in diesem Featurebranch für VM-Tests freigegeben.
- `updater/dtu_ota/client.py`: automatische profilspezifische Hook-/Supervisor-
  Auswahl vor jedem Paketbau/Staging; V1.2 bleibt auf dem bisherigen Hook.
- `updater/dtu_ota/package.py`: profilspezifische Freigabe für V1.0/V1.2;
  V1.0-Pakete verlangen die korrekten getrennten Payload-Dateinamen.
  Der V1.0-Supervisor kontrolliert Build-ID und vollständige SHA256 unabhängig.
- `updater/dtu_ota/cli.py`: read-only `identify`-Kommando.
- `updater/common/phnix_modem_info.py`: keine V1.2-RAM-Diagnose
  auf unbekannten oder V1.0-Originaldiensten.
- `devtools/phnix_ota_v10/`: Signaturdatei, Offline-Verifier und
  sichere Laufzeit-Beobachtung.
- `tests/test_dtu_build_profiles.py`,
  `tests/test_dtu_v10_static_checker.py` und angepasste Fake-ADB-Fixtures.

## Noch **nicht** validiert / produktiv freigegeben

Diese Punkte sind die nächsten Schritte aus Issue #66:

1. Der V1.0-Hook ist implementiert, aber C350/C36E/C357/C5A8 und die
   terminalen Breakpoints müssen gegen den **vollständigen autonomen
   Runner/ADB-/QEMU-Pfad** getestet werden.
2. Der neue Supervisor besitzt die eigenen V1.0-Readiness-Adressen und
   Allowlist. Dynamische Prüfung der Neustarts und Zustandsübergänge ausstehend.
3. V1.0 hat keine Statistikdatei; das getrennte OTA_INFO-Backup/Restore
   (220 Byte) im V1.0-Pfad muss noch dynamisch bestätigt werden.
4. Host-/DTU-seitige Recovery-, Watchdog-, Resume-, Restore- und
   Crash-after-C5A8-Pfade in Test-VM durchspielen.
5. **Erst nach bestandenen Tests** V1.0 auch für reale Geräte freigeben,
   in `main` übernehmen und als neues Stable-Release veröffentlichen.

Der Windows-Portable-/Setup-Build enthält beide V1.0-Payloads; der
Windows-Backend-Verifier prüft, dass sie tatsächlich im Artefakt landen.
Die produktiv nachgewiesene V1.2-Hookdatei
`updater/dtu_ota/payload/phnix_ota_runtime_hook` wurde **nicht editiert**.
Auch `dtu_ota_supervisor.sh` bleibt zunächst exakt beim bewährten V1.2-Verhalten.

## Validierung / Testanweisung

```sh
python3 -m unittest discover -s tests -p "test_dtu_*.py"
python3 -m unittest discover -s tests -p "test_phnix_modem_info.py"
python3 -m unittest discover -s tests -p "test_*.py"
sh -n updater/dtu_ota/payload/phnix_ota_runtime_hook
sh -n updater/dtu_ota/payload/dtu_ota_supervisor.sh
```

Der optionale reale ELF-Test der Signaturen wird nur mit
`FOXAIR_DTU_V10_LOCAL_BINARY=/pfad/phnixIot4G` ausgeführt. Diese Binärdatei,
IMEI, SIM-Daten und alle anderen personenbezogenen DTU-Daten gehören **nicht**
in das öffentliche Repository oder GitHub-Artefakte.
