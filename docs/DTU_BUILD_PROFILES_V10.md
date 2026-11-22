# LTE-DTU Build-Profile: V1.0 & V1.2 (Entwicklungsbranch)

Stand: 2026-11-22. Zugehörig: [Issue #66](https://github.com/dosordie/FoxAir_updater/issues/66).

## Ziel und Freigabestatus

Der Updater erkennt **vor dem Upload eines OTA-Pakets** den tatsächlich installierten
`/data/phnixIot4G`-Build anhand der vollständigen SHA256. Der Aufdruck `82300225`
(Hardwarecode) oder ein DTU-Versionsstring sind keine belastbaren Hook-Identifikatoren.

| DTU-Software | Build-ID (Anfang) | Implementierungsstatus | OTA |
|---|---|---|---|
| V1.2 | `af4dcae1` | unveränderter validierter Hook/Supervisor | **freigegeben** |
| V1.0 | `d25ea21f` | statische Symbole / Signaturen, Laufzeit nicht validiert | **gesperrt** |
| andere | unbekannt | keine Profilzuordnung | **gesperrt** |

Wichtig: **V1.0 wird derzeit erkannt, aber es wird weder ein Updatepaket
hochgeladen noch GDB gestartet noch eine Datei auf der DTU verändert.**
Die vollen SHA256/ELF-Build-IDs sind als Konstanten in
`updater/dtu_ota/build_profiles.py` hinterlegt.

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
`dtu_software_version`, `elf_build_id`, `ota_enabled`, `ota_status` und
bei V1.0 den Sperrgrund. `prepare` (auch aus der Windows-GUI oder Linux)
ruft dieselbe Erkennung vor jedem Staging auf. Beim unbekannten Build und
bei V1.0 wird **vor** `mkdir`/`push` abgebrochen.

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
  Freigabe-Flag; V1.0 absichtlich nicht freigegeben.
- `updater/dtu_ota/client.py`: Build-Erkennung vor jedem Paketbau/Staging;
  V1.2 nutzt weiter exakt den bisherigen Runtime-Hook.
- `updater/dtu_ota/package.py`: Host-side-Paketfreigabe für nur den validierten
  V1.2-Build. Die unabhängige DTU-seitige V1.2-Allowlist bleibt erhalten.
- `updater/dtu_ota/cli.py`: read-only `identify`-Kommando.
- `updater/common/phnix_modem_info.py`: keine V1.2-RAM-Diagnose
  auf unbekannten oder V1.0-Originaldiensten.
- `devtools/phnix_ota_v10/`: Signaturdatei, Offline-Verifier und
  sichere Laufzeit-Beobachtung.
- `tests/test_dtu_build_profiles.py`,
  `tests/test_dtu_v10_static_checker.py` und angepasste Fake-ADB-Fixtures.

## Noch **nicht** freigegeben oder implementiert

Diese Punkte sind die nächsten Schritte aus Issue #66:

1. Eigenen V1.0-Hook erstellen, dessen Eintritts-, GDB-, C350/C36E/C357/C5A8-
   und Terminalpunkte **dynamisch** absichern; keine einfache Addition eines
   Adress-Offsets.
2. Versionierte DTU-Supervisor-Validierung inklusive Readiness-Adressen,
   unabhängiger Hook-/Service-Signaturfreigabe und unverändertem V1.2-Profil.
3. Bei V1.0 ist die Datei `/data/phnixIot_device_statisic` **nicht vorhanden**:
   OTA_INFO (220 Byte) versioniert sichern; fehlende Statistik nicht erstellen
   oder als Backupvoraussetzung fordern.
4. Host-/DTU-seitige Recovery-, Watchdog-, Resume-, Restore- und
   Crash-after-C5A8-Pfade in Test-VM und echter Hardware prüfen.
5. Erst nach erfolgreicher Testfreigabe: `ota_enabled=True` **und**
   passender V1.0-Hook, Paket-Profil-Allowlist sowie Supervisor-Freigabe
   gemeinsam in einem kontrollierten Review aktivieren.

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
