# Firmwaremanifest

Jeder Firmwarelauf verwendet eine Manifestdatei als zentrale Quelle für die
Firmwaremetadaten, die der Updater für Prüfung, Vorbereitung und OTA-Handshake
verwendet.

Für FoxAir gibt es jetzt drei sinnvolle Arbeitsweisen:

```text
Standardmodus
  -> SoftwareCode und Display-Version werden explizit angegeben

--full
  -> SoftwareCode und Wire-Version werden direkt aus der Mainboard-Firmware
     extrahiert
  -> Display-Version wird daraus abgeleitet
  -> Cortex-M-Image wird plausibilisiert
  -> Größe, MD5 und SHA-256 werden berechnet

--show
  -> erzeugt exakt dieselben Manifestdaten nur im Speicher
  -> gibt das JSON auf der Konsole aus
  -> schreibt keine Manifestdatei
```

`--full` und `--show` können kombiniert werden. Damit lässt sich eine neue
Firmware vollständig lesend analysieren, ohne eine JSON-Datei anzulegen.

Der Vollmodus arbeitet fail-closed: Wird keine eindeutige Firmwareidentität
gefunden, wird weder ein Manifest geschrieben noch eine Vorschau ausgegeben.

## Aufbau

Beispiel für das bestätigte V3.3-Format:

```json
{
  "schema": "foxair-firmware-v1",
  "firmware_file": "phnixIot_device_OTA",
  "software_code": "82400644",
  "display_version": "V3.3",
  "wire_version": "0033",
  "target_ssid": "0063",
  "size": 287598,
  "md5": "CEB6A4BF386FF644E23E410023E74673",
  "sha256": "6C635D8E9A1E7246EA492B81ACFF5B748E85CC86C0FE0DEF35C2F0A597E4389A",
  "image_base": "0x08050000"
}
```

## Herkunft der Felder

| Feld | Standardmodus | `--full` | Bedeutung |
|---|---|---|---|
| `schema` | Toolkonstante | Toolkonstante | Manifestformat `foxair-firmware-v1` |
| `firmware_file` | Firmware-Dateiname | Firmware-Dateiname | Name der BIN |
| `software_code` | `--software-code` | **aus BIN extrahiert** | 8-stellige Mainboard-/Softwarekennung |
| `display_version` | `--display-version` | aus `wire_version` abgeleitet | z. B. `V3.3` |
| `wire_version` | aus Display-Version | **aus BIN extrahiert** | z. B. `0033` |
| `target_ssid` | fest `0063` | fest `0063` | FoxAir Modbus Unit-ID `0x63` |
| `size` | aus Datei | aus Datei | tatsächliche Dateigröße |
| `md5` | berechnet | berechnet | Original-PHNIX-Dateihash |
| `sha256` | berechnet | berechnet | zusätzliche lokale Integritätsprüfung |
| `image_base` | fest/validiert `0x08050000` | fest/validiert `0x08050000` | erwartete Mainboard-Imagebasis |

## Firmwareidentität in der V3.3-BIN

Die analysierte V3.3-Firmware enthält die aktive Identität als 12 ASCII-Bytes:

```text
824006440033
```

Aufteilung:

```text
82400644   software_code
0033       wire_version
```

In der V3.3-Referenzdatei liegt diese Konstante bei:

```text
Datei-Offset: 0x42780
Flashadresse: 0x08092780
```

Der Vollmodus verwendet **nicht** diesen festen Offset. Eine neue Firmware darf
die Konstante an eine andere Stelle verschieben.

Stattdessen sucht der Generator nach dem rekonstruierten Format:

```text
8 ASCII-Zeichen SoftwareCode
+
4-stellige nicht-null Wire-Version im Format 00xy
```

Die V3.3 enthält direkt daneben noch die andere code-referenzierte Konstante:

```text
823003140000
```

Da deren Versionsanteil `0000` ist, wird sie nicht als laufende
Firmwareidentität akzeptiert.

Werden kein oder mehrere gültige nicht-null Kandidaten gefunden, bricht
`--full` ab. Das Tool rät nicht und verwendet nicht automatisch den ersten
Treffer.

## `display_version` wird nicht separat aus der BIN gelesen

Ein ASCII-String `V3.3` ist in der V3.3-BIN nicht vorhanden. Die sichtbare
Version wird aus der Wire-Version erzeugt:

```text
0033 -> V3.3
0034 -> V3.4
```

## `target_ssid = 0063` ist die Modbus-Adresse

Die als `target_ssid` bezeichnete Manifestangabe entspricht beim FoxAir-Pfad
der festen Modbus-Unit-ID des Mainboards:

```text
0x63 -> Manifest/0033-Darstellung "0063"
```

Deshalb gilt für dieses Repository:

```text
target_ssid muss 0063 sein
```

## Vollmodus: Manifest aus einer Source-Firmware erzeugen

Liegt eine neue Firmware im lokalen Ordner `firmware/`:

```bash
./foxair-updater manifest FW3.4.bin --full
```

Das Ergebnis wird standardmäßig neben der Firmware geschrieben:

```text
firmware/FW3.4.bin
-> firmware/FW3.4.json
```

## Read-only Vorschau mit `--show`

Soll die Firmware nur analysiert und das resultierende Manifest angesehen
werden, ohne eine Datei zu erzeugen:

```bash
./foxair-updater manifest FW3.4.bin --full --show
```

Der Befehl liest ausschließlich die lokale Firmwaredatei, führt dieselbe
Firmwareanalyse wie beim echten Manifest-Erstellen aus und gibt anschließend
das vollständige JSON auf stdout aus.

Beispielausgabe:

```json
{
  "schema": "foxair-firmware-v1",
  "firmware_file": "FW3.4.bin",
  "software_code": "82400644",
  "display_version": "V3.4",
  "wire_version": "0034",
  "target_ssid": "0063",
  "size": 123456,
  "md5": "...",
  "sha256": "...",
  "image_base": "0x08050000"
}
```

Dabei wird **keine `.json`-Datei geschrieben**. `--show` ist damit besonders
geeignet, um eine unbekannte Firmware zunächst nur lesend zu prüfen.

Auch der Standardmodus kann so nur als Vorschau verwendet werden:

```bash
./foxair-updater manifest FW3.4.bin \
  --software-code 82400644 \
  --display-version V3.4 \
  --show
```

Der direkte Python-Aufruf funktioniert ebenfalls:

```bash
python3 tools/phnix_ota/create_firmware_manifest.py \
  --firmware firmware/FW3.4.bin \
  --full \
  --show
```

`--show` und `--output` schließen sich gegenseitig aus.

## Zusätzliche Sollwerte im Vollmodus

`--software-code` und `--display-version` dürfen zusammen mit `--full`
angegeben werden. Sie werden dann nicht als Override benutzt, sondern als
zusätzliche Erwartungswerte. Weicht die BIN davon ab, bricht das Tool ab.

## Cortex-M-Plausibilisierung im Vollmodus

Vor der Identitätsextraktion prüft `--full` zusätzlich:

```text
Initial Stack Pointer -> plausibler SRAM-Bereich 0x20000000...
Reset Vector          -> Thumb-Adresse innerhalb des Images
Image Base            -> 0x08050000
```

## Vollprüfung unmittelbar vor einem Update

Die Firmwareidentität kann vor einem echten Lauf nochmals gegen das vorhandene
Manifest geprüft werden:

```bash
./foxair-updater update FW3.4.json --full --confirm
```

Diese Vollprüfung findet vor ADB- und Busaktivität statt.

## Warum diese Trennung beim OTA wichtig ist

Beim Mainboard-OTA sind mindestens drei verschiedene Informationsquellen zu
unterscheiden:

```text
1. Angebots-/Handshake-Metadaten
   software_code + wire_version
   -> C350

2. Binärintegrität
   size + MD5
   -> C357 / lokale Dateiprüfung

3. tatsächlich laufende Firmwareidentität
   -> stammt aus dem laufenden Mainboard-Firmwarecode
```

## `0033` ist nicht die Firmwareversion

Der oberste JSON-Code `0033` ist eine Protokollkonstante für einen
Mainboard-OTA-Auftrag. Er darf nicht mit `wire_version = 0033` für Firmware
V3.3 verwechselt werden.

## Referenzmanifest

Das bestätigte V3.3-Referenzmanifest liegt unter:

```text
firmware_manifests/FW3.3.json
```

Für neue Firmwarestände ist ein sinnvoller erster, vollständig lokaler Schritt:

```bash
./foxair-updater manifest DATEI.bin --full --show
```

Erst wenn die erkannten Werte plausibel sind, kann anschließend mit demselben
Analysemotor eine echte Manifestdatei erzeugt werden:

```bash
./foxair-updater manifest DATEI.bin --full
```
