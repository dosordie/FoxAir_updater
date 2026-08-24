# Firmwaremanifest

Jeder Firmwarelauf verwendet eine Manifestdatei als zentrale Quelle für die
Firmwaremetadaten, die der Updater für Prüfung, Vorbereitung und OTA-Handshake
verwendet.

Für FoxAir gibt es jetzt zwei Erzeugungs-/Prüfmodi:

```text
Standardmodus
  -> SoftwareCode und Display-Version werden explizit angegeben

--full
  -> SoftwareCode und Wire-Version werden direkt aus der Mainboard-Firmware
     extrahiert
  -> Display-Version wird daraus abgeleitet
  -> Cortex-M-Image wird plausibilisiert
  -> Größe, MD5 und SHA-256 werden berechnet
```

Der Vollmodus ist für neue, unbekannte Firmwarestände der bevorzugte Weg. Er
arbeitet fail-closed: Wird keine eindeutige Firmwareidentität gefunden, wird
kein Manifest erzeugt.

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

Damit stammen im Vollmodus sowohl SoftwareCode als auch die eigentliche
Firmware-Wire-Version aus dem Image; die menschenlesbare Schreibweise wird nur
abgeleitet.

## `target_ssid = 0063` ist die Modbus-Adresse

Die bisher als `target_ssid` bezeichnete Manifestangabe ist beim FoxAir-Pfad
keine aus der Firmware zu extrahierende Versionsinformation. Sie entspricht der
festen Modbus-Unit-ID des Mainboards:

```text
0x63 -> Manifest/0033-Darstellung "0063"
```

Das passt zu den rekonstruierten OTA-Telegrammen. C350, C357, C36E, C371,
C5A8, C36A und C37B werden auf dem FoxAir-LTE-RS485-Pfad mit Unit-ID `0x63`
gesendet bzw. empfangen.

Deshalb gilt für dieses Repository jetzt:

```text
target_ssid muss 0063 sein
```

Der Manifest-Validator lehnt andere Werte ab. Auch der Generator verwendet
`0063` automatisch; `--target-ssid` ist nur noch aus Kompatibilitätsgründen
vorhanden und darf keinen anderen Wert enthalten.

## Vollmodus: Manifest direkt aus einer Source-Firmware erzeugen

Liegt eine neue Firmware im lokalen Ordner `firmware/`, kann das Manifest über
den Quick-Setup-Befehl erzeugt werden:

```bash
./foxair-updater manifest FW3.4.bin --full
```

Wird nur der Dateiname angegeben, sucht `foxair-updater` automatisch in:

```text
./firmware/
```

Das Ergebnis wird standardmäßig neben der Firmware mit gleichem Basisnamen
geschrieben:

```text
firmware/FW3.4.bin
-> firmware/FW3.4.json
```

Der direkte Python-Aufruf lautet:

```bash
python3 tools/phnix_ota/create_firmware_manifest.py \
  --firmware firmware/FW3.4.bin \
  --full \
  --output firmware/FW3.4.json
```

Der Generator meldet dabei die erkannte Identität samt Fundstelle, z. B.:

```text
detected firmware identity: software_code=82400644 wire_version=0033 display_version=V3.3 offset=0x42780
```

### Zusätzliche Sollwerte im Vollmodus

`--software-code` und `--display-version` dürfen zusammen mit `--full`
angegeben werden. Sie werden dann **nicht als Override** benutzt, sondern als
zusätzliche Erwartungswerte.

Beispiel:

```bash
./foxair-updater manifest FW3.4.bin --full \
  --software-code 82400644 \
  --display-version V3.4
```

Weicht die BIN davon ab, bricht das Tool ab.

## Cortex-M-Plausibilisierung im Vollmodus

Vor der Identitätsextraktion prüft `--full` zusätzlich die ersten beiden
Vektortabellenwerte:

```text
Initial Stack Pointer -> plausibler SRAM-Bereich 0x20000000...
Reset Vector          -> Thumb-Adresse innerhalb des Images
Image Base            -> 0x08050000
```

Damit soll vermieden werden, dass eine falsche Datei nur aufgrund eines
zufälligen ASCII-Treffers ein scheinbar gültiges Manifest erhält.

Die Prüfung ersetzt keine vollständige Firmwareanalyse, ist aber eine weitere
fail-closed Hürde.

## Standardmodus bleibt kompatibel

Ein Manifest kann weiterhin explizit erzeugt werden:

```bash
./foxair-updater manifest FW3.4.bin \
  --software-code 82400644 \
  --display-version V3.4
```

`target_ssid` muss nicht mehr angegeben werden; für FoxAir wird automatisch
`0063` verwendet.

Der direkte Python-Aufruf funktioniert analog.

## Vollprüfung unmittelbar vor einem Update

Zusätzlich zum Erzeugen eines Manifests kann der Quick-Setup-Updater die
Firmwareidentität unmittelbar vor einem echten Lauf nochmals unabhängig gegen
das vorhandene Manifest prüfen:

```bash
./foxair-updater update FW3.4.json --full --confirm
```

Der Ablauf ist dann:

```text
Manifest laden
-> firmware_file aus Manifest bestimmen
-> Firmware neben dem Manifest oder unter ./firmware/ suchen
-> create_firmware_manifest.py --full auf genau diese BIN anwenden
-> alle Manifestfelder vergleichen:
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
-> nur bei vollständiger Übereinstimmung ADB-/Updatepfad starten
```

Die Vollprüfung findet damit **vor ADB- und Busaktivität** statt.

Ohne `--full` bleibt der bisherige Aufruf erhalten:

```bash
./foxair-updater update FW3.4.json --confirm
```

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

Der C350-Vorhandshake entscheidet anhand der angebotenen Metadaten, ob das
Mainboard die angebotene Version als identisch oder abweichend betrachtet.
Deshalb ist die `--full`-Prüfung sinnvoll: Ein normales Produktionsmanifest
soll nicht versehentlich eine andere Version behaupten als die zugehörige BIN.

## `0033` ist nicht die Firmwareversion

Der oberste JSON-Code:

```text
0033
```

ist eine Protokollkonstante für einen Mainboard-OTA-Auftrag.

Er darf nicht mit:

```text
wire_version = 0033
```

für Firmware V3.3 verwechselt werden. Im V3.3-Beispiel sehen beide Werte nur
zufällig gleich aus.

## Referenzmanifest

Das bestätigte V3.3-Referenzmanifest liegt unter:

```text
firmware_manifests/FW3.3.json
```

Für neue Firmwarestände ist der bevorzugte erste Schritt:

```bash
./foxair-updater manifest DATEI.bin --full
```

Ein bewusstes Überschreiben der C350-Angebotsversion für Labor-/Regressionstests
sollte weiterhin als separater expliziter Testmodus behandelt werden und nicht
über ein normales Produktionsmanifest erfolgen.
