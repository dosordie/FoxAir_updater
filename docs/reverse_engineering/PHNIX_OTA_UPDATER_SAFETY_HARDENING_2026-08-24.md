# PHNIX OTA Updater – Safety-Hardening vor dem ersten Versionswechsel

Stand: 24. August 2026

Dieses Dokument beschreibt die Sicherheitsänderungen, die nach einer erneuten
End-to-End-Prüfung des realen Mainboard-OTA-Pfads vorgenommen wurden. Ziel war
**nicht**, den PHNIX-OTA-Ablauf neu zu entwerfen, sondern ausschließlich
zusätzliche Fehlerquellen unseres Host-Updaters zu entfernen.

Der bekannte und bereits live getestete Gleichversionspfad bleibt unverändert:

```text
0033 lokal injizieren
→ C350
→ Mainboard C36E Status 0
→ kein C357
→ kein C5A8
→ persistente LTE-Dateien wiederherstellen
```

Der vollständige Versionswechsel ist weiterhin nicht live an realer Hardware
bis zum Ende ausgeführt worden.

---

## 1. Sicherheitsgrenze: erster C5A8

Für den Launcher existieren zwei grundlegend unterschiedliche Zustände.

### Vor dem ersten C5A8

Bis zu diesem Punkt ist ein Fail-Closed-Halt weiterhin sinnvoll:

```text
C350 / C357 / Vorbereitung
→ Fehler im Host/Helper
→ phnixIot4G darf kontrolliert angehalten werden
→ kein weiterer OTA-Schritt läuft unkontrolliert weiter
```

Vor C5A8 kann noch kein Firmwareblock durch unseren Full-Update-Pfad in den
Stagingbereich des Mainboards übertragen worden sein.

### Ab dem ersten C5A8

Sobald der Runtime-Hook den ersten C5A8-Sendepfad erreicht, wird weiterhin der
bestehende Marker gesetzt:

```text
/tmp/phnix_ota_hook/transfer-started
```

Ab diesem Zeitpunkt gilt die entgegengesetzte Regel:

> **Der originale `phnixIot4G`-Dienst ist für den laufenden Board-OTA
> autoritativ und darf durch einen Host-/ADB-/Helperfehler nicht mehr per
> `SIGSTOP` angehalten werden.**

Der Grund: Firmwaredatei und OTA-Metadaten liegen zu diesem Zeitpunkt bereits
auf dem LTE-Modem; der weitere C5A8/C371-Verkehr findet direkt zwischen
`phnixIot4G` und dem Mainboard über RS485 statt. Raspberry Pi, Debian-PC oder
Windows-PC sind für den eigentlichen Blocktransport nicht erforderlich.

---

## 2. Behobener USB-/ADB-Ausfallpfad

### Vorher

Der Runtime-Hook hatte für jeden nichtterminalen `EXIT/INT/TERM` denselben
Cleanup:

```text
RUN_ACTIVE && !SAFE_TO_CLEAN
→ kill -STOP phnixIot4G
→ guarded-hold
```

Damit konnte ein Verlust der ADB-Shell nach bereits begonnenem C5A8 den
Originaldienst anhalten und dadurch einen ansonsten selbständig laufenden
Mainboardtransfer unterbrechen.

Zusätzlich versuchte auch der Host-Controller bei einem nichtterminalen Fehler
pauschal den Helper-Befehl `hold` auszuführen.

### Jetzt

Der Zustand wird an `TRANSFER_STARTED` getrennt:

```text
vor C5A8:
    bisheriger guarded-hold bleibt unverändert

nach C5A8:
    kein SIGSTOP von phnixIot4G
    kein Host-seitiger hold-Befehl
    Originaldienst läuft weiter
    Status = transfer-unattended / host-supervision-lost
```

Es wurden dafür **keine** neuen RS485-Kommandos, kein neuer Cancel und keine
neuen GDB-Breakpoints eingeführt.

Die Cloud-/Watchdog-Behandlung wurde absichtlich nicht zusätzlich umgebaut.
Der Patch soll nur verhindern, dass unser eigener Fehler den bereits laufenden
Original-OTA stoppt.

---

## 3. Unveränderter Controller-Core + gemeinsame Safety-Schicht

Der bisher verifizierte Controller bleibt als Protokoll-Core erhalten:

```text
tools/phnix_ota/phnix_local_ota_controller.py
```

Neu ist eine plattformübergreifende Host-Sicherheitsschicht:

```text
tools/phnix_ota/phnix_local_ota_controller_hardened.py
```

Sie übernimmt nur:

```text
Speicherplatz-Preflight
persistenten Host-Run-State
passive C5A8-Stallwarnung
100-%-/Promotion-Anzeige
Post-C5A8-Hostfehlerregel
```

Linux startet diese Safety-Schicht direkt. Im Windows-Portable-Build bleibt der
bisherige Controller bytegleich als
`phnix_local_ota_controller_core.py` erhalten; die gleiche Safety-Schicht liegt
davor. Damit wird die sicherheitsrelevante Post-C5A8-Logik nicht getrennt für
Linux und Windows implementiert.

---

## 4. Vollanalyse bei echten Updates ist Pflicht

Ein echter Linux-Updateaufruf verlangt jetzt:

```bash
./foxair-updater update FW3.4.json --full --confirm
```

`--full` ist nicht mehr optional.

Damit wird unmittelbar vor ADB-/Busaktivität die Firmware erneut analysiert und
mit dem Manifest verglichen:

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

Der Windows-Updater führte diesen Full-Abgleich bereits automatisch aus; dieses
Verhalten bleibt bestehen.

Ziel ist, dass C350 niemals mit einer Manifestidentität angeboten wird, die
nicht zur tatsächlich übertragenen Binärdatei gehört.

---

## 5. Harte C357-Größengrenze

Die bekannte V3.3-Mainboard-Firmware akzeptiert bei C357 maximal:

```text
0x4B000 = 307200 Byte
```

Diese Grenze ist nun direkt im gemeinsamen `FirmwareManifest` verankert:

```text
size > 307200
→ Manifest ungültig
→ kein Update
```

Sie gilt dadurch für Linux und Windows bereits vor dem eigentlichen OTA-Lauf.

---

## 6. Freier Speicher als echte Stopbedingung

Bisher wurde `df -k /cache /data` nur protokolliert. Ein zu voller Datenträger
konnte deshalb theoretisch erst beim Staging oder beim PHNIX-HTTP-Download
auffallen.

Die Safety-Schicht prüft jetzt den tatsächlich freien Speicher vor einem Full
Update.

Benötigt werden mindestens:

```text
wenn /data und /cache verschiedene Dateisysteme sind:
    je Dateisystem Firmwaregröße + 1 MiB Sicherheitsreserve

wenn /data und /cache dasselbe Dateisystem sind:
    2 × Firmwaregröße + 1 MiB Sicherheitsreserve
```

Der zweite Fall berücksichtigt konservativ die lokale Stagingkopie unter
`/data/phnix_local_ota/` und die PHNIX-Cachedatei unter `/cache/`.

Bei zu wenig freiem Speicher wird vor dem Update abgebrochen.

---

## 7. Persistenter Host-Run-State

Der Modemmarker `transfer-started` liegt unter `/tmp` und ist daher allein kein
dauerhafter Nachweis, ob der Point-of-no-return in einem früheren Lauf erreicht
wurde.

Für jeden Full-Update-Lauf wird deshalb zusätzlich auf dem Host geschrieben:

```text
<state-dir>/<Zeitstempel>/run-state.json
```

Schema:

```text
foxair-ota-run-state-v1
```

Relevante Felder sind unter anderem:

```text
phase
transfer_started
point_of_no_return
highest_confirmed_offset
software_code
wire_version
firmware_md5
firmware_size
updated_at
```

Nach einem Host-/ADB-Verlust nach C5A8 wird beispielsweise gespeichert:

```text
phase = host-supervision-lost
transfer_started = true
point_of_no_return = true
```

Die Datei ist **rein informativ**. Sie löst keine Boardaktion aus.

Linux verwendet den bestehenden Ordner:

```text
phnix-ota-state/
```

Windows verwendet einen stabilen Benutzerpfad unter:

```text
%LOCALAPPDATA%\FoxAir Updater\ota-state\
```

Die Implementierung verwendet Python `pathlib` und funktioniert dadurch auf
beiden Plattformen ohne Linux-spezifische Pfadlogik.

---

## 8. Passive C5A8-Stallwarnung

Der Full-Update-Controller besitzt weiterhin **keinen automatischen
C5A8-Abbruchtimeout**. Das ist absichtlich so: Ab dem ersten Firmwareblock soll
der Host nicht eigenmächtig in die Original-State-Machine eingreifen.

Neu ist nur eine Beobachtung des ohnehin bereits gelesenen, CRC-gültigen
`OTA_INFO.offset`.

Wenn der bestätigte Offset mindestens 60 Sekunden nicht steigt:

```text
WARNUNG: C5A8-Fortschritt unverändert
Originaldienst läuft weiter
kein automatischer Eingriff
```

Die Warnung:

- sendet kein RS485-Frame,
- setzt keinen Mainboardzustand,
- stoppt keinen Prozess,
- löst keinen Cancel aus.

Sie macht lediglich einen möglichen Transferstillstand sichtbar.

---

## 9. 100 % bedeutet Transportende, nicht Updateende

Ein bestätigter Offset gleich `fileSize` bedeutet zunächst nur:

```text
alle C5A8-Firmwarebytes wurden vom Mainboard angenommen
```

Danach folgen auf Mainboardseite weiterhin unter anderem:

```text
Staging-MD5
Promotion / Target-Programmierung
zweite MD5-Prüfung
Candidate-/Commitpfad
```

Die Benutzeranzeige unterscheidet das jetzt ausdrücklich:

```text
100 % Firmware übertragen
→ Mainboard programmiert und verifiziert intern weiter
```

Erst der bereits vorhandene terminale PHNIX-Erfolgspfad wird weiterhin als
Abschluss des aktuellen Updaterlaufs behandelt.

Es wurde **noch keine** neue harte C544-Nachprüfung eingeführt, weil der genaue
Zeitpunkt eines C544 nach dem ersten realen Versionswechsel noch nicht live
beobachtet wurde.

---

## 10. Cache-Restore beim normalen Update mit gleicher Version

Ein angenommenes Cloudkommando `0033` löscht die vorhandene Datei:

```text
/cache/phnixIot_device_OTA
```

bereits vor dem C350-Ergebnis.

Beim dedizierten `same-version`-Befehl wurde das Originalcache-Backup deshalb
bereits zurückgespielt. Beim normalen `update`-Pfad bestand dagegen ein
Sonderfall:

```text
update mit gleicher Firmware
→ 0033 löscht Cache
→ C36E Status 0
→ Controller Exit 0
→ Cache-Backup-Marker wurde nur gelöscht
```

Damit blieb die zuvor vorhandene Cachedatei verschwunden.

Jetzt wird nach einem erfolgreichen normalen Update der **persistente
Host-Run-State** ausgewertet:

```text
phase = same-version
→ ursprünglichen Cache exakt wiederherstellen

phase = success
→ neuen/aktuellen Cachezustand unverändert lassen
```

Es wird bewusst **nicht** allein aus dem Vorhandensein oder Fehlen der
Cachedatei auf Erfolg oder Same-Version geschlossen.

Diese Logik ist für Linux und Windows umgesetzt.

---

## 11. Bewusst nicht geändert

Diese Überarbeitung fügt ausdrücklich **nicht** hinzu:

```text
keinen zusätzlichen GDB-Halt unmittelbar vor C5A8
keine neue OTA_INFO-Blockade im Runtimepfad
keine neuen C36A/C36C-Breakpoints im Full-Update
keinen aktiven eigenen Cancel nach begonnenem C5A8
keine neuen RS485-Kommandos
keine Änderung des C350/C357/C5A8/C371-Wireformats
keinen neuen C544-Zwang als Erfolgsbedingung
keinen großen Helper-/Daemon-Umbau
```

Der bereits analysierte Originalpfad soll damit so wenig wie möglich verändert
werden.

---

## 12. Stromausfall

Diese Änderungen behaupten nicht, das Power-Loss-Verhalten des residenten
Mainboard-Loaders zu lösen. Ein Stromausfall während Target-Erase oder Copy ist
eine grundsätzliche Eigenschaft des PHNIX-Firmwareupdatepfads und kann ebenso
bei einem regulären Hersteller-/Cloud-OTA auftreten.

Das Ziel dieses Hardening-Patches ist enger:

> **Unser lokaler Updater soll gegenüber dem Original-OTA keine zusätzliche
> Ausfallursache erzeugen.**

Insbesondere soll ein Ausfall von USB, ADB oder Host nach begonnenem C5A8 nicht
zusätzlich den weiterhin lokal laufenden Originaldienst stoppen.

---

## 13. Tests / Reviewgrenzen

Zusätzliche Tests prüfen unter anderem:

```text
C357-Maximalgröße
Speicherplatzberechnung bei gemeinsamen/getrennten Dateisystemen
plattformneutralen JSON-Run-State
100-%-/Promotion-Ausgabe
kein SIGSTOP im Runtime-Cleanup nach TRANSFER_STARTED
kein Host-hold nach erkanntem Point-of-no-return
Linux --full Pflicht
Linux-/Windows-Cacheentscheidung anhand des Run-State
stabilen Windows-OTA-State-Pfad
```

Die vorhandenen Tests für Manifest, OTA-Frames, Controller, Simulator und
Runtimeprofil bleiben zusätzlich bestehen.

---

## 14. Sicherheitsentscheidung

Mit diesem Patch wird die Hostseite konservativer, ohne die bisher
rekonstruierte PHNIX-State-Machine zu erweitern:

```text
vor C5A8:
    fail closed / guarded hold

erster C5A8:
    point of no return markieren

danach:
    Original-phnixIot4G niemals wegen Hostfehler anhalten
    nur beobachten und protokollieren
```

Damit ist insbesondere der zuvor identifizierte USB-/ADB-Ausfallpfad entschärft,
ohne einen neuen Recoveryalgorithmus in den Mainboard-OTA einzuführen.
