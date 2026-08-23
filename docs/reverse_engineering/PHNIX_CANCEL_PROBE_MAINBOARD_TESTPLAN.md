# PHNIX Cancel-Probe – Testplan vor dem ersten Mainboard-Schreibtest

Stand: 2026-08-23

## Ziel

Der erste Mainboardtest soll ausschließlich den originalen Cancelpfad prüfen:

```text
lokales Original-0073
  -> down_board_cancel_ota_handle
  -> Board-Step 7
  -> C36A Status 1
  -> C36C Status 1
  -> cancel_pending gelöscht
  -> Board-Step 10
  -> lokaler 0083-Publish-Erfolg
  -> Board-Step 12
```

Es wird dabei **kein 0033**, kein C350, kein C357 und kein C5A8 gesendet. Es
wird keine Firmwaredatei übertragen.

## Warum dieser Test nur „ungefährlich“ und nicht risikofrei ist

Die Mainboardanalyse zeigt, dass ein früher C36A-Pfad ohne gesetztes
`OTA+0x1C` keinen Staging-Flash-Erase ausführt. C36A setzt jedoch den
OTA-/EEPROM-Zustand `0x3F0` zurück. Der Test ist deshalb ein begrenzter
Schreibtest am Mainboard und benötigt eine ausdrückliche Freigabe.

Der Test darf nicht ausgeführt werden, wenn ein echter oder unterbrochener OTA
aktiv sein könnte.

## Buildgebundene Beobachtungspunkte

Für den verifizierten Originaldienst mit SHA-256
`7c573431f0a67620d473419644a83a4f4dc04b8a91bde5923c74a63ba1eaedb7`
sind vorbereitet:

| Adresse | Nachweis |
|---:|---|
| `0x1FDAC` | kontrollierter Scheduler-/Parser-Einstieg |
| `0x19764` | Originalhandler für Cloud-Code 0073 |
| `0x1DACC` | tatsächlicher Aufruf von `reply_cancel_upgrade(1)` / C36A |
| `0x1B51C` | Eingang des C36C-Handlers |
| `0x1B5A8` | `cancel_pending` wurde unmittelbar zuvor gelöscht |
| `0x1DB94` | effektiver Übergang von Step 7 auf Step 10 |
| `0x19264` | originaler 0083-Fehlerreport |
| `0x1D748` | ausgeführter terminaler Step-12-Übergang |

`tools/phnix_ota/verify_runtime_profile.py` prüft SHA-256 und die erwarteten
Maschinenbefehle an allen acht Stellen. Der Runtime-Helfer kann sie mit
`cancel-breakpoint-test` gemeinsam setzen und wieder entfernen, ohne einen
Handler auszuführen oder ein RS485-Frame zu senden.

## Exaktes Cancel-JSON

```json
{"cmd":"CMD_OTA","code":"0073"}
```

`ota_code_handle()` dispatcht ausschließlich anhand des numerisch gelesenen
Top-Level-Feldes `code`. Der Handler 0073 liest keine `param`-Felder.

## Zwingende Vorbedingungen

1. Wärmepumpe läuft stabil im Normalbetrieb.
2. Kein Update, Resume oder Rollback wurde begonnen.
3. OTA_INFO besitzt gültige CRC sowie `offset == 0` und `length == 0`.
4. Originaldienst und alle acht Breakpoint-Opcodes stimmen exakt.
5. Zwei `helloworld`-Watchdogs sind vorhanden.
6. Stabile Stromversorgung; während des Tests nicht abschalten.
7. Original-Cloud wird für das kurze Testfenster blockiert.
8. RS485 wird passiv mitgeschnitten.
9. Vor der Injektion wurde eine zusammenhängende Sendepause beobachtet.
10. Eine Person überwacht Wärmepumpe, LTE-Modem und Statusausgabe.

Lesender Vorplan:

```sh
python3 tools/phnix_ota/phnix_local_ota_controller.py \
  --adb adb \
  cancel-probe-plan
```

Der Plan muss `ready: true` und `live_send_enabled: false` melden. Das zweite
Feld bleibt bis zur bewussten Testfreigabe absichtlich `false`.

## Harte Abbruchkriterien

Der Dienst und die Guards bleiben in `guarded-hold`, wenn eines zutrifft:

- 0073 erreicht den Originalhandler nicht;
- vor C36A erscheint ein unerwartetes OTA- oder normales TX-Frame;
- C36A enthält falsche SSID oder falschen Status;
- kein passendes C36C Status 1 eintrifft;
- `cancel_pending` nicht gelöscht wird;
- Step 10 oder der originale 0083-Pfad fehlt;
- Step 12 wird nicht erreicht;
- Mainboard oder Wärmepumpe zeigen ungewöhnliches Verhalten.

Ein Timeout ist **kein** Nachweis eines sicheren Abbruchs und erlaubt kein
automatisches Aufräumen.

## Erfolgskriterien

Alle folgenden Punkte müssen gemeinsam im selben Lauf vorliegen:

```text
0073-Handler gesehen
C36A gesehen
C36C mit passender SSID und Status 1 gesehen
cancel_pending == 0
Step 10 gesehen
0083 lokal bestätigt
Step 12 ausgeführt
Normalbetrieb passiv bestätigt
keine C350/C357/C5A8-Frames
```

Erst danach dürfen Debugger, Cloudsperre und pausierte Watchdogs entfernt
werden.

## Aktueller Freigabestatus

- statische Adressen und Opcodes: vorbereitet;
- VM-Simulatorvertrag: getestet;
- Breakpoint-Installationskommando: am echten Originaldienst erfolgreich;
- alle acht Punkte gleichzeitig gesetzt, aufgelistet und entfernt;
- danach `TracerPid: 0`, 13 Threads und beide Watchdogs bestätigt;
- Cloudverbindung wiederhergestellt, keine Testartefakte/Firewallregeln;
- lesender Live-Vorplan: `ready: true`, keine Blocker;
- Live-OTA_INFO: CRC gültig, Offset 0, Länge 0;
- echter Live-Cancel im Runtime-Helfer: weiterhin gesperrt;
- Mainboardtest: **noch nicht ausgeführt**.

Der nächste bewusste Schritt ist damit ausschließlich der oben beschriebene
Mainboard-Schreibtest nach erneuter passiver Sendepause und ausdrücklicher
Freigabe. Bis dahin bleibt `live_send_enabled: false`.
