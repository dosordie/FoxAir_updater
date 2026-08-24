# Firmwaremanifest

Jeder Firmwarelauf verwendet eine Manifestdatei als zentrale Quelle für die
Firmwaremetadaten, die der Updater für Prüfung, Vorbereitung und OTA-Handshake
verwendet. Der Controller enthält keine fest eingebauten Werte für V3.3 oder
eine zukünftige V3.4.

Wichtig ist die Trennung zwischen:

1. Werten, die direkt aus der Firmwaredatei stammen oder daraus berechnet
   werden,
2. Werten, die derzeit vom Benutzer bzw. aus bekanntem Projektwissen vorgegeben
   werden,
3. Werten, die das Tool daraus ableitet.

Das Manifest ist deshalb **nicht automatisch eine vollständige Beschreibung des
Inhalts der BIN**. Insbesondere `software_code` und `display_version` werden vom
aktuellen Manifest-Generator noch nicht aus der Firmware extrahiert.

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

| Feld | Herkunft im aktuellen Tool | Bedeutung |
|---|---|---|
| `schema` | feste Tool-/Projektkonstante | Manifestformat, aktuell `foxair-firmware-v1` |
| `firmware_file` | Dateiname der übergebenen Firmware | Name der zum Manifest gehörenden BIN |
| `software_code` | **manuell über `--software-code`** | 8-stellige Mainboard-/Softwarekennung für den OTA-Handshake |
| `display_version` | **manuell über `--display-version`** | menschenlesbare Version, z. B. `V3.3` |
| `wire_version` | aus `display_version` abgeleitet | Bus-/Handshake-Darstellung, z. B. `V3.3` -> `0033` |
| `target_ssid` | **manuell über `--target-ssid`** | OTA-/Zielparameter, derzeit nicht aus der BIN extrahiert |
| `size` | direkt aus der Firmwaredatei | tatsächliche Dateigröße in Byte |
| `md5` | über die komplette Firmwaredatei berechnet | Hash für Original-OTA/Dateiprüfung |
| `sha256` | über die komplette Firmwaredatei berechnet | zusätzlicher starker Hash für unsere lokale Integritätsprüfung |
| `image_base` | Standardwert/Projektwissen, derzeit `0x08050000` | erwartete Link-/Imagebasis der Mainboard-Firmware |

Damit stammen im aktuellen `create_firmware_manifest.py` tatsächlich nur diese
Werte direkt aus der Datei bzw. werden daraus berechnet:

```text
firmware_file
size
md5
sha256
```

Von außen vorgegeben werden derzeit:

```text
software_code
display_version
target_ssid
```

Daraus wird anschließend erzeugt:

```text
wire_version
```

`schema` und die standardmäßige `image_base` stammen aus dem Tool bzw. aus
bekanntem Projektwissen.

## Aktuelles Verhalten des Manifest-Generators

Ein Entwurf für eine neue Firmware wird z. B. erzeugt mit:

```bash
python3 tools/phnix_ota/create_firmware_manifest.py \
  --firmware FW3.4.bin \
  --software-code 82400644 \
  --display-version V3.4 \
  --target-ssid 0063 \
  --output FW3.4.json
```

Der Generator liest die komplette Firmwaredatei und berechnet daraus:

```text
size
MD5
SHA-256
```

Aus `--display-version V3.4` wird zusätzlich automatisch:

```text
wire_version = 0034
```

erzeugt.

Das Tool prüft derzeit nur Format und innere Konsistenz dieser Metadaten. Es
prüft **noch nicht**, ob der angegebene `software_code` oder die angegebene
`display_version` tatsächlich mit der intern in der Mainboard-Firmware
enthaltenen Softwarekennung übereinstimmen.

Damit wäre technisch beispielsweise ein Manifest möglich, das eine V3.4
behauptet, obwohl die übergebene BIN intern weiterhin V3.3 enthält. Größe und
Hashes würden trotzdem korrekt zur Datei passen.

## Warum diese Trennung beim OTA wichtig ist

Beim Mainboard-OTA sind mindestens drei verschiedene Informationsquellen zu
unterscheiden:

```text
1. Angebots-/Handshake-Metadaten
   software_code + wire_version
   -> werden beim Start des OTA über C350 verwendet

2. Binärintegrität
   size + MD5
   -> werden über C357 bzw. für die Firmwareprüfung verwendet

3. tatsächlich laufende Firmwareidentität
   -> wird vom Mainboard aus der laufenden Firmware selbst gemeldet
      und später über den Service-/Versionspfad wieder gelesen
```

Der C350-Vorhandshake entscheidet also anhand der **angebotenen Metadaten**, ob
das Mainboard die angebotene Version als identisch oder als abweichenden Build
betrachtet. Diese Metadaten werden nicht einfach dauerhaft als neue
Firmwareidentität in die BIN geschrieben.

Die tatsächlich laufende Software besitzt ihre eigene Software-/Versionskennung
im Firmwarecode. Nach einem erfolgreichen Update meldet das Mainboard daher
wieder die Kennung der tatsächlich gestarteten Firmware.

Das ist insbesondere für Tests relevant: Eine absichtlich geänderte
Handshake-Version kann den `same version`-Vergleich beeinflussen, ohne den
Inhalt der Firmwaredatei selbst zu verändern. Solche Overrides dürfen deshalb
nicht versehentlich durch ein falsch gepflegtes Produktionsmanifest entstehen.

## Validierung durch den Updater

Vor ADB-Zugriff oder Busaktivität prüft das Tool derzeit mindestens:

```text
Schema
Feldformate
wire_version-Ableitung aus display_version
Dateiname
Dateigröße
MD5
SHA-256
image_base
```

Beim Bereitstellen auf dem Modem wird MD5 zusätzlich über die kopierte und die
lokal per HTTP ausgelieferte Datei geprüft.

Die Manifestwerte werden anschließend zur Erzeugung des Original-`0033`-Auftrags
und der erwarteten persistenten OTA-Metadaten verwendet.

Wichtig:

> Eine formal gültige Manifestdatei beweist derzeit noch nicht, dass
> `software_code`, `display_version` und `target_ssid` aus dem Inhalt der BIN
> stammen oder zu diesem Inhalt passen.

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

für Firmware V3.3 verwechselt werden. Beide Werte sehen im V3.3-Beispiel gleich
aus, haben aber eine völlig unterschiedliche Bedeutung.

## Referenzmanifest

Das bestätigte V3.3-Referenzmanifest liegt unter:

```text
firmware_manifests/FW3.3.json
```

Eine neue Firmware erhält erst nach eigener Firmwareanalyse und Hashprüfung ein
freigegebenes Manifest.

Dabei sind vor einer Livefreigabe mindestens unabhängig zu prüfen:

```text
Softwarecode
interne Firmwareversion
Imagebasis
Ziel/Mainboard-Kompatibilität
Dateigröße
MD5
SHA-256
```

## Geplante Verbesserung

Langfristig sollte der Manifest-Generator die bekannten Firmwareidentitäten
nicht mehr ausschließlich als Benutzereingabe übernehmen, sondern – soweit das
Firmwareformat eindeutig rekonstruiert ist – direkt aus der BIN extrahieren und
gegen optionale Sollwerte prüfen.

Zielbild:

```text
Firmwaredatei
  -> Softwarecode extrahieren
  -> Firmwareversion extrahieren
  -> wire_version daraus ableiten
  -> Imagebasis plausibilisieren
  -> Größe / MD5 / SHA-256 berechnen
  -> Manifest erzeugen
```

`target_ssid` bleibt davon getrennt ein OTA-/Laufzeitparameter, solange nicht
belegt ist, dass dieser Wert Teil der Firmwareidentität selbst ist.

Ein bewusstes Überschreiben der C350-Angebotsversion für Labor-/Regressionstests
sollte später – falls benötigt – als **expliziter Testmodus** implementiert
werden und nicht über ein scheinbar normales Produktionsmanifest erfolgen.
