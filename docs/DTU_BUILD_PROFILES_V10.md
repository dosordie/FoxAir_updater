# LTE-DTU Build-Profile: V1.0 & V1.2

Stand: 2026-11-22. Zugehörig: [Issue #66](https://github.com/dosordie/FoxAir_updater/issues/66).

## Ziel und Freigabestatus

Der Updater erkennt **vor dem Upload eines OTA-Pakets** den tatsächlich installierten
`/data/phnixIot4G`-Build anhand der vollständigen SHA256. Der Aufdruck `82300225`
(Hardwarecode) oder ein DTU-Versionsstring sind keine belastbaren Hook-Identifikatoren.

| DTU-Software | Build-ID (Anfang) | Implementierungsstatus | OTA |
|---|---|---|---|
| V1.2 | `af4dcae1` | unveränderter validierter Hook/Supervisor | **freigegeben** |
| V1.0 | `d25ea21f` | eigener Hook/Supervisor; vollständiger OTA in VM bestätigt | **freigegeben** |
| andere | unbekannt | keine Profilzuordnung | **gesperrt** |

Beide erkannten DTU-Builds sind mit eigenen Hook-/Supervisor-Payloads im
Updater freigegeben. Unbekannte Dienst-Binärdateien bleiben gesperrt. Die
vollständigen SHA256/ELF-Build-IDs sind in `updater/dtu_ota/build_profiles.py`
fest hinterlegt. **Die Freigabe gilt für genau diese beiden Binär-Builds**,
nicht automatisch für andere V1.0-/V1.2-Varianten.

Der Branch enthält jetzt `phnix_ota_runtime_hook_v10` und
`dtu_ota_supervisor_v10.sh`. Die Paketvorbereitung wählt die Payload-Dateien
anhand des erkannten Profils. Die V1.0-Dateien verwenden die 18 dokumentierten
Einstiegskandidaten, den JSON-Puffer bei `0xA2160` und die V1.0-RAM-Adressen.
Das UART-Sendeflag wird als ein Byte gelesen. V1.0 sichert und restauriert
OTA_INFO ohne Statistikdatei. Die unvalidierten Cancel-Probe-Aktionen sind
aus der V1.0-Hookdatei entfernt.

Der vollständige V1.0-OTA wurde über den Windows-Updater mit autonomem Runner,
GDB-Hook und originalem PHNIX-V1.0-Dienst in der QEMU-Test-VM bis zur terminalen
Mainboardbestätigung erfolgreich getestet. Der V1.2-OTA-Start wurde ebenfalls
geprüft. Crash-/Resume-Szenarien wurden separat getestet. Die VM simuliert das
Mainboard; dieser Nachweis ist nicht mit einem Hardware-Flash-Test gleichzusetzen.

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
Für beide bekannten Builds lautet der Status **`supported`**. `prepare`
(Windows-GUI und Linux) wählt den passenden Hook/Supervisor automatisch aus und
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
`PASS` bestätigt nur die statische Dateiintegrität; die dynamischen OTA-Tests
sind eigenständig zu bewerten.

Optionaler, lesender RAM-Test mit **laufender V1.0-DTU**:

```sh
python3 devtools/phnix_ota_v10/probe_runtime.py --adb adb
```

Der Probe liest aus dem genau identifizierten V1.0-Prozess vier **je 1 Byte**
lange RAM-Felder (`dtu_run_step`, `dtu_sta`, `board_ota_step`,
`uart_send_flag`). Die Byte-Werte sind Diagnoseinformationen und ersetzen keinen OTA-Ende-Check.
Keine GDB-/OTA-Aktion.

## Dateien dieses Branches

- `updater/dtu_ota/build_profiles.py`: feste SHA-Pins, Build-ID-Metadaten und
  Freigabe-Flag für beide bekannten Dienst-Builds.
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

## Teststatus / Release

- V1.0: Vollständiger Windows-Updater-OTA über den autonomen Hook bis zur
  erfolgreichen Mainboard-Simulatorbestätigung (Status 5) bestätigt.
- V1.2: Originaldienst startet korrekt, OTA-Download mit korrekter MD5 und
  Beginn des Blocktransfers bestätigt; bestehender V1.2-Hook unverändert.
- Crash-/Resume-Szenarien: im Simulator getestet.
- Paketintegrität: SHA256-/Build-ID-Pinning und getrennte V1.0-/V1.2-
  Hook-/Supervisor-Auswahl erhalten. Unbekannte Builds bleiben gesperrt.

Die in der VM erzeugten Mainboardantworten sind keine tatsächliche
Flash-Erfolgskontrolle auf realer Hardware. Für Release-Betrieb gelten die
bekannten Hinweise in README.md.

Der Windows-Portable-/Setup-Build enthält sowohl V1.0- als auch V1.2-Payloads; der
Windows-Backend-Verifier prüft, dass sie tatsächlich im Artefakt landen.
Die produktiv nachgewiesene V1.2-Hookdatei
`updater/dtu_ota/payload/phnix_ota_runtime_hook` wurde **nicht editiert**.
Auch `dtu_ota_supervisor.sh` bleibt beim bewährten V1.2-Verhalten.

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
