# PHNIX `phnixIot4G` – Abschluss des Board-OTA nach letztem C5A8-Block

Stand: 29. August 2026

Diese Notiz rekonstruiert den Abschluss des Board-OTA nach dem letzten Firmwareblock. Die statische Analyse wurde inzwischen durch den erfolgreichen realen V3.3→V3.4-Lauf ergänzt.

> [!IMPORTANT]
> Live bestätigt wurden inzwischen die reale Reihenfolge **letzter C5A8 → C36E Status 3 → C36E Status 5 → Board-Step 12 → C544 Version `0034`**.
>
> Im Live-Lauf lagen zwischen letztem C5A8 und Status 3 rund **2 Sekunden**, zwischen letztem C5A8 und Status 5 rund **5 Minuten 16 Sekunden**.

## 1. Ende des C5A8-Transfers

In `dtu_upgrade_pro()`:

```text
0x1D9D8  get_board_ota_step()
0x1D9E0  compare == 6
0x1D9E8  set_update_board_bin_by_485()
0x1D9F0  compare return == 0
0x1D9F8  set_board_ota_step(12)
```

Semantisch:

```c
if (board_ota_step == 6) {
    if (set_update_board_bin_by_485() == 0)
        set_board_ota_step(12);
}
```

`0` bedeutet hier: kein weiterer Datenblock mehr zu senden / Datei vollständig abgearbeitet. Der Übergang auf Step 12 erfolgt im Worker und nicht direkt im C371-ACK-Handler.

Wichtig: **100 % Offset bzw. der letzte C5A8 ist noch kein terminaler Firmwareerfolg.** Danach folgen mindestens Staging-Prüfung und Mainboard-Promotion.

## 2. Step 12 als Wartezustand

Step 12 erzeugt in `dtu_upgrade_pro()` keinen eigenen Abschlussreport und setzt nicht automatisch Step 5. Der Worker wartet auf ein eingehendes Board-Statusframe, das über `board_is_allow_upg_handle()` verarbeitet wird.

Die V3.3-Mainboard-Firmware unterscheidet zwei Erfolgsstufen:

```text
C36E Status 3
= vollständiges Staging-Image / Staging-MD5 erfolgreich

C36E Status 5
= späterer Promotion-/Commit-Abschluss
```

Status 3 ist damit **kein Fehler und kein terminaler Erfolg**.

Der reale V3.3→V3.4-Lauf bestätigte diese Zweistufigkeit praktisch.

## 3. Eingehendes C36E Status 5

`unpack_mcu_modbus()` reicht für Register C36E den Datenbereich an:

```text
board_is_allow_upg_handle() @ 0x1BA04
```

Der Handler liest:

```text
data[1]   -> SSID low byte
data[3]   -> Board-OTA-Status
data[4:5] -> optionale Blockgröße, nur bei len == 6
```

Für SSID `0x0063`, Status `5`, Blockgröße `168` ist ein synthetisch gültiges vollständiges FC10-Frame:

```text
63 10 C3 6E 00 03 06 00 63 00 05 00 A8 24 D9
```

Diese sechs Nutzbytes sind handler-kompatibel, aber kein behaupteter Live-Mitschnitt. Das reale Mainboard verwendet den bekannten C36E-Aufbau mit zwei Registern/vier Nutzbytes.

## 4. Exakter Status-5-Pfad im Handler

Relevante Instruktionen:

```text
0x1BE08  load otaDeviceInfo+0x251
0x1BE0C  compare status == 5
0x1BE30  r0 = 5
0x1BE34  BL dtu_reply_recv_status
0x1BE38  r0 = 0
0x1BE3C  BL sys_set_board_file_offset
0x1BE40  r0 = 0
0x1BE44  BL sys_set_board_file_len
0x1BE48  app+1 = 0
0x1BE58  get_board_ota_step()
0x1BE60  compare == 12
0x1BE68  r0 = 5
0x1BE6C  BL set_board_ota_step
0x1BE70  ota_info+0x16 = 0
```

Semantisch:

```c
if (board_status == 5) {
    dtu_reply_recv_status(5);
    sys_set_board_file_offset(0);
    sys_set_board_file_len(0);
    app[1] = 0;

    if (board_ota_step == 12)
        set_board_ota_step(5);

    ota_info[0x16] = 0;
}
```

Damit ist Status 5 eindeutig der Board-Erfolgsabschluss im Originaldienst.

## 5. DTU-Antwort auf Status 3/5: C37B

`dtu_reply_recv_status()` bei `0x1AD30` baut ein FC10-Frame an Register C37B:

```text
63 10 C3 7B 00 02 04
SSID_HI SSID_LO
STATUS_HI STATUS_LO
CRC_LO CRC_HI
```

Bekannte Beispiele für SSID `0x0063`:

```text
Status 3: 63 10 C3 7B 00 02 04 00 63 00 03 B4 6B
Status 4: 63 10 C3 7B 00 02 04 00 63 00 04 F5 A9
Status 5: 63 10 C3 7B 00 02 04 00 63 00 05 34 69
Status 6: 63 10 C3 7B 00 02 04 00 63 00 06 74 68
```

Status 3 wird quittiert, löst aber nicht den finalen Cloud-/Step-5-Abschluss aus.

Aus der Mainboard-Firmwareanalyse folgt außerdem: Ein fehlendes C37B/3 ist **kein Promotion-Gate**; die Board-Promotion läuft unabhängig weiter.

## 6. Step 5 → Erfolgsreport → Step 12

In `dtu_upgrade_pro()`:

```text
0x1DA08  get_board_ota_step()
0x1DA10  compare == 5
0x1DA18  BL board_ota_rep
0x1DA20  compare return == 0
0x1DA34  r0 = 12
0x1DA38  BL set_board_ota_step
```

`board_ota_rep()` ruft:

```text
ota_device_send_ota_finish() @ 0x191C0
```

auf.

Das PHNIX-JSON lautet sinngemäß:

```json
{"cmd":"CMD_OTA","code":"0053","param":{"deviceCode":"<redigiert>","progress":"100","ssid":"0063"}}
```

Nach erfolgreicher Behandlung des Reports kehrt der Worker auf Step 12 zurück.

Endsequenz aus Sicht des Dienstes:

```text
C36E Status 5
→ C37B Status-5-ACK
→ Step 12 → Step 5
→ Erfolgsreport 0053 / progress 100
→ Step 5 → Step 12
```

Der aktuelle lokale Updater behandelt den terminalen **Status 5 / Board-Step 12** als erfolgreichen Mainboardabschluss.

## 7. Live-Validierung V3.3 → V3.4

Der zuvor nur statisch/synthetisch rekonstruierte Abschluss wurde am 29. August 2026 auf realer Hardware bestätigt.

Gemessener Ablauf:

| Zeitpunkt | Ereignis |
|---|---|
| 01:20:16 | letzter C5A8-Firmwareblock bestätigt |
| 01:20:18 | C36E Status 3 |
| 01:25:32 | C36E Status 5 |
| 01:25:34 | Runtime-Helfer: terminaler Erfolg, `board_ota_step=12` |
| 01:26:33 | C544 meldet Softwarecode `82400644`, Version `0034` |

Damit ist praktisch bestätigt:

- Status 3 folgt nach vollständiger Datenübertragung/Staging-Prüfung;
- Status 3 ist nicht terminal;
- das Mainboard arbeitet danach mehrere Minuten selbstständig weiter;
- Status 5 markiert den erfolgreichen Abschluss der Board-Promotion;
- Board-Step 12 wird danach terminal erreicht;
- die neue Firmware V3.4 ist anschließend aktiv und meldet sich über C544.

Der Originaldienst blieb bis Status 5 derselbe Prozess.

## 8. Bedeutung für Simulatoren

Ein Mainboard-naher Simulator sollte mindestens folgende Reihenfolge nachbilden:

```text
1. letzten C5A8 empfangen
2. finalen C371-ACK erzeugen
3. Transferende / Step 12 zulassen
4. C36E Status 3 erzeugen
5. Promotion-/Verarbeitungsphase simulieren
6. C36E Status 5 erzeugen
7. C37B Status-5-ACK erwarten
8. terminalen Board-Step 12 zulassen
```

Für schnelle Tests dürfen die realen fünf Minuten Promotionzeit komprimiert werden; die Zustandsreihenfolge darf dadurch nicht verändert werden.

## 9. Sinnvolle Breakpoints für Laboranalyse

```gdb
b *0x1D9E8   # set_update_board_bin_by_485()
b *0x1D9F8   # unmittelbar vor Step 6 -> 12
b *0x1BE30   # Status-5-Pfad erkannt
b *0x1BE6C   # unmittelbar vor Step 12 -> 5
b *0x1DA18   # vor Erfolgsreport
b *0x19250   # vor ali_mqtt_push_OTA_msg() für 0053
```

## 10. Evidenzgrad

**Statisch direkt bewiesen:**

- Step 6 → 12 bei EOF von `set_update_board_bin_by_485()`;
- Status 5 ruft `dtu_reply_recv_status(5)` auf;
- Status 5 löscht Offset und Dateilänge;
- nur bei Step 12 wird Step 5 gesetzt;
- Step 5 führt den Erfolgsreport aus;
- danach Rückkehr auf Step 12;
- C37B-Frameaufbau;
- Mainboardpfad Status 3 vor späterem Status 5.

**Live bestätigt:**

- kompletter C5A8-Transfer;
- Status 3 nach letztem Datenblock;
- mehrere Minuten Promotionphase;
- Status 5;
- terminaler Board-Step 12;
- neue aktive C544-Version `0034`.

**Weiterhin nicht aus diesem einen Lauf bewiesen:**

- Verhalten beliebiger anderer Mainboardfamilien/Softwarecodes;
- alle Fehlerpfade Status 4/6 auf realer Hardware;
- Power-Loss-/Loader-Recovery während kritischer Promotionphasen.

## 11. Referenzen

- [`PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md)
- [`PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md`](PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md)
- [`PHNIX_phnixIot4G_board_ota_state_machine.md`](PHNIX_phnixIot4G_board_ota_state_machine.md)