# PHNIX OTA Updater – Safety-Hardening PR #1

Stand: 24. August 2026

Dieses Dokument hält den bewusst verkleinerten Umfang von PR #1 fest. Nach dem
ersten Review wurde entschieden, die Änderungen rund um **USB-/ADB-Ausfall nach
begonnenem C5A8, Remote-Supervisor und Post-C5A8-Recovery** nicht zusammen mit
den einfacheren Preflight-/Portabilitätsänderungen zu mergen.

Ziel von PR #1 ist deshalb:

> **Vorprüfungen und Beobachtung verbessern, ohne den bestehenden PHNIX-OTA-
> Lifecycle oder den Runtime-Cleanup nach C5A8 zu verändern.**

Der bekannte und bereits live getestete Gleichversionspfad bleibt weiterhin:

```text
0033 lokal injizieren
→ C350
→ Mainboard C36E Status 0
→ kein C357
→ kein C5A8
→ persistente LTE-Dateien wiederherstellen
```

Ein vollständiger Versionswechsel wurde weiterhin noch nicht live bis zum Ende
auf realer Hardware ausgeführt.

---

## 1. Was PR #1 absichtlich nicht mehr ändert

Eine erste Fassung des PR hatte im Runtime-Hook nach vorhandenem
`TRANSFER_STARTED` den bisherigen `SIGSTOP`-Cleanup übersprungen. Das verhinderte
zwar ein direktes Anhalten von `phnixIot4G`, erzeugte aber einen nicht vollständig
definierten Zwischenzustand:

```text
Cloud-Sperre möglicherweise aktiv
Watchdogs möglicherweise angehalten
GDB/gdbserver möglicherweise vorhanden
run.active / transfer-started bleiben gesetzt
Restore ist wegen transfer-started gesperrt
```

Diese Änderung wurde deshalb aus PR #1 wieder entfernt.

Der Runtime-Hook besitzt in PR #1 wieder exakt die bisherige Guarded-Hold-
Semantik. Ebenso enthält die neue Host-Safety-Schicht **keine eigene
Post-C5A8-Exception-/Cleanup-Logik**.

Die Untersuchung wird separat fortgeführt. Vor einem späteren PR #2 sollen am
realen LTE-Modem zunächst harmlose Prozess-Lifetime-Tests klären, was beim
Verlust von USB/ADB mit einer entkoppelten Remote-Shell, GDB und Kindprozessen
tatsächlich passiert.

Für PR #2 vorgesehen sind insbesondere:

```text
ADB-/USB-Prozess-Persistenztest auf realem LTE-Modem
entkoppelter Remote-Supervisor
passive Feststellung aktiv/terminal nach Hostverlust
sicherer Post-C5A8-Cleanup erst nach Terminalbeweis
Host-/ADB-/Helper-/GDB-Ausfalltests
```

---

## 2. Gemeinsamer Core bleibt für den OTA-Lifecycle autoritativ

Der bekannte Controller bleibt:

```text
tools/phnix_ota/phnix_local_ota_controller.py
```

Die zusätzliche Datei

```text
tools/phnix_ota/phnix_local_ota_controller_hardened.py
```

kopiert nicht mehr den kompletten `run_update()`-Loop. Stattdessen delegiert sie
den eigentlichen Lauf direkt an den bestehenden Core:

```text
Safety-Schicht
  ├─ Speicherplatz vorprüfen
  ├─ Statusereignisse passiv beobachten
  └─ originalen core.run_update() aufrufen
          ↓
      unveränderter OTA-Lifecycle
```

Damit existiert in PR #1 keine zweite Host-State-Machine für C350/C357/C5A8.
Insbesondere werden keine zusätzlichen `hold`, `stop`, `cancel` oder
Restore-Entscheidungen durch die Safety-Schicht eingeführt.

---

## 3. `--full` ist bei echten Linux-Updates Pflicht

Ein echter Linux-Updateaufruf verlangt:

```bash
./foxair-updater update FW3.4.json --full --confirm
```

Der Full-Abgleich analysiert die Firmware direkt vor ADB-/Busaktivität erneut
und vergleicht:

```text
schema
firmware_file
software_code
display_version
wire_version
target_ssid
size
md5
sha256
image_base
```

Damit soll verhindert werden, dass C350 eine Manifestidentität anbietet, die
nicht zur tatsächlich übertragenen Binärdatei gehört.

Windows führte diesen Full-Abgleich bereits im Sicherheitswrapper durch.

---

## 4. Harte C357-Größengrenze

Die bekannte Mainboardimplementierung akzeptiert bei C357 maximal:

```text
0x4B000 = 307200 Byte
```

Diese Grenze ist nun zentral im gemeinsamen `FirmwareManifest` verankert:

```text
size > 307200
→ Manifest ungültig
→ kein Update
```

Die Prüfung gilt damit für Linux und Windows vor einem echten Transfer.

---

## 5. Freier Speicher wird fail-closed geprüft

Für `/data` und `/cache` wird vor dem Full-Update geprüft, ob genug freier
Speicher für lokale Stagingdatei und PHNIX-Cache vorhanden ist.

Konservative Berechnung:

```text
verschiedene Dateisysteme:
    je Firmwaregröße + 1 MiB Reserve

gleiches Dateisystem:
    2 × Firmwaregröße + 1 MiB Reserve
```

Zu wenig Speicher beendet den Lauf vor dem eigentlichen OTA.

### Warum `df` auf dem Host geparst wird

Die erste Implementierung verwendete:

```text
df -k <pfad> | tail -n 1
```

und erwartete eine einzelne Datenzeile. Der ADB-Simulator emuliert jedoch keine
komplette Shell-Pipeline und lieferte Header plus Datenzeile zurück. Dadurch
wurde `Available` als Zahlenfeld interpretiert und sämtliche Full-Update-
VM-Szenarien brachen schon im Preflight ab.

Die robuste Implementierung ruft deshalb nur auf:

```text
df -k <pfad>
```

und sucht **auf dem Host von unten nach oben die letzte syntaktisch gültige
Datenzeile mit numerischen Blockfeldern**. Header oder zusätzliche Textzeilen
werden ignoriert.

Damit hängt die Sicherheitsprüfung weder von `tail` auf dem Zielgerät noch von
einer perfekten Shell-Pipeline-Emulation des Testtransports ab.

---

## 6. End-to-End-VM-Matrix wird CI-Pflicht

Die normalen Unit-Tests hatten den ursprünglichen `df`-Integrationsfehler nicht
erkannt. Deshalb reicht für diesen Bereich künftig ein grüner Mock-/Unit-Test
allein nicht aus.

PR #1 enthält eine echte Prozess-/ADB-Simulator-Matrix mit **24 Szenarien**:

```text
2 Basisfälle
  status
  restore-original

11 Full-Update-Szenarien
  success
  parser-rejected
  crc-error
  metadata-mismatch
  offset-backwards
  offset-overflow
  stall-c350
  stall-c5a8
  helper-exit
  success-without-step12
  same-version

6 Pre-C5A8-Handshake-Szenarien
  success
  wrong-status-1
  missing-status-2
  metadata-change
  c5a8-leak
  cancel-fail

5 Same-Version-Szenarien
  success
  status-1
  c357-leak
  c5a8-leak
  restore-mismatch
```

Die Matrix startet den realen Controllerprozess über den ADB-kompatiblen
Simulator. Dadurch durchläuft sie auch die neue Speicherprüfung und fängt
Integrationsfehler zwischen Controller und Simulator ab.

Merge-Ziel für PR #1:

```text
Unit-Tests grün
Shell-Syntax grün
VM-Matrix 24/24 erwartete Ergebnisse
```

---

## 7. Persistenter Host-Run-State bleibt rein informativ

Während eines normalen Full-Update-Laufs beobachtet die Safety-Schicht die
ohnehin vorhandenen Statusereignisse und schreibt zusätzlich:

```text
<state-dir>/<Zeitstempel>/run-state.json
```

Relevante Felder:

```text
phase
terminal
transfer_started
point_of_no_return
highest_confirmed_offset
software_code
wire_version
firmware_md5
firmware_size
```

Diese Datei **steuert keinen Mainboardzustand** und löst keinen `hold`, `stop`,
`cancel` oder Restore aus.

Sie wird unter anderem benötigt, um nach einem normalen `update` eindeutig
zwischen

```text
phase = same-version
```

und

```text
phase = success
```

zu unterscheiden.

---

## 8. Cache-Restore beim normalen Update mit gleicher Version

Der originale PHNIX-`0033`-Handler kann die vorhandene Datei

```text
/cache/phnixIot_device_OTA
```

bereits löschen, bevor das Mainboard mit C36E Status 0 auf eine gleiche Version
antwortet.

Vorher wurde beim normalen `update` nach Exit 0 nur der Pending-Marker des
Hostbackups gelöscht. Dadurch konnte die ursprüngliche Cache-Firmware trotz
Same-Version verschwunden bleiben.

Jetzt entscheidet der gespeicherte terminale Run-State:

```text
same-version
→ ursprünglichen Cache wiederherstellen

success
→ erfolgreichen neuen Cachezustand nicht überschreiben
```

Es wird bewusst nicht allein aus dem Vorhandensein oder Fehlen einer Cachedatei
auf den Terminalzustand geschlossen.

---

## 9. Passive C5A8-Beobachtung

Die Safety-Schicht darf Statusinformationen lesen und darstellen, ändert aber
nicht den bisherigen OTA-Lifecycle.

### Stall-Hinweis

Wenn während beobachtetem `c5a8` der CRC-gültige bestätigte Offset mindestens
60 Sekunden nicht steigt, wird nur eine Warnung ausgegeben:

```text
C5A8-Fortschritt unverändert
→ Warnung
→ kein eigener Timeout
→ kein Cancel
→ kein zusätzlicher Prozessbefehl
```

### 100 % Transport ist nicht automatisch Terminalzustand

Bei

```text
offset >= length
```

wird angezeigt, dass **100 % der Firmwarebytes übertragen** wurden. Die Anzeige
weist gleichzeitig darauf hin, dass das Mainboard intern noch programmieren und
verifizieren kann.

Der bestehende Core entscheidet weiterhin allein, wann der bisher bekannte
terminale Erfolgspfad erreicht wurde.

C544 wird in PR #1 weiterhin nicht als neue harte Erfolgsbedingung eingeführt.

---

## 10. Windows: Entwicklungs- und Releasepfad durch dieselben Safety-Schichten

Die gepackte Windows-Version verwendet bereits:

```text
GUI
→ Windows-Sicherheitswrapper
→ gemeinsame Safety-Schicht
→ bytegleicher Controller-Core
```

Im direkten Repository-Entwicklungsmodus wählte die GUI vorher dagegen den
Core unmittelbar aus. Damit wurden Wrapperfunktionen wie Full-Abgleich,
Cache-Backup/-Restore und stabiler Windows-Run-State umgangen.

PR #1 enthält deshalb einen kleinen Source-Mode-Backend-Router unter:

```text
backend/tools/phnix_ota/
```

Der bereits dokumentierte direkte GUI-Start kann damit denselben logischen
Backendpfad benutzen wie das Release. Kleine Source-Mode-Shims unter
`updater/windows/` reichen Aufrufe an die gemeinsamen Implementierungen unter
`tools/phnix_ota/` weiter; es entsteht keine zweite OTA-Implementierung.

---

## 11. LF-Pinning des extensionlosen Linux-Launchers

`.gitattributes` erzwingt bereits LF für Python-, Shell- und mehrere interne
Skripte. Der extensionlose Launcher

```text
foxair-updater
```

war davon nicht ausdrücklich erfasst.

PR #1 ergänzt:

```gitattributes
foxair-updater text eol=lf
```

Damit kann ein Windows-Checkout den Shebang-/Shell-Launcher nicht versehentlich
mit CRLF für eine spätere Nutzung unter WSL/Git Bash/Linux auschecken.

---

## 12. Bewusst auf PR #2 verschoben

Nicht Teil von PR #1 sind:

```text
kein neuer USB-/ADB-Ausfall-Lifecycle nach C5A8
kein entkoppelter Remote-Supervisor
kein neuer Post-C5A8-Recoverypfad
kein automatisches Aufräumen nach unbekanntem Hostverlust
keine neuen C36A/C36C-Breakpoints im Full-Update
kein eigener aktiver Cancel nach begonnenem C5A8
keine neuen RS485-Kommandos
keine neue C544-Erfolgsbedingung
```

Vor diesen Änderungen sollen reale, harmlose Prozess-Persistenztests auf dem
LTE-Modem durchgeführt werden.

---

## 13. Sicherheitsentscheidung für PR #1

Der verkleinerte PR folgt damit einer klaren Grenze:

```text
Preflight härten       → ja
Manifest härten        → ja
Tests härten           → ja
Status passiv beobachten → ja
Cache-Bookkeeping fixen  → ja
Windows-Pfade vereinheitlichen → ja

OTA-Lifecycle nach C5A8 verändern → nein, separat untersuchen
```

Damit bleiben weniger gleichzeitig veränderte Komponenten im ersten Merge und
die schwierigere USB-/ADB-/Recovery-Frage kann anschließend isoliert in PR #2
entwickelt und getestet werden.
