# FoxAir Fake ADB Server für Debian-Test-VM

Dieser Baustein stellt auf einer Debian-/Linux-Test-VM einen kleinen ADB-Smart-Socket-Server bereit. Der **echte Google-`adb.exe`-Client unter Windows** kann sich über `ADB_SERVER_SOCKET=tcp:<VM-IP>:5038` damit verbinden.

Ziel ist ein möglichst realistischer End-to-End-Testpfad:

```text
FoxAir_Updater.exe (Windows)
        ↓
echtes adb.exe
        ↓
ADB Smart Socket / TCP 5038
        ↓
FoxAir Fake ADB Server (Debian VM)
        ↓
vorhandener PHNIX OTA Simulator
        ↓
virtuelles LTE-Modem / virtuelles Mainboard
```

Der Fake-Server implementiert bewusst **nicht ADB vollständig**, sondern den vom FoxAir Updater benötigten Ausschnitt:

- `host:version`
- `devices` / `devices -l`
- `get-state`
- Transportauswahl (`transport-any`, Serial, Transport-ID)
- Feature-Abfrage mit `shell_v2`
- `adb shell ...` inklusive Exit-Code
- `adb push` / `adb pull` über das klassische ADB-SYNC-Protokoll
- `STAT`, `LIST`, `SEND`, `RECV`
- `adb reconnect`

Die Geräte-/OTA-Seite wird vom bestehenden `tools/phnix_ota/phnix_ota_simulator.py` bereitgestellt.

> **Nur Testnetz:** Der Server besitzt absichtlich keine ADB-Authentifizierung. Port 5038 nicht ins Internet oder in ein untrusted LAN freigeben.

## Installation nach Merge

Auf einer frischen Debian-VM genügt:

```sh
wget -qO- https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/tools/testvm/fake_adb/install.sh | sudo sh
```

Das Setup:

1. prüft/installiert `python3`, `wget` und die benötigten Basistools,
2. legt den Systembenutzer `foxair-adb` an,
3. installiert nach `/opt/foxair-fake-adb`,
4. legt den Simulatorzustand unter `/var/lib/foxair-fake-adb` ab,
5. installiert `foxair-fake-adb.service`,
6. startet den Simulator im Szenario `success`,
7. aktiviert den Fake-ADB-Server auf TCP **5038**.

## Testen dieses PR-Branches vor dem Merge

```sh
wget -qO- https://raw.githubusercontent.com/dosordie/FoxAir_updater/testvm/fake-adb-server/tools/testvm/fake_adb/install.sh \
  | sudo env FOXAIR_FAKE_ADB_REF=testvm/fake-adb-server sh
```

## Windows verbinden

In der FoxAir-Updater-GUI:

```text
Remote ADB Server: EIN
IP:   <IP der Debian-VM>
Port: 5038
```

Direkter Test in PowerShell:

```powershell
$env:ADB_SERVER_SOCKET="tcp:<VM-IP>:5038"

adb.exe devices -l
adb.exe get-state
adb.exe shell "pidof phnixIot4G || true"
```

Erwartet:

```text
List of devices attached
foxair-vm    device product:foxair model:LTE_VM device:foxair transport_id:1
```

und:

```text
4100
```

## Push/Pull-Test

```powershell
"FoxAir Fake ADB" | Set-Content -NoNewline test.txt
adb.exe push test.txt /data/test.txt
adb.exe shell "cat /data/test.txt"
adb.exe pull /data/test.txt test-back.txt
```

Damit wird der echte ADB-Clientpfad einschließlich SYNC/SEND/RECV getestet.

## Simulator steuern

```sh
sudo foxair-fake-adbctl status
sudo foxair-fake-adbctl scenario same-version
sudo foxair-fake-adbctl scenario stall-c350
sudo foxair-fake-adbctl scenario stall-c5a8
sudo foxair-fake-adbctl reset success
sudo foxair-fake-adbctl logs
```

Weitere vorhandene Szenarien kommen direkt aus `phnix_ota_simulator.py`.

Das simulierte Gerät kann bei laufendem ADB-Server gezielt offline geschaltet werden:

```sh
sudo foxair-fake-adbctl simulator-stop
```

Dann meldet `adb devices -l` das virtuelle Gerät als `offline`. Wieder online:

```sh
sudo foxair-fake-adbctl simulator-start success
```

## Konfiguration

`/etc/default/foxair-fake-adb`:

```sh
FOXAIR_FAKE_ADB_BIND=0.0.0.0
FOXAIR_FAKE_ADB_PORT=5038
FOXAIR_FAKE_ADB_SERIAL=foxair-vm
FOXAIR_FAKE_ADB_STATE=/var/lib/foxair-fake-adb
FOXAIR_FAKE_ADB_SIMULATOR=/opt/foxair-fake-adb/phnix_ota_simulator.py
```

Nach Änderungen:

```sh
sudo systemctl restart foxair-fake-adb
```

## Dateien

```text
tools/testvm/fake_adb/
├── README.md
├── install.sh
├── foxair_fake_adb_server.py
├── foxair-fake-adb.service
└── foxair-fake-adbctl
```

Der Installer lädt zusätzlich den bereits vorhandenen:

```text
tools/phnix_ota/phnix_ota_simulator.py
```

in das Installationsverzeichnis der VM.
