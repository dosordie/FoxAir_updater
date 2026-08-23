# Firmwaremanifest

Jeder Firmwarelauf verwendet eine Manifestdatei als einzige Quelle für
Firmwaremetadaten. Der Controller enthält keine fest eingebauten Werte für
V3.3 oder eine zukünftige V3.4.

Pflichtfelder:

```json
{
  "schema": "foxair-firmware-v1",
  "firmware_file": "FW3.4.bin",
  "software_code": "82400644",
  "display_version": "V3.4",
  "wire_version": "0034",
  "target_ssid": "0063",
  "size": 123456,
  "md5": "32 GROSSBUCHSTABIGE HEXZEICHEN",
  "sha256": "64 GROSSBUCHSTABIGE HEXZEICHEN",
  "image_base": "0x08050000"
}
```

Vor ADB-Zugriff oder Busaktivität prüft das Tool Schema, Feldformate,
Versionsableitung, Dateiname, Dateigröße, MD5 und SHA-256. Beim Bereitstellen auf
dem Modem wird MD5 erneut über die kopierte und die lokal per HTTP ausgelieferte
Datei geprüft. Die Manifestwerte erzeugen anschließend unverändert das
Original-`0033`-Kommando und die erwarteten persistenten Metadaten.

`0033` als oberster JSON-Code bleibt eine Protokollkonstante für einen
Mainboard-OTA-Auftrag. Die Firmwareversion stammt dagegen aus
`display_version` und `wire_version`.

Das bestätigte V3.3-Referenzmanifest liegt unter
`firmware_manifests/FW3.3.json`. Eine V3.4-Datei erhält erst nach eigener
Firmwareanalyse und Hashprüfung ein freigegebenes Manifest.

Ein Entwurf für eine neue Datei wird erzeugt mit:

```bash
python3 tools/phnix_ota/create_firmware_manifest.py \
  --firmware FW3.4.bin \
  --software-code 82400644 \
  --display-version V3.4 \
  --target-ssid 0063 \
  --output FW3.4.json
```

Das berechnet Größe, MD5, SHA-256 und die Busversion `0034`. Das erzeugte
Manifest ist zunächst nur ein Entwurf: Softwarecode, Ziel, Imagebasis und die
interne Identität der BIN müssen vor einer Livefreigabe unabhängig analysiert
werden.
