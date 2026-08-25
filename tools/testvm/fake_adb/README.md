# FoxAir Fake ADB für das vorhandene PHNIX-QEMU-Lab

Der TestVM-Baustein stellt einen ADB-Smart-Socket-Server auf TCP 5038 bereit. Der echte Google-`adb.exe`-Client unter Windows verbindet sich über:

```powershell
$env:ADB_SERVER_SOCKET="tcp:<VM-IP>:5038"
```

Es wird kein zweites Modem simuliert. `/data` und `/cache` zeigen aus ADB-Sicht direkt auf das vorhandene Work-QEMU-Lab unter `/opt/phnix-lab/rootfs`; das originale ARM-`/data/phnixIot4G` läuft weiterhin über den vorhandenen Work-Szenario-Runner und dessen PTY/AT/RS485-Emulatoren.

## Architektur

```text
Windows FoxAir Updater
        ↓
echtes Google adb.exe
        ↓ TCP 5038
foxair_fake_adb_server.py
        ↓
qemu_permissive_backend.py
        ↓
privater ADB-Mount-Namespace
   /data  → /opt/phnix-lab/rootfs/data
   /cache → /opt/phnix-lab/rootfs/cache
   /tmp   → /var/lib/foxair-fake-adb/device-tmp
        ↓
qemu_work_lab_backend.py
        ↓
Work run_scenario_lab.sh
        ↓
originales ARM phnixIot4G + RS485/Mainboard-Emulator
```

Die normale Debian-VM wird dabei **nicht** global umgebogen. Insbesondere gibt es nach aktueller Installation keine globalen `/data`- oder `/cache`-Symlinks auf das QEMU-RootFS. Ältere PR-Versionen haben solche Links angelegt; der Installer entfernt sie automatisch, aber nur wenn sie tatsächlich auf das aktuelle Work-QEMU-RootFS zeigen.

## Pfadtrennung

ADB sieht:

```text
/data/...   → /opt/phnix-lab/rootfs/data/...
/cache/...  → /opt/phnix-lab/rootfs/cache/...
/tmp/...    → /var/lib/foxair-fake-adb/device-tmp/...
```

Die Debian-Host-Sicht bleibt davon getrennt:

```text
Debian /data   → unverändert / nicht vom Fake-ADB angelegt
Debian /cache  → unverändert / nicht vom Fake-ADB angelegt
Debian /tmp    → normales Host-/tmp
```

`adb push`/`adb pull` benutzen dieselbe virtuelle Zuordnung direkt über das ADB-SYNC-Protokoll. Shell und SYNC sehen deshalb denselben Modemzustand, ohne das Host-Dateisystem global umzuschreiben.

## Shell-Verhalten

Die TestVM ist absichtlich permissiv. Normale `adb shell ...`-Kommandos werden als root über die Debian-Werkzeuge ausgeführt. Dafür installiert der Setup-Pfad unter anderem:

```text
busybox
curl
gdb
net-tools
iproute2
procps
bubblewrap
```

`bubblewrap` dient ausschließlich als privater Mount-Namespace für `/data`, `/cache` und `/tmp`. Es ist keine Security-Sandbox für diesen Testaufbau.

Einige PHNIX-spezifische Prozess-/Statusabfragen werden weiterhin adaptiert, weil der originale ARM-Prozess auf Debian als QEMU-/Wrapper-Prozess erscheint. Dazu gehören insbesondere `pidof phnixIot4G`, Prozessstatus/Tracer, Watchdog-Repräsentation und die isolierte MQTT-Sicht.

## ADB-Protokoll

Unterstützt werden unter anderem:

- ADB Smart Socket auf TCP 5038
- `host:version`, `host:devices(-l)`, `host:get-state`, Features
- moderne `host:tport:*`-Transportauswahl mit Transport-ID
- `shell_v2`
- klassisches ADB-SYNC v1: `STAT`, `LIST`, `SEND`, `RECV`

Normale Host-Abfragen werden nach ihrer Antwort mit einem geordneten Socket-Close abgeschlossen. Nur nach einer Transportauswahl bleibt die Verbindung für `shell:` oder `sync:` offen. Das entspricht dem Verhalten des aktuellen Google-ADB-Clients.

## Installation dieses PR-Branches

```sh
wget -qO- https://raw.githubusercontent.com/dosordie/FoxAir_updater/testvm/fake-adb-server/tools/testvm/fake_adb/install.sh \
  | sudo env FOXAIR_FAKE_ADB_REF=testvm/fake-adb-server sh
```

Vorausgesetzt werden mindestens:

```text
/opt/phnix-lab/rootfs/data/phnixIot4G
/opt/phnix-lab/rootfs/usr/bin/qemu-arm-static
/opt/phnix-lab/tools/run_scenario_lab.sh
/opt/phnix-lab/tools/rs485_fault_emulator.py
```

## Windows-Schnelltest

```powershell
$env:ADB_SERVER_SOCKET="tcp:<VM-IP>:5038"

adb.exe devices -l
adb.exe get-state
adb.exe shell "id"
adb.exe shell "ls -l /data/phnixIot4G"
adb.exe shell "echo test >/tmp/adb-only && cat /tmp/adb-only"
adb.exe pull /data/phnixIot4G phnixIot4G-from-qemu
```

`phnixIot4G-from-qemu` muss anschließend Größe und SHA-256 des Originals unter `/opt/phnix-lab/rootfs/data/phnixIot4G` besitzen.

## Szenarien

Der Fake-ADB-Controller startet den vorhandenen Work-Runner. Die direkt abgebildeten Hauptszenarien sind:

```sh
sudo foxair-fake-adbctl scenario success
sudo foxair-fake-adbctl scenario same-version
sudo foxair-fake-adbctl scenario stall-c350
sudo foxair-fake-adbctl scenario stall-c5a8
```

Die Zuordnung erfolgt auf die tatsächlich vorhandenen `rs485_fault_emulator.py`-Schalter. Nicht direkt unterstützte historische Simulatornamen werden nicht stillschweigend angenähert.

Nützliche Diagnosebefehle:

```sh
sudo foxair-fake-adbctl status
sudo foxair-fake-adbctl lab-log
sudo journalctl -u foxair-fake-adb -f
```

## Konfiguration

`/etc/default/foxair-fake-adb` enthält typischerweise:

```sh
FOXAIR_FAKE_ADB_BIND=0.0.0.0
FOXAIR_FAKE_ADB_PORT=5038
FOXAIR_FAKE_ADB_SERIAL=foxair-vm
FOXAIR_FAKE_ADB_STATE=/var/lib/foxair-fake-adb
FOXAIR_FAKE_ADB_TMP=/var/lib/foxair-fake-adb/device-tmp
FOXAIR_FAKE_ADB_SIMULATOR=/opt/foxair-fake-adb/qemu_permissive_backend.py
FOXAIR_QEMU_LAB_ROOT=/opt/phnix-lab
FOXAIR_QEMU_LAB_ROOTFS=/opt/phnix-lab/rootfs
FOXAIR_QEMU_RUN_SECONDS=1200
```

Der OTA-Core, der Windows-Updater und das Work-QEMU-Lab werden durch diese ADB-Schicht nicht ersetzt.
