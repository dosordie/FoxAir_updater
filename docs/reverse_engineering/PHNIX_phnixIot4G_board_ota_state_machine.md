# PHNIX `phnixIot4G` – `board_ota_step` State-Machine

Stand: 29. August 2026

Grundlage ist die statische Analyse des ARM-ELF `phnixIot4G`, ergänzt um den erfolgreichen realen V3.3→V3.4-Lauf. Schwerpunkt ist die Board-OTA-Zustandsmaschine in `dtu_upgrade_pro()` (`0x1D5C0`) sowie die direkten `set_board_ota_step()`-Übergänge.

> [!IMPORTANT]
> Der reale Lauf bestätigte die zentrale Abschlusssequenz: kompletter C5A8-Transfer → Step 12/Warten → C36E Status 3 → mehrere Minuten Board-Promotion → C36E Status 5 → Step 5/Erfolgsreport → terminal wieder Step 12. Anschließend meldete C544 die neue Version `0034`.

## 1. Globale Zustandsvariable

```text
ota_info @ 0x98A7C
board_ota_step = ota_info + 0x18
Adresse: 0x98A94
```

Zugriff:

```text
set_board_ota_step() @ 0x1D34C
get_board_ota_step() @ 0x1D38C
```

`dtu_upgrade_pro()` arbeitet produktiv nur bei:

```text
get_dtu_run_step() == 11
```

## 2. Verwendete Step-Werte

Aktiv verwendet werden:

```text
1, 3, 5, 6, 7, 8, 9, 10, 12
```

`12` ist mehrdeutig: Es ist sowohl neutraler/abgeschlossener Zustand als auch Wartezustand zwischen Transferaktionen und eingehenden Boardstatusmeldungen. Deshalb darf `board_ota_step == 12` allein nicht als „Update vollständig“ interpretiert werden.

## 3. Hauptpfad

```text
lokaler/Cloud OTA-Auftrag 0033
        ↓
step 1   Upgrade-Erlaubnis / Boardstatus melden
        ↓
step 3   Firmware laden + MD5 prüfen
        ↓
step 6   Firmwareblock via C5A8 senden
        ↓
step 12  auf Boardantwort / nächsten Zustand warten
        ↕
step 6   weitere C5A8-Blöcke
        ↓
Transfer vollständig
        ↓
step 12
        ↓
C36E Status 3
        ↓
step 12 bleibt Wartezustand; Mainboard promoted selbstständig
        ↓
C36E Status 5
        ↓
step 5   Erfolg melden
        ↓
step 12  terminaler Dienstzustand
```

Fehler-/Sonderpfade:

```text
step 7   Cancel / Recovery
step 8   Rollback-Steuerung
step 9   Rollback-Ergebnis melden
step 10  Upgradefehler melden
```

## 4. `step 1` – Upgrade-Erlaubnis / Statusreport

Block:

```text
0x1D750 ... 0x1D81C
```

Kern:

```c
if (board_ota_step == 1) {
    if (board_request_upgrade() != 0)
        return;

    if (ota_info[0] == 0 && otaDeviceInfo.fileSize != 0) {
        board_ota_step = 3;
        ...
    }
}
```

`board_request_upgrade()` führt den PHNIX-Report `0023` aus. Im lokalen Updater wird die notwendige Erfolgssemantik dieses Originalpfads kontrolliert bereitgestellt.

## 5. `step 3` – Firmware laden und MD5 prüfen

Block:

```text
0x1D820 ... 0x1D9D4
```

Normaler Pfad:

```text
board_ota_http_download()
→ Firmware nach /cache/phnixIot_device_OTA
→ ota_check_device_otaFile_md5()
→ Offset/MD5/Länge/Version persistieren
→ board_ota_step = 6
```

Nach mehr als zwei fehlgeschlagenen Download-/Prüfversuchen geht der Dienst auf:

```text
step 10
```

und meldet den Fehler.

Beim lokalen Updater stammt die Download-URL aus dem eingespeisten `0033`, zeigt aber auf den lokalen Loopback-HTTP-Server `127.0.0.1`.

## 6. `step 6` – C5A8-Firmwaredaten senden

Block:

```text
0x1D9D8 ... 0x1DA04
```

Kern:

```c
if (board_ota_step == 6) {
    if (set_update_board_bin_by_485() == 0)
        board_ota_step = 12;
    else
        return;
}
```

`set_update_board_bin_by_485()` / `set_board_update_bin()` lesen die Firmware und erzeugen C5A8-Frames über den gemeinsamen UART-Sendeslot.

Während des Transfers wechseln Step 6 und Step 12 entsprechend Sendung/Antwortverarbeitung. Deshalb ist Step 12 während C5A8 **nicht** automatisch terminal.

Im realen V3.3→V3.4-Lauf dauerte die C5A8-Phase rund **28:56 Minuten**.

## 7. `step 12` – Warte-/Abschlusszustand

Step 12 besitzt keinen eigenen großen Workerblock. Eingehende RS485-Handler treiben die Zustandsmaschine weiter.

Wichtigster heutiger Erkenntnisstand:

- nach einem einzelnen C5A8 kann Step 12 nur „warte auf C371/Boardantwort“ bedeuten;
- nach dem letzten C5A8 bedeutet Step 12 zunächst „Transfer vollständig, warte auf Boardstatus“;
- C36E Status 3 bestätigt Staging/erste MD5-Stufe, ist aber nicht terminal;
- erst C36E Status 5 kann aus dem passenden Step-12-Kontext Step 5 erzeugen;
- nach erfolgreichem Step-5-Report kehrt der Dienst wieder auf Step 12 zurück.

Deshalb braucht eine terminale Bewertung zusätzlich den beobachteten Status-/Phasenkontext.

## 8. C36E Status 3

Status 3 wird durch `board_is_allow_upg_handle()` verarbeitet und mit C37B/status 3 quittiert.

Er bedeutet im bekannten Mainboardpfad:

```text
vollständiges Staging-Image
+
Staging-MD5 erfolgreich
+
Board-Promotion läuft weiter
```

Status 3 setzt **nicht** den finalen Erfolgspfad Step 5 in Gang.

Im realen V3.3→V3.4-Lauf kam Status 3 rund **2 Sekunden nach dem letzten C5A8**.

## 9. C36E Status 5 → `step 5`

Im Status-5-Pfad von `board_is_allow_upg_handle()`:

```text
dtu_reply_recv_status(5)
sys_set_board_file_offset(0)
sys_set_board_file_len(0)
...
if current step == 12:
    set_board_ota_step(5)
```

Damit ist Status 5 der Übergang in den LTE-Erfolgsreport.

Der reale V3.3→V3.4-Lauf erreichte Status 5 rund **5:16 Minuten nach dem letzten C5A8**.

## 10. `step 5` – Erfolg melden

Block:

```text
0x1DA08 ... 0x1DA40
```

```text
board_ota_rep()
→ ota_device_send_ota_finish()
→ Code 0053 / progress 100
```

Bei erfolgreicher Reportsemantik:

```text
board_ota_step = 12
```

Der aktuelle lokale Updater verwendet den erfolgreich durchlaufenen **Status-5-/Step-5-/Step-12-Abschluss** als terminalen Mainboarderfolg.

## 11. `step 10` – Upgradefehler melden

Block:

```text
0x1D70C ... 0x1D74C
```

```text
sys_set_board_file_offset(0)
board_upgrade_fail_rep()
→ ota_device_send_ota_Failed()
```

Bei erfolgreicher Reportsemantik:

```text
board_ota_step = 12
```

Step 10 wird unter anderem nach endgültigem Downloadfehler und aus mehreren Board-/Cancelfehlerpfaden erreicht.

## 12. `step 7` – Cancel/Recovery

Step 7 wird unter anderem gesetzt durch:

- `down_board_cancel_ota_handle()`;
- `board_recv_cancel_upgrade_handle()`;
- bestimmte `board_is_allow_upg_handle()`-Pfade.

Der Dienst sendet im Cancelpfad C36A und erwartet C36C. Danach kann ein Fehler-/Reportpfad folgen.

Für den aktuellen Updater gilt jedoch die härtere Sicherheitsgrenze: Ein generischer Host-Restore wird **ab begonnenem C5A8 nicht mehr als Recoveryinstrument benutzt**. Ab dann bleibt der Originaldienst autoritativ.

## 13. `step 8` / `step 9` – Rollback

```text
step 8
→ dtu_to_board(1/2/3)
→ Rollback-/Backroll-Steuerung
→ step 9
→ board_verbackroll_result_repo()
→ bei Erfolg step 12
```

Diese Pfade sind statisch rekonstruiert, aber nicht Teil des erfolgreichen V3.3→V3.4-Normalpfads.

## 14. State-Tabelle

| Step | Bedeutung | Hauptaktion | Typischer Folgezustand |
|---:|---|---|---:|
| 0 | Idle / uninitialisiert | keine eigene Aktion | extern |
| 1 | Upgrade-Erlaubnis/Status | `board_request_upgrade()` | 3 |
| 3 | Firmware laden + MD5 | `board_ota_http_download()` | 6 oder 10 |
| 5 | Erfolg melden | `board_ota_rep()` | 12 |
| 6 | Firmware an Board übertragen | `set_update_board_bin_by_485()` | 12 |
| 7 | Cancel/Recovery | `reply_cancel_upgrade()` / Cleanup | 10 bzw. extern |
| 8 | Rollback-Steuerung | `dtu_to_board()` | 9 |
| 9 | Rollback-Ergebnis melden | `board_verbackroll_result_repo()` | 12 |
| 10 | Upgradefehler melden | `board_upgrade_fail_rep()` | 12 |
| 12 | Warte-/neutraler Abschlusszustand | keine direkte Hauptaktion | 6/5/8/... via Handler |

## 15. Kontrollfluss-Adressen

```text
board_ota_step storage         0x98A94
set_board_ota_step()           0x1D34C
get_board_ota_step()           0x1D38C
dtu_upgrade_pro()              0x1D5C0

step 10 block                  0x1D70C
step 1 block                   0x1D750
step 3 block                   0x1D820
HTTP download call             0x1D860
step 3 -> 6                    0x1D8FC
step 6 block                   0x1D9D8
RS485 firmware-send call       0x1D9E8
step 6 -> 12                   0x1D9F8
step 5 block                   0x1DA08
step 7 block                   0x1DA44
step 8 block                   0x1DB9C
step 9 block                   0x1DC60
```

## 16. Live-Bestätigung

V3.3→V3.4:

| Ereignis | Zeitpunkt |
|---|---|
| erster C5A8 | 00:51:20 |
| letzter C5A8 | 01:20:16 |
| C36E Status 3 | 01:20:18 |
| C36E Status 5 | 01:25:32 |
| terminaler Board-Step 12 | 01:25:34 |
| C544 Version `0034` | 01:26:33 |

Damit wurden die wesentlichen Zustände des normalen erfolgreichen Pfads nicht nur statisch, sondern auch dynamisch auf realer Hardware bestätigt.

## 17. Wichtigste Schlussfolgerungen

1. `0033` allein bedeutet noch keinen RS485-Firmwaretransfer.
2. Die Firmwaredatenphase beginnt in Step 6 / C5A8.
3. Step 12 ist kontextabhängig und nicht allein terminal.
4. Status 3 ist Staging-Erfolg, kein finaler Erfolg.
5. Status 5 führt aus dem passenden Step-12-Kontext in Step 5.
6. Erst nach erfolgreichem Status-5-/Step-5-Abschluss und Rückkehr auf Step 12 ist der Dienstpfad terminal erfolgreich.
7. Die neue C544-Version liefert anschließend einen unabhängigen praktischen Nachweis, dass die neue Firmware aktiv ist.

## 18. Referenzen

- [`PHNIX_phnixIot4G_board_ota_completion.md`](PHNIX_phnixIot4G_board_ota_completion.md)
- [`PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md`](PHNIX_V33_TO_V34_LIVE_UPDATE_2026-08-29.md)
- [`PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md`](PHNIX-OTA-UPDATE-ABLAUF-KURZREFERENZ.md)