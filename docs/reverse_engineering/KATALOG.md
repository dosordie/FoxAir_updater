# FoxAir / PHNIX Reverse-Engineering-Katalog

Stand: 5. September 2026

Dieser Katalog gilt **ausschließlich für Dateien in `docs/reverse_engineering/`**.

Er dient zwei Zielen:

1. Menschen sollen schnell das passende Reverse-Engineering-Dokument finden.
2. KI-/Assistenzsysteme sollen vorhandene Erkenntnisse zuerst gezielt nachschlagen, bevor Firmware erneut vollständig disassembliert oder bereits geklärte Zusammenhänge neu rekonstruiert werden.

Die bestehende [`README.md`](README.md) bleibt davon getrennt und wird durch diesen Katalog **nicht ersetzt**.

---

# 1. Empfohlene Lookup-Reihenfolge für KI / Analyse

Bei technischen Fragen zum FoxAir-/PHNIX-System möglichst zuerst so vorgehen:

```text
1. KATALOG.md lesen
2. Thema + Firmwarestand bestimmen
3. SUPERSEDED- und Known-Corrections-Matrix prüfen
4. 1–3 passende kanonische/primäre Dokumente lesen
5. dortige Querverweise verfolgen
6. erst wenn die Dokumentation fehlt, widersprüchlich oder unvollständig ist:
   Binary / Disassembly / Live-Mitschnitt erneut analysieren
7. neue belastbare Erkenntnisse in einem bestehenden Spezialdokument
   oder einem neuen versionsgebundenen Dokument festhalten
8. KATALOG.md anschließend ergänzen
```

## Wichtige Prioritätsregeln

- **Firmwareadressen sind versionsgebunden.** Eine V3.3-RAM-/Codeadresse darf nicht ungeprüft auf V3.4 übertragen werden.
- Bei einer **V3.4-Frage** zuerst vorhandene V3.4-Dokumente lesen; V3.3-Dokumente dienen dann nur als Architektur-/Protokollreferenz.
- **Live bestätigte Ergebnisse** haben Vorrang vor älteren statischen Hypothesen oder Testplänen.
- Ein als **SUPERSEDED** markiertes Dokument nicht als Primärquelle verwenden.
- Bei einer **BASIS**-Datei zuerst prüfen, ob spätere Spezialdokumente einzelne Aussagen korrigiert haben.
- Für OTA-Fragen zuerst aktuelle Kurzreferenz, State-Machine und Live-Ergebnis lesen; alte Labor-/Probe-Dokumente nur bei Detailfragen.
- Für Registerfragen zuerst Modbus-Gesamtkatalog und die passenden Parameter-/Status-Audits verwenden.
- Bei Verdichterfragen Mainboard-Regelung und **Unit `0x01` Inverterboard** als getrennte Boards behandeln.

---

# 2. Statuskennzeichnung

| Status | Bedeutung |
|---|---|
| **KANONISCH** | bevorzugte aktuelle Referenz für das jeweilige Thema |
| **VERSIONIERT** | belastbare technische Analyse, aber explizit an einen Firmwarestand gebunden |
| **LIVE** | auf realer Hardware / realem Verkehr bestätigt |
| **BASIS** | wichtige frühe Gesamt-/Grundlagenanalyse; spätere Spezialdokumente können Details korrigieren |
| **ARBEITSSTAND** | Analyse-/Teststand; kann durch neuere Dokumente überholt sein |
| **HISTORISCH** | bewusst erhaltener Entwicklungs-/Teststand, nicht als aktueller Gesamtstatus lesen |
| **SUPERSEDED** | durch eine andere Datei ersetzt; nur Redirect, Historie oder alte Verweise |
| **DATENSATZ** | CSV / strukturierte Begleitdaten |

---

# 3. Maschinenlesbarer Prioritätsindex

Dieser Block ist bewusst redundant zur Menschenansicht und soll KI-/Tooling-Lookups vereinfachen.

```yaml
catalog_schema: 1
scope: docs/reverse_engineering
lookup_policy:
  first: KATALOG.md
  prefer: [KANONISCH, LIVE, VERSIONIERT]
  avoid_as_primary: [SUPERSEDED, HISTORISCH, ARBEITSSTAND]
  firmware_addresses_are_version_specific: true

superseded:
  FW3.3-HYD61-EXTERNER-DURCHFLUSS.md:
    replaced_by:
      - FW3.3-PUMPEN-EXTERNER-DURCHFLUSS.md

  FW3.3-MODBUS-KORREKTUREN-FOXAIR_CONTROL.md:
    replaced_by:
      - FW3.3-MODBUS-FINALE-DELTA-FOXAIR_CONTROL.md
      - FW3.3-MODBUS-GESAMTKATALOG.md
      - FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md
      - FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md

known_corrections:
  PHNIX_phnixIot4G_RE.md:
    mqtt_transport:
      old_statement: plain_or_unencrypted_TCP_1883
      current_result: MQTT_3.1.1_over_TLS_1.2_on_TCP_port_1883
      current_sources:
        - PHNIX_phnixIot4G_mqtt_runtime_corrections.md
        - PHNIX_phnixIot4G_tls_mqtt_trust.md
    role: BASIS

  PHNIX_phnixIot4G_mqtt_connect_exact.md:
    role: static_detail_with_later_runtime_corrections
    effective_keepalive_seconds: 180
    requested_keepalive_ms: 300000
    partner_module_ids: present_in_this_build
    current_source:
      - PHNIX_phnixIot4G_mqtt_runtime_corrections.md

  PHNIX_phnixIot4G_tls_mqtt_trust.md:
    requested_keepalive_ms: 300000
    effective_keepalive_seconds: 180
    current_source:
      - PHNIX_phnixIot4G_mqtt_runtime_corrections.md

  Warmlink_LTE_DTU_ReverseEngineering.md:
    mqtt_transport_clarification: MQTT_3.1.1_over_TLS_1.2_on_TCP_port_1883
    role: BASIS_HARDWARE_SYSTEM_OVERVIEW
```

---

# 4. Schnell-Router nach Thema

| Frage / Suchbegriffe | Zuerst lesen | Danach |
|---|---|---|
| **Umwälzpumpe, Wasserpumpe, PWM, Pumpendrehzahl, Durchfluss, UPM4L, P08, A40, D22** | [`FW3.3-PUMPEN-PWM-REGELUNG.md`](FW3.3-PUMPEN-PWM-REGELUNG.md) | `DURCHFLUSS-VERWENDUNG`, `100-PROZENT`, `UPM4L`, `P08` |
| **externer Durchfluss, H30=3, HYD61, Unit 0x61, 2047/2048** | [`FW3.3-PUMPEN-EXTERNER-DURCHFLUSS.md`](FW3.3-PUMPEN-EXTERNER-DURCHFLUSS.md) | Pumpen-PWM / interne Boardarchitektur |
| **Verdichter, Kompressor, Inverter, Hz, Soll-/Istfrequenz, Unit 0x01, 1999/2000, 2071/2072** | [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md) | [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md), Frequenzlimits |
| **WW ↔ Heizen, Warmwasserumschaltung, Verdichterstopp, 3-Wege-Ventil, H32, FA7/FA8** | [`FW3.4-WW-HEIZEN-UMSCHALTUNG-VERDICHTER.md`](FW3.4-WW-HEIZEN-UMSCHALTUNG-VERDICHTER.md) | V3.3 Inverter-/Boardarchitektur |
| **Ölrückführung / Oil Return** | [`FW3.3-OELRUECKFUEHRUNG.md`](FW3.3-OELRUECKFUEHRUNG.md) | Kompressor-/Inverteransteuerung |
| **EEV / EVV / elektronisches Expansionsventil / Überhitzung** | [`FW3.3-EEV-SMART-REGELUNG.md`](FW3.3-EEV-SMART-REGELUNG.md) | Gesamt-Erkenntnisse |
| **Lüfter / Fan / RPM / Fan Driver** | [`FW3.3-LUEFTERREGELUNG.md`](FW3.3-LUEFTERREGELUNG.md) | Unit-1-Inverterprotokoll / interne Boardarchitektur |
| **Modbus Register allgemein** | [`FW3.3-MODBUS-GESAMTKATALOG.md`](FW3.3-MODBUS-GESAMTKATALOG.md) | Parameter-/Status-/Service-Audits |
| **Änderungen für FoxAir_Control** | [`FW3.3-MODBUS-FINALE-DELTA-FOXAIR_CONTROL.md`](FW3.3-MODBUS-FINALE-DELTA-FOXAIR_CONTROL.md) | Status-/Parameter-Audits; `modbus_v3.3_final_delta.csv` |
| **Parameter 1001–1540, H/A/D/C/P-Parameter** | [`FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md`](FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md) | Gesamtkatalog |
| **Status 2001–2180, Livewerte, Fehler, Ausgänge** | [`FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md`](FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md) | Gesamtkatalog / Service Audit |
| **interner Modbus, Boardadressen, Slave Units, RS485/UART** | [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md) | UART-Hardware / Unit-1-Protokoll |
| **Warmlink externer Modbus / 0x63 Dispatcher** | [`FW3.3-WARMLINK-0x63-MODBUS-DISPATCHER.md`](FW3.3-WARMLINK-0x63-MODBUS-DISPATCHER.md) | Modbus-Katalog |
| **SG Ready / PV / Register 8801** | [`FW3.3-SG-READY-MODBUS-8801.md`](FW3.3-SG-READY-MODBUS-8801.md) | Parameter-Audit |
| **Firmwarefamilien / Softwarecodes / 82400644 / Versionen** | [`PHNIX_FIRMWAREFAMILIEN_SOFTWARECODES.md`](PHNIX_FIRMWAREFAMILIEN_SOFTWARECODES.md) | V3.3-Erkenntnisse / V3.3→V3.4 Live Update |
| **Mainboard OTA allgemein, C350, C36E, C5A8, C544** | [`PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md`](PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md) | Board OTA State Machine / Completion / Live Update |
| **V3.3 → V3.4 realer Updateablauf** | [`PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md) | OTA-Kurzreferenz |
| **DTU / phnixIot4G Gesamtarchitektur** | [`PHNIX_phnixIot4G_program_map.md`](PHNIX_phnixIot4G_program_map.md) | `PHNIX_phnixIot4G_RE.md` als BASIS + Non-OTA Architecture |
| **MQTT Datenpfad / MQTT↔RS485 Bridge / Topics** | [`PHNIX_phnixIot4G_normal_mqtt_bridge.md`](PHNIX_phnixIot4G_normal_mqtt_bridge.md) | Cloud Telemetry Commands |
| **MQTT CONNECT / TLS / Auth / Keepalive / Client-ID** | [`PHNIX_phnixIot4G_mqtt_runtime_corrections.md`](PHNIX_phnixIot4G_mqtt_runtime_corrections.md) | TLS Trust, MQTT Connect Exact (statische Detailquelle) |
| **LTE / QMI / NAS / Modem** | [`PHNIX_phnixIot4G_qmi_nas.md`](PHNIX_phnixIot4G_qmi_nas.md) | QMI Init/Data Path/Followup, `lte_verbindung.md` |
| **DTU ↔ Mainboard RS485** | [`PHNIX_phnixIot4G_identity_rs485.md`](PHNIX_phnixIot4G_identity_rs485.md) | RS485 Runtime / OTA RS485 Frames |
| **Watchdog / Reboot / Reset Counter / Offline 1800 s** | [`PHNIX_phnixIot4G_watchdogs_reset_counters.md`](PHNIX_phnixIot4G_watchdogs_reset_counters.md) | Runtime Counters / Security |
| **DTU OTA Runner / autonomer Ablauf** | [`PHNIX_DTU_OTA_RUNNER_STATUS_2026-09-02.md`](PHNIX_DTU_OTA_RUNNER_STATUS_2026-09-02.md) | Stage1 / Autonomous Live Test |

---

# 5. Hauptplatine – Gesamtübersicht und Firmwarestände

## Primärdokumente

| Dokument | Status | Firmware | Inhalt / Keywords |
|---|---|---|---|
| [`FW3.3-ERKENNTNISSE.md`](FW3.3-ERKENNTNISSE.md) | **VERSIONIERT** | V3.3 | breite Mainboard-Gesamtübersicht; Spezialdokumente bei Detailfragen bevorzugen |
| [`PHNIX_FIRMWAREFAMILIEN_SOFTWARECODES.md`](PHNIX_FIRMWAREFAMILIEN_SOFTWARECODES.md) | **KANONISCH** | mehrere | Firmwarefamilien, Softwarecodes, Versionszuordnung |
| [`PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md) | **LIVE** | V3.3→V3.4 | realer Updatebeweis, Version 0033 → 0034 |

## Spezialdokument

- [`FW3.3-IAP-COPY-SPRUNGPFAD-KORREKTUR.md`](FW3.3-IAP-COPY-SPRUNGPFAD-KORREKTUR.md) — **VERSIONIERT**; korrigierte Imagebasis/IAP-/Copy-/Sprungpfade.

---

# 6. Verdichter / Inverter / Frequenzregelung

## Primärdokumente

- [`FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md`](FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md) — **VERSIONIERT**, V3.3. End-to-End-Pfad Mainboard → Sollfrequenz → Unit `0x01` → Inverter → Rückmeldung.
- [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md) — **VERSIONIERT**, V3.3. FC10 `1999ff` / FC03 `2099ff`, Remote-Register des Leistungsboards.
- [`FW3.4-WW-HEIZEN-UMSCHALTUNG-VERDICHTER.md`](FW3.4-WW-HEIZEN-UMSCHALTUNG-VERDICHTER.md) — **VERSIONIERT**, V3.4. WW↔Heizen-State-Machine, FA7/FA8, Verdichter-Stop, Soft-Stop, H32-Abgrenzung.

## Ergänzende Dokumente

- [`FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md`](FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md) — Frequenzlimits und Register 2139.
- [`FW3.3-OELRUECKFUEHRUNG.md`](FW3.3-OELRUECKFUEHRUNG.md) — Ölrückführungs-State-Machine und Sonderfrequenz.
- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md) — Trennung Regelmainboard / Leistungsboard und weitere interne Units.

### Suchbegriffe

```text
Verdichter Kompressor compressor inverter Unit1 Unit 0x01
1999 2000 2071 2072 Hz Frequenz frequency target actual
Soft-Stop FA7 FA8 Warmwasser WW DHW Heizen heating H32
```

---

# 7. Hydraulik / Umwälzpumpe / Durchfluss

## Primärdokument

- [`FW3.3-PUMPEN-PWM-REGELUNG.md`](FW3.3-PUMPEN-PWM-REGELUNG.md) — **VERSIONIERT**, V3.3. Zentrale PWM-/Pumpenregelung.

## Detaildokumente

- [`FW3.3-DURCHFLUSS-VERWENDUNG.md`](FW3.3-DURCHFLUSS-VERWENDUNG.md) — Verwendung des wirksamen Durchflusswertes in Regel-/Schutzpfaden.
- [`FW3.3-PUMPEN-EXTERNER-DURCHFLUSS.md`](FW3.3-PUMPEN-EXTERNER-DURCHFLUSS.md) — **KANONISCH für H30=3 / HYD61 / externen Durchfluss**.
- [`FW3.3-P08-PUMPEN-NENNLEISTUNG.md`](FW3.3-P08-PUMPEN-NENNLEISTUNG.md) — P08; für V3.3 kein aktiver Regelparameter.
- [`FW3.3-PUMPEN-100-PROZENT-OVERRIDES.md`](FW3.3-PUMPEN-100-PROZENT-OVERRIDES.md) — Zustände mit erzwungenen 100 % PWM.
- [`FW3.3-PUMPEN-DURCHFLUSS-KALIBRIERUNG-UPM4L.md`](FW3.3-PUMPEN-DURCHFLUSS-KALIBRIERUNG-UPM4L.md) — **LIVE/empirisch**, UPM4L-/WMZ-Durchflusskalibrierung.

## Ersetzte Datei

- [`FW3.3-HYD61-EXTERNER-DURCHFLUSS.md`](FW3.3-HYD61-EXTERNER-DURCHFLUSS.md) — **SUPERSEDED**, Redirect auf `FW3.3-PUMPEN-EXTERNER-DURCHFLUSS.md`.

### Suchbegriffe

```text
Umwälzpumpe Wasserpumpe circulation pump PWM flow Durchfluss
HYD61 Unit 0x61 H30 UPM4L P08 A40 D22 pump speed 100 Prozent
```

---

# 8. Kältekreis – EEV und Lüfter

- [`FW3.3-EEV-SMART-REGELUNG.md`](FW3.3-EEV-SMART-REGELUNG.md) — **VERSIONIERT**, EEV-/EVV-Smart-Regelung, elektronische Expansion.
- [`FW3.3-LUEFTERREGELUNG.md`](FW3.3-LUEFTERREGELUNG.md) — **VERSIONIERT**, Lüfter-Sollwerte, Fan-Driver, RPM-Regelung.

---

# 9. Modbus – Register, Parameter und externe Schnittstelle

## Kanonische / zentrale Referenzen

- [`FW3.3-MODBUS-GESAMTKATALOG.md`](FW3.3-MODBUS-GESAMTKATALOG.md) — **KANONISCH für V3.3-Registerzuordnung**.
- [`FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md`](FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md) — Parameterbereich.
- [`FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md`](FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md) — Status-/Livewertebereich.
- [`FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md`](FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md) — Service-/Engineering-Bereiche.

## Abgleich mit `FoxAir_Control`

- [`FW3.3-MODBUS-FINALE-DELTA-FOXAIR_CONTROL.md`](FW3.3-MODBUS-FINALE-DELTA-FOXAIR_CONTROL.md) — **KANONISCH für die noch umzusetzende V3.3-Delta-Liste**.
- [`FW3.3-MODBUS-KORREKTUREN-FOXAIR_CONTROL.md`](FW3.3-MODBUS-KORREKTUREN-FOXAIR_CONTROL.md) — **SUPERSEDED**, Redirect auf die finale Delta-/Audit-Dokumentation.

Hinweis vom Audit 05.09.2026: Der aktuelle `FoxAir_Control/data/foxair_phnix_registers.json` enthält noch nicht alle Punkte der finalen Delta-Liste; z. B. ist `MAIN:1022` dort weiterhin als `Reserviert` geführt. Die finale Delta-Datei ist daher **noch relevant** und nicht historisch erledigt.

## Sonderpfade

- [`FW3.3-SG-READY-MODBUS-8801.md`](FW3.3-SG-READY-MODBUS-8801.md) — SG Ready / Register 8801.
- [`FW3.3-WARMLINK-0x63-MODBUS-DISPATCHER.md`](FW3.3-WARMLINK-0x63-MODBUS-DISPATCHER.md) — Warmlink/DTU Dispatcher Unit `0x63`.

## Begleitdatensätze

- [`modbus_status_v3.3_delta_audit.csv`](modbus_status_v3.3_delta_audit.csv) — **DATENSATZ**.
- [`modbus_v3.3_final_delta.csv`](modbus_v3.3_final_delta.csv) — **DATENSATZ**.
- [`modbus_v3.3_master_ranges.csv`](modbus_v3.3_master_ranges.csv) — **DATENSATZ**.

---

# 10. Interner Modbus / Boardarchitektur / Hardware-UART

- [`FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md`](FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md) — **KANONISCH für V3.3-Boardtopologie**; interne Slave-Adressen und Boardrollen.
- [`FW3.3-INTERNER-MODBUS-UART-HARDWARE.md`](FW3.3-INTERNER-MODBUS-UART-HARDWARE.md) — USART/GPIO/RS485-Hardwarepfad.
- [`FW3.3-UNIT1-INVERTER-PROTOKOLL.md`](FW3.3-UNIT1-INVERTER-PROTOKOLL.md) — Unit `0x01` Leistungs-/Inverterboard.

---

# 11. Mainboard OTA / Firmware-Update

## Aktuelle Primärreferenzen

- [`PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md`](PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md) — **KANONISCH**, kompakter Gesamtpfad.
- [`PHNIX_phnixIot4G_board_ota_state_machine.md`](PHNIX_phnixIot4G_board_ota_state_machine.md) — **KANONISCH**, `board_ota_step` / Zustandsmaschine.
- [`PHNIX_phnixIot4G_board_ota_completion.md`](PHNIX_phnixIot4G_board_ota_completion.md) — **KANONISCH**, Abschluss / C36E Status 3/5 / Step 12.
- [`PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md) — **LIVE**, kompletter V3.3→V3.4-Lauf.
- [`PHNIX_phnixIot4G_ota_full_path.md`](PHNIX_phnixIot4G_ota_full_path.md) — vollständiger Originaldienst-Pfad.

## Transport / Download / Persistenz

- [`PHNIX_phnixIot4G_board_ota_http_download.md`](PHNIX_phnixIot4G_board_ota_http_download.md)
- [`PHNIX_phnixIot4G_0033_to_board_bin_transfer.md`](PHNIX_phnixIot4G_0033_to_board_bin_transfer.md)
- [`PHNIX_phnixIot4G_ota_rs485_frames.md`](PHNIX_phnixIot4G_ota_rs485_frames.md)
- [`PHNIX_phnixIot4G_ota_persistence.md`](PHNIX_phnixIot4G_ota_persistence.md)
- [`PHNIX_phnixIot4G_ota_runtime_followup.md`](PHNIX_phnixIot4G_ota_runtime_followup.md)
- [`PHNIX_phnixIot4G_C544_softcode_resume.md`](PHNIX_phnixIot4G_C544_softcode_resume.md)
- [`PHNIX_phnixIot4G_0033_handler_breakpoint.md`](PHNIX_phnixIot4G_0033_handler_breakpoint.md)

## Validierung / Sicherheit / Recovery

- [`FW3.3-OTA-ERKENNTNISSE.md`](FW3.3-OTA-ERKENNTNISSE.md) — **VERSIONIERT**, Mainboard-V3.3 OTA-/Flash-/Bootpfad.
- [`FW3.3-OTA-PROMOTION-RECOVERY.md`](FW3.3-OTA-PROMOTION-RECOVERY.md) — **VERSIONIERT**, Promotion/Abbruch/Recovery.
- [`FW3.3-OTA-VORTEST-SICHERHEIT.md`](FW3.3-OTA-VORTEST-SICHERHEIT.md) — **HISTORISCHER TESTKONTEXT mit weiterhin gültigen technischen Sicherheitsbefunden**.
- [`PHNIX_OTA_DYNAMISCHE_VALIDIERUNG.md`](PHNIX_OTA_DYNAMISCHE_VALIDIERUNG.md) — Labor-/dynamische Transportvalidierung.
- [`PHNIX_phnixIot4G_ota_cancel_rollback_restart.md`](PHNIX_phnixIot4G_ota_cancel_rollback_restart.md)
- [`PHNIX_CANCEL_PROBE_MAINBOARD_TESTPLAN.md`](PHNIX_CANCEL_PROBE_MAINBOARD_TESTPLAN.md) — **HISTORISCH/ARBEITSSTAND**.
- [`PHNIX_CANCEL_PROBE_LIVE_RESULT.md`](PHNIX_CANCEL_PROBE_LIVE_RESULT.md) — **LIVE**.
- [`PHNIX_C350_GLEICHVERSION_LIVE_RESULT.md`](PHNIX_C350_GLEICHVERSION_LIVE_RESULT.md) — **LIVE**.
- [`PHNIX_FULL_RUN_STALE_STATUS_LIVE_RESULT.md`](PHNIX_FULL_RUN_STALE_STATUS_LIVE_RESULT.md) — **LIVE**.

## Labor / Simulator / alte Übergaben

- [`PHNIX_OTA_VM_SIMULATOR.md`](PHNIX_OTA_VM_SIMULATOR.md) — **ARBEITSSTAND**.
- [`PHNIX_OFFLINE_VM_TESTBERICHT.md`](PHNIX_OFFLINE_VM_TESTBERICHT.md) — **HISTORISCH/LIVE-LABOR**.
- [`PHNIX_OTA_RUNTIME_HELPER_C36E_EVENT_LOOP_FIX.md`](PHNIX_OTA_RUNTIME_HELPER_C36E_EVENT_LOOP_FIX.md) — spezifischer Runtime-Fix.
- [`PHNIX_OTA_UPDATER_SAFETY_HARDENING_2026-08-24.md`](PHNIX_OTA_UPDATER_SAFETY_HARDENING_2026-08-24.md) — **HISTORISCH**.
- [`PHNIX_OTA_WORKCHAT_UEBERGABE.md`](PHNIX_OTA_WORKCHAT_UEBERGABE.md) — **HISTORISCH**.
- [`PHNIX_TRAFFIC_TRACER_LIVE_FINDINGS_2026-08-26.md`](PHNIX_TRAFFIC_TRACER_LIVE_FINDINGS_2026-08-26.md) — **LIVE**.

---

# 12. DTU / `phnixIot4G` – Gesamtarchitektur und Kommunikation

## Gesamtübersicht

- [`PHNIX_phnixIot4G_program_map.md`](PHNIX_phnixIot4G_program_map.md) — **bevorzugter Funktions-/Programmindex**.
- [`PHNIX_phnixIot4G_non_ota_architecture.md`](PHNIX_phnixIot4G_non_ota_architecture.md) — Nicht-OTA-Runtimearchitektur.
- [`PHNIX_phnixIot4G_RE.md`](PHNIX_phnixIot4G_RE.md) — **BASIS**, frühe breite statische OTA-/DTU-Analyse; spätere Spezialdokumente bei Detailkonflikten bevorzugen.
- [`Warmlink_LTE_DTU_ReverseEngineering.md`](Warmlink_LTE_DTU_ReverseEngineering.md) — **BASIS**, Hardware-/System-/Zugriffsübersicht; MQTT-Transportdetails nach neueren MQTT-Dokumenten bewerten.
- [`lte_verbindung.md`](lte_verbindung.md) — reale LTE-/AT-/ADB-Verbindungsdetails.

## Identität / Provisioning / Mainboard-RS485

- [`PHNIX_phnixIot4G_device_identity_block.md`](PHNIX_phnixIot4G_device_identity_block.md)
- [`PHNIX_phnixIot4G_identity_rs485.md`](PHNIX_phnixIot4G_identity_rs485.md)
- [`PHNIX_phnixIot4G_rs485_runtime.md`](PHNIX_phnixIot4G_rs485_runtime.md)
- [`PHNIX_phnixIot4G_uart_provisioning.md`](PHNIX_phnixIot4G_uart_provisioning.md)

## Cloud / MQTT / TLS

- [`PHNIX_phnixIot4G_mqtt_runtime_corrections.md`](PHNIX_phnixIot4G_mqtt_runtime_corrections.md) — **KANONISCH/LIVE für effektive CONNECT-/TLS-Parameter**; Keepalive 180 s.
- [`PHNIX_phnixIot4G_normal_mqtt_bridge.md`](PHNIX_phnixIot4G_normal_mqtt_bridge.md) — **KANONISCH für normalen MQTT↔RS485-Datenpfad**.
- [`PHNIX_phnixIot4G_tls_mqtt_trust.md`](PHNIX_phnixIot4G_tls_mqtt_trust.md) — TLS-/CA-/Hostname-Vertrauenspfad; `300000 ms` ist die angeforderte Keepalive-Vorgabe, nicht der effektive CONNECT-Wert.
- [`PHNIX_phnixIot4G_mqtt_connect_exact.md`](PHNIX_phnixIot4G_mqtt_connect_exact.md) — detaillierte statische CONNECT-Rekonstruktion; **bei Keepalive und Partner-/Module-ID durch `mqtt_runtime_corrections` überholt**.
- [`PHNIX_phnixIot4G_cloud_telemetry_commands.md`](PHNIX_phnixIot4G_cloud_telemetry_commands.md)
- [`PHNIX_phnixIot4G_hidden_runtime_remote_control.md`](PHNIX_phnixIot4G_hidden_runtime_remote_control.md)

Aktuell bestätigter Transport:

```text
MQTT 3.1.1
über TLS 1.2
über TCP Port 1883
CA-Prüfung + Hostname-Verifikation aktiv
CleanSession = 0
effektiver Keepalive = 180 s
```

## LTE / QMI / NAS

- [`PHNIX_phnixIot4G_qmi_client_init.md`](PHNIX_phnixIot4G_qmi_client_init.md)
- [`PHNIX_phnixIot4G_qmi_data_path.md`](PHNIX_phnixIot4G_qmi_data_path.md)
- [`PHNIX_phnixIot4G_qmi_minimal_responses.md`](PHNIX_phnixIot4G_qmi_minimal_responses.md)
- [`PHNIX_phnixIot4G_qmi_nas.md`](PHNIX_phnixIot4G_qmi_nas.md) — QMI/NAS/DMS/UIM-Grundlage.
- [`PHNIX_phnixIot4G_qmi_nas_followup.md`](PHNIX_phnixIot4G_qmi_nas_followup.md) — echte Vertiefung, kein Ersatz; Polling/RS485-Watchdogs.
- [`PHNIX_phnixIot4G_nas_serving_system_layout.md`](PHNIX_phnixIot4G_nas_serving_system_layout.md)

## Diagnose / Fehler / Sicherheit / Watchdogs

- [`PHNIX_phnixIot4G_diagnostics_statistics_debug.md`](PHNIX_phnixIot4G_diagnostics_statistics_debug.md)
- [`PHNIX_phnixIot4G_error_status.md`](PHNIX_phnixIot4G_error_status.md)
- [`PHNIX_phnixIot4G_watchdogs_reset_counters.md`](PHNIX_phnixIot4G_watchdogs_reset_counters.md) — bevorzugte Referenz für Reboot-/Offline-/Resetlogik.
- [`PHNIX_phnixIot4G_runtime_counters_remote_control_security.md`](PHNIX_phnixIot4G_runtime_counters_remote_control_security.md)
- [`PHNIX_phnixIot4G_security_findings.md`](PHNIX_phnixIot4G_security_findings.md)

---

# 13. DTU OTA Runner / lokaler Launcher

- [`PHNIX_DTU_AUTONOMOUS_RUNNER_LIVE_TEST_2026-09-01.md`](PHNIX_DTU_AUTONOMOUS_RUNNER_LIVE_TEST_2026-09-01.md) — **LIVE**, autonomer Minimal-Runner.
- [`PHNIX_DTU_OTA_RUNNER_STAGE1.md`](PHNIX_DTU_OTA_RUNNER_STAGE1.md) — Stage-1-Architektur / Umsetzung.
- [`PHNIX_DTU_OTA_RUNNER_STATUS_2026-09-02.md`](PHNIX_DTU_OTA_RUNNER_STATUS_2026-09-02.md) — bevorzugter aktueller Runner-Status.
- [`PHNIX_LOCAL_OTA_LAUNCHER_BEDIENUNG.md`](PHNIX_LOCAL_OTA_LAUNCHER_BEDIENUNG.md) — technischer lokaler Launcher.
- [`PHNIX_SAFE_LAUNCHER_REALMODEM_TESTS.md`](PHNIX_SAFE_LAUNCHER_REALMODEM_TESTS.md) — **LIVE**, Safe-Launcher mit realem Modem.
- [`PHNIX_phnixIot4G_safe_launcher.md`](PHNIX_phnixIot4G_safe_launcher.md) — Runtime-/Implementierungsanalyse Safe Launcher.
- [`PHNIX_LOGGER_REGISTER_UND_OTA_GUIDE.md`](PHNIX_LOGGER_REGISTER_UND_OTA_GUIDE.md) — Logger-/Register-/OTA-Arbeitsreferenz.

---

# 14. Vollständiges Inventar nach Dateityp

Dieser Abschnitt dient als Vollständigkeitskontrolle. **SUPERSEDED-Dateien bleiben absichtlich im Inventar**, weil ihre Pfade als Redirects erhalten werden.

## Katalog / Ordnerstatus

```text
KATALOG.md
README.md
```

## Mainboard-/Firmware- und Regelungsdokumente

```text
FW3.3-DURCHFLUSS-VERWENDUNG.md
FW3.3-EEV-SMART-REGELUNG.md
FW3.3-ERKENNTNISSE.md
FW3.3-HYD61-EXTERNER-DURCHFLUSS.md                 # SUPERSEDED
FW3.3-IAP-COPY-SPRUNGPFAD-KORREKTUR.md
FW3.3-INTERNER-MODBUS-BOARDARCHITEKTUR.md
FW3.3-INTERNER-MODBUS-UART-HARDWARE.md
FW3.3-KOMPRESSOR-INVERTER-ANSTEUERUNG.md
FW3.3-LUEFTERREGELUNG.md
FW3.3-MAIN-2139-FREQUENZLIMITIERUNGEN.md
FW3.3-MODBUS-FINALE-DELTA-FOXAIR_CONTROL.md
FW3.3-MODBUS-GESAMTKATALOG.md
FW3.3-MODBUS-KORREKTUREN-FOXAIR_CONTROL.md          # SUPERSEDED
FW3.3-MODBUS-PARAMETER-1001-1540-AUDIT.md
FW3.3-MODBUS-SERVICE-ENGINEERING-AUDIT.md
FW3.3-MODBUS-STATUS-2001-2180-AUDIT.md
FW3.3-OELRUECKFUEHRUNG.md
FW3.3-OTA-ERKENNTNISSE.md
FW3.3-OTA-PROMOTION-RECOVERY.md
FW3.3-OTA-VORTEST-SICHERHEIT.md
FW3.3-P08-PUMPEN-NENNLEISTUNG.md
FW3.3-PUMPEN-100-PROZENT-OVERRIDES.md
FW3.3-PUMPEN-DURCHFLUSS-KALIBRIERUNG-UPM4L.md
FW3.3-PUMPEN-EXTERNER-DURCHFLUSS.md
FW3.3-PUMPEN-PWM-REGELUNG.md
FW3.3-SG-READY-MODBUS-8801.md
FW3.3-UNIT1-INVERTER-PROTOKOLL.md
FW3.3-WARMLINK-0x63-MODBUS-DISPATCHER.md
FW3.4-WW-HEIZEN-UMSCHALTUNG-VERDICHTER.md
```

## PHNIX / DTU / OTA Dokumente

```text
PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md
PHNIX_C350_GLEICHVERSION_LIVE_RESULT.md
PHNIX_CANCEL_PROBE_LIVE_RESULT.md
PHNIX_CANCEL_PROBE_MAINBOARD_TESTPLAN.md
PHNIX_DTU_AUTONOMOUS_RUNNER_LIVE_TEST_2026-09-01.md
PHNIX_DTU_OTA_RUNNER_STAGE1.md
PHNIX_DTU_OTA_RUNNER_STATUS_2026-09-02.md
PHNIX_FIRMWAREFAMILIEN_SOFTWARECODES.md
PHNIX_FULL_RUN_STALE_STATUS_LIVE_RESULT.md
PHNIX_LOCAL_OTA_LAUNCHER_BEDIENUNG.md
PHNIX_LOGGER_REGISTER_UND_OTA_GUIDE.md
PHNIX_OFFLINE_VM_TESTBERICHT.md
PHNIX_OTA_DYNAMISCHE_VALIDIERUNG.md
PHNIX_OTA_RUNTIME_HELPER_C36E_EVENT_LOOP_FIX.md
PHNIX_OTA_UPDATER_SAFETY_HARDENING_2026-08-24.md
PHNIX_OTA_VM_SIMULATOR.md
PHNIX_OTA_WORKCHAT_UEBERGABE.md
PHNIX_SAFE_LAUNCHER_REALMODEM_TESTS.md
PHNIX_TRAFFIC_TRACER_LIVE_FINDINGS_2026-08-26.md
PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md
PHNIX_phnixIot4G_0033_handler_breakpoint.md
PHNIX_phnixIot4G_0033_to_board_bin_transfer.md
PHNIX_phnixIot4G_C544_softcode_resume.md
PHNIX_phnixIot4G_RE.md
PHNIX_phnixIot4G_board_is_allow_upg_handle.md
PHNIX_phnixIot4G_board_ota_completion.md
PHNIX_phnixIot4G_board_ota_http_download.md
PHNIX_phnixIot4G_board_ota_state_machine.md
PHNIX_phnixIot4G_cloud_telemetry_commands.md
PHNIX_phnixIot4G_device_identity_block.md
PHNIX_phnixIot4G_diagnostics_statistics_debug.md
PHNIX_phnixIot4G_error_status.md
PHNIX_phnixIot4G_hidden_runtime_remote_control.md
PHNIX_phnixIot4G_identity_rs485.md
PHNIX_phnixIot4G_mqtt_connect_exact.md
PHNIX_phnixIot4G_mqtt_runtime_corrections.md
PHNIX_phnixIot4G_nas_serving_system_layout.md
PHNIX_phnixIot4G_non_ota_architecture.md
PHNIX_phnixIot4G_normal_mqtt_bridge.md
PHNIX_phnixIot4G_ota_cancel_rollback_restart.md
PHNIX_phnixIot4G_ota_full_path.md
PHNIX_phnixIot4G_ota_persistence.md
PHNIX_phnixIot4G_ota_rs485_frames.md
PHNIX_phnixIot4G_ota_runtime_followup.md
PHNIX_phnixIot4G_program_map.md
PHNIX_phnixIot4G_qmi_client_init.md
PHNIX_phnixIot4G_qmi_data_path.md
PHNIX_phnixIot4G_qmi_minimal_responses.md
PHNIX_phnixIot4G_qmi_nas.md
PHNIX_phnixIot4G_qmi_nas_followup.md
PHNIX_phnixIot4G_rs485_runtime.md
PHNIX_phnixIot4G_runtime_counters_remote_control_security.md
PHNIX_phnixIot4G_safe_launcher.md
PHNIX_phnixIot4G_security_findings.md
PHNIX_phnixIot4G_tls_mqtt_trust.md
PHNIX_phnixIot4G_uart_provisioning.md
PHNIX_phnixIot4G_watchdogs_reset_counters.md
Warmlink_LTE_DTU_ReverseEngineering.md
lte_verbindung.md
```

## Strukturierte Begleitdaten

```text
modbus_status_v3.3_delta_audit.csv
modbus_v3.3_final_delta.csv
modbus_v3.3_master_ranges.csv
```

---

# 15. Ergebnis des Dokument-Audits vom 05.09.2026

## Konsolidiert

| Datei | Ergebnis |
|---|---|
| `FW3.3-HYD61-EXTERNER-DURCHFLUSS.md` | **SUPERSEDED** → Redirect auf `FW3.3-PUMPEN-EXTERNER-DURCHFLUSS.md` |
| `FW3.3-MODBUS-KORREKTUREN-FOXAIR_CONTROL.md` | **SUPERSEDED** → Redirect auf finale Delta-/Audit-Dokumente |

## Bewusst getrennt gelassen

Die folgenden ähnlich klingenden Gruppen sind **keine Dubletten**:

- `PUMPEN-PWM-REGELUNG` vs. `DURCHFLUSS-VERWENDUNG` vs. `PUMPEN-DURCHFLUSS-KALIBRIERUNG-UPM4L`: Regelalgorithmus, Verbraucher des Flow-Werts und reale Kalibrierung sind unterschiedliche Ebenen.
- `KOMPRESSOR-INVERTER-ANSTEUERUNG` vs. `UNIT1-INVERTER-PROTOKOLL`: Mainboard-Regelkette gegenüber Remote-Protokoll des zweiten Boards.
- `OTA-ERKENNTNISSE` vs. `OTA-PROMOTION-RECOVERY` vs. `OTA-VORTEST-SICHERHEIT`: Gesamtpfad, Recovery-Vertiefung und historischer Sicherheits-/Testkontext.
- `phnixIot4G_ota_full_path` vs. `ota_runtime_followup`: Gesamt-OTA-Pfad gegenüber Timer-/Stall-/Persistenz-Vertiefung.
- `qmi_nas` vs. `qmi_nas_followup`: QMI/NAS-Grundlage gegenüber Polling-/Watchdog-Vertiefung.

## Bekannte veraltete Einzelangaben

- `PHNIX_phnixIot4G_RE.md`: frühe Aussage „unverschlüsseltes TCP/1883“ ist durch spätere Analyse widerlegt. Aktuell bestätigt ist **TLS 1.2 auf TCP-Port 1883**.
- `PHNIX_phnixIot4G_mqtt_connect_exact.md`: die statische Zwischenableitung `Keepalive=300 s` ist nicht der effektive Wire-Wert; das SDK begrenzt auf **180 s**. Partner-/Module-ID sind in diesem Build vorhanden.
- `PHNIX_phnixIot4G_tls_mqtt_trust.md`: `300000 ms` im lokalen Parameterblock ist korrekt als **angeforderter** Wert, aber der effektive MQTT-CONNECT-Wert beträgt **180 s**.
- `Warmlink_LTE_DTU_ReverseEngineering.md`: `MQTT über TCP/1883` technisch präzisieren zu **MQTT 3.1.1 über TLS 1.2 über TCP-Port 1883**.

Diese alten Dateien bleiben als Analyseprovenance erhalten. Für neue Antworten sollen die in Abschnitt 3 genannten aktuellen Quellen Vorrang haben.

---

# 16. Pflegekonvention für neue Erkenntnisse

1. **Vorhandenes Spezialdokument aktualisieren**, wenn Thema und Firmwarestand bereits passen.
2. **Neues Dokument anlegen**, wenn ein eigenständiger Regelpfad, eine andere Firmwareversion oder eine neue Hardwarekomponente untersucht wird.
3. Firmwarestand im Dateinamen verwenden, wenn Code-/RAM-Adressen versionsabhängig sind (`FW3.3-...`, `FW3.4-...`).
4. Im Dokument klar zwischen `bestätigt`, `stark bestätigt`, `Hypothese/offen` unterscheiden.
5. Bei Live-Versuchen Datum und reale Firmware-/Hardwareversion dokumentieren.
6. Wenn ein älteres Dokument durch ein besseres ersetzt wird, möglichst **nicht löschen**: alten Pfad als `SUPERSEDED`-Stub mit `canonical_document` erhalten.
7. Bei einer neuen Korrektur eine `known_corrections`-Notiz in diesem Katalog ergänzen, bis das Ursprungsdokument selbst sauber aktualisiert wurde.
8. Dateiumbenennungen nur durchführen, wenn der alte Name wirklich irreführend ist; anschließend alle internen Links aktualisieren.
9. **Jedes neue oder wesentlich geänderte Reverse-Engineering-Thema anschließend in `KATALOG.md` eintragen.**

---

# 17. Noch sinnvolle zukünftige Kategorien

```text
- Abtauung / Defrost
- Warmwasserregelung allgemein
- 3-Wege-/4-Wege-Ventile
- Frostschutz
- elektrische Heizstäbe
- Temperatursensoren / ADC
- Fehler- und Schutz-State-Machines
- Zeitprogramme / SG Ready / PV-Logik
- Display-/DWIN-Protokoll
```

Bis eigene Spezialdokumente existieren, sollen solche Fragen zunächst über `FW3.3-ERKENNTNISSE.md`, Modbus-Katalog und thematisch benachbarte Dokumente geroutet werden.
