# Firmwaremanifest

Stand: 29. August 2026

> [!NOTE]
> Für Windows steht dieselbe Manifest-Logik direkt in der **FoxAir-Updater-GUI** zur Verfügung. Öffentliche Windows-Versionen gibt es unter [GitHub Releases](https://github.com/dosordie/FoxAir_updater/releases).
>
> Der vollständige Firmwarewechsel **V3.3 → V3.4** wurde auf realer Hardware erfolgreich durchgeführt. Der dabei verwendete V3.4-Datensatz wurde vor dem Lauf über das Manifest geprüft und nach dem Update über C36E Status 5 / Board-Step 12 sowie C544-Version `0034` bestätigt.

Jeder Firmwarelauf verwendet eine Manifestdatei als zentrale Quelle für die Firmwaremetadaten, die der Updater für Prüfung, Vorbereitung und OTA-Handshake benötigt.

Das Manifest ersetzt keine Herstellersignatur. Es stellt sicher, dass die ausgewählte Datei exakt zu den lokal erwarteten Metadaten und Prüfsummen passt.

## Arbeitsweisen

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

`--full` und `--show` können kombiniert werden. Damit lässt sich eine neue Firmware vollständig lesend analysieren, ohne eine JSON-Datei anzulegen.

Der Vollmodus arbeitet fail-closed: Wird keine eindeutige Firmwareidentität gefunden, wird weder ein Manifest geschrieben noch eine Vorschau erzeugt.

## Windows-GUI

Auf der Registerkarte **Manifest** stehen die gleichen Funktionen ohne Python-/PowerShell-Bedienung bereit:

1. originale Firmwaredatei auswählen – sie muss keine `.bin`-Endung besitzen;
2. **Vorschau aus Firmware (Full / Show)** ausführen;
3. erkannte Werte prüfen;
4. **Manifest automatisch erzeugen (Full)** verwenden;
5. das erzeugte Manifest im Firmware-Update-Tab verwenden.

Intern werden dieselben Werkzeuge verwendet:

```text
create_firmware_manifest.py --firmware FIRMWARE --full --show
create_firmware_manifest.py --firmware FIRMWARE --full --output FIRMWARE.json
```

Falls die automatische Analyse nicht möglich ist, bleibt als letzter Fallback die manuelle Manifest-Erzeugung mit Software-Code, Display-Version und Target-SSID erhalten. Diese Werte dürfen nicht geraten werden.

## Aufbau

Schema:

```text
foxair-firmware-v1
```

Beispiel V3.3:

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

Beim erfolgreichen V3.3→V3.4-Live-Update wurde verwendet:

```json
{
  "schema": "foxair-firmware-v1",
  "firmware_file": "phnixIot_device_OTA",
  "software_code": "82400644",
  "display_version": "V3.4",
  "wire_version": "0034",
  "target_ssid": "0063",
  "size": 289806,
  "md5": "149A586EDE6F035B385762EA48C71605",
  "sha256": "97B4BB09BF854BD3C7521278DE05354D9BB04A862DD05A864582B365D7AF5890",
  "image_base": "0x08050000"
}
```

## Herkunft der Felder

| Feld | Standardmodus | `--full` | Bedeutung |
|---|---|---|---|
| `schema` | Toolkonstante | Toolkonstante | Manifestformat `foxair-firmware-v1` |
| `firmware_file` | Firmware-Dateiname | Firmware-Dateiname | zugehörige Firmwaredatei |
| `software_code` | `--software-code` | **aus BIN extrahiert** | 8-stellige Mainboard-/Softwarekennung |
| `display_version` | `--display-version` | aus `wire_version` abgeleitet | z. B. `V3.4` |
| `wire_version` | aus Display-Version | **aus BIN extrahiert** | z. B. `0034` |
| `target_ssid` | explizit/fest geprüft | explizit/fest geprüft | FoxAir-Modbus-Unit-ID `0x63` → `0063` |
| `size` | aus Datei | aus Datei | tatsächliche Dateigröße |
| `md5` | berechnet | berechnet | vom Original-PHNIX-OTA verwendete Integritätsprüfung |
| `sha256` | berechnet | berechnet | zusätzliche lokale eindeutige Integritätsprüfung |
| `image_base` | validiert | validiert | erwartete Mainboard-Imagebasis `0x08050000` |

## V3.3 gegen originale PHNIX-OTA-Metadaten verifiziert

Für die V3.3-Referenzdatei liegt eine originale

```text
/data/phnixIot_device_OTA_INFO
```

mit gültiger CRC vor. Dekodiert wurden:

```text
Firmware-MD5     CEB6A4BF386FF644E23E410023E74673
SoftwareCode     82400644
SoftwareVersion  0033
```

Die gesicherte V3.3-Firmware besitzt exakt denselben MD5 und dieselbe Identität.

Das ist ein Integritätsnachweis gegen die vom Originaldienst gespeicherten OTA-Metadaten, **keine digitale Herstellersignatur**.

Details:

[`../reverse_engineering/PHNIX_phnixIot4G_ota_persistence.md`](../reverse_engineering/PHNIX_phnixIot4G_ota_persistence.md)

## Firmwareidentität in der BIN

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

Der Vollmodus verwendet **nicht** diesen festen Offset. Eine andere Firmware darf die Konstante an eine andere Stelle verschieben.

Stattdessen sucht der Generator nach dem rekonstruierten Format:

```text
8 ASCII-Zeichen SoftwareCode
+
4-stellige nicht-null Wire-Version im Format 00xy
```

Werden kein oder mehrere gültige Kandidaten gefunden, bricht `--full` ab. Das Tool rät nicht.

## `display_version` wird aus `wire_version` abgeleitet

Beispiele:

```text
0033 -> V3.3
0034 -> V3.4
```

## `target_ssid = 0063`

Für den bestätigten FoxAir-Pfad entspricht `target_ssid` der Modbus-Unit-ID des Mainboards:

```text
0x63 -> "0063"
```

Für den aktuell bestätigten GL9-/Softwarecode-82400644-Pfad gilt deshalb:

```text
target_ssid = 0063
```

Andere Hardwarevarianten nicht ohne eigenen Nachweis übernehmen.

## Vollmodus: Manifest aus einer Firmware erzeugen

```bash
./foxair-updater manifest FW3.4.bin --full
```

Standardausgabe:

```text
firmware/FW3.4.bin
-> firmware/FW3.4.json
```

## Read-only Vorschau mit `--show`

```bash
./foxair-updater manifest FW3.4.bin --full --show
```

Dabei wird keine `.json`-Datei geschrieben.

Der direkte Python-Aufruf funktioniert ebenfalls:

```bash
python3 tools/phnix_ota/create_firmware_manifest.py \
  --firmware firmware/FW3.4.bin \
  --full \
  --show
```

`--show` und `--output` schließen sich gegenseitig aus.

## Zusätzliche Sollwerte im Vollmodus

`--software-code` und `--display-version` dürfen zusammen mit `--full` angegeben werden. Sie dienen dann als zusätzliche Erwartungswerte. Weicht die BIN davon ab, bricht das Tool ab.

## Cortex-M-Plausibilisierung

Vor der Identitätsextraktion prüft `--full` zusätzlich:

```text
Initial Stack Pointer -> plausibler SRAM-Bereich 0x20000000...
Reset Vector          -> Thumb-Adresse innerhalb des Images
Image Base            -> 0x08050000
```

## Vollprüfung unmittelbar vor dem Update

Unter Linux:

```bash
./foxair-updater update FW3.4.json --full --confirm
```

Unter Windows wird dieser Full-Abgleich von der Windows-Sicherheitshülle automatisch unmittelbar vor einem echten Update durchgeführt.

Der V3.3→V3.4-Live-Lauf bestätigt, dass der Full-Abgleich mit einem realen erfolgreichen Versionswechsel zusammen funktioniert. Er beweist nicht, dass beliebige andere Firmware-/Hardwarekombinationen kompatibel sind.

## Warum die Trennung beim OTA wichtig ist

Beim Mainboard-OTA gibt es mindestens drei verschiedene Informationsquellen:

```text
1. Angebots-/Handshake-Metadaten
   software_code + wire_version
   -> C350

2. Binärintegrität
   size + MD5
   -> C357 / lokale Dateiprüfung

3. tatsächlich laufende Firmwareidentität
   -> stammt aus dem laufenden Mainboard-Firmwarecode / C544
```

Ein passendes Manifest bestätigt Punkt 1 und 2. Ob die neue Firmware tatsächlich übernommen wurde, wird erst nach dem OTA über den terminalen Mainboardstatus und die neue laufende Firmwareidentität bestätigt.

## `0033` kann zwei verschiedene Bedeutungen haben

Der oberste JSON-Code `0033` ist eine Protokollkonstante für einen Mainboard-OTA-Auftrag.

Davon getrennt kann `wire_version = "0033"` die Firmwareversion V3.3 bedeuten.

Beide Werte dürfen nicht verwechselt werden.

## Referenzmanifest

Das bestätigte V3.3-Referenzmanifest liegt unter:

```text
firmware_manifests/FW3.3.json
```

Für neue Firmwarestände ist der sinnvolle erste Schritt:

```bash
./foxair-updater manifest DATEI.bin --full --show
```

oder unter Windows **Vorschau aus Firmware (Full / Show)**.

Erst wenn die erkannten Werte plausibel sind, eine Manifestdatei erzeugen und anschließend einen Dry-Run durchführen.