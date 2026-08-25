# FoxAir Fake ADB für das vorhandene PHNIX-QEMU-Lab

Dieser Baustein stellt auf der Debian-Test-VM einen ADB-Smart-Socket-Server bereit. Der **echte Google-`adb.exe`-Client unter Windows** verbindet sich über `ADB_SERVER_SOCKET=tcp:<VM-IP>:5038` damit.

Wichtig: Es wird **kein zweites virtuelles Modem** mehr aufgebaut. Die ADB-Schicht verwendet direkt das bereits von Work aufgebaute QEMU-Lab unter `/opt/phnix-lab` und dessen originales ARM-RootFS.

```text
FoxAir_Updater.exe (Windows)
        ↓
echtes adb.exe
        ↓
ADB Smart Socket / TCP 5038
        ↓
foxair_fake_adb_server.py
        ↓
qemu_lab_adapter.py
        ↓
/opt/phnix-lab/rootfs
        ↓
originales ARM /data/phnixIot4G
        ↓
PTY / AT-Modem / ttyHSL2 / Mainboard-Emulator des QEMU-Labs
```

Damit trifft zum Beispiel

```text
adb pull /data/phnixIot4G
```

wirklich

```text
/opt/phnix-lab/rootfs/data/phnixIot4G
```

und nicht mehr eine kleine Stub-Datei aus einem separaten Python-Simulator.

> **Nur Testnetz:** Der Server besitzt absichtlich keine ADB-Authentifizierung. Er bildet für den Test eine Root-ADB-Sicht auf das QEMU-Lab ab. Port 5038 niemals ins Internet oder in ein untrusted LAN freigeben.

## Voraussetzungen

Das von Work erstellte PHNIX-Lab muss bereits vorhanden sein. Standardmäßig wird erwartet:

```text
/opt/phnix-lab/
├── rootfs/
│   ├── data/
│   │   └── phnixIot4G
│   ├── cache/
│   ├── tmp/
│   └── usr/bin/qemu-arm-static
├── tools/
├── logs/
└── control/                 # wird bei Bedarf vom ADB-Adapter ergänzt
```

Der Installer akzeptiert alternativ `FOXAIR_QEMU_LAB_ROOTFS=<pfad>`.

## Installation nach Merge

```sh
wget -qO- https://raw.githubusercontent.com/dosordie/FoxAir_updater/main/tools/testvm/fake_adb/install.sh | sudo sh
```

Zum Testen dieses PR-Branches vor dem Merge:

```sh
wget -qO- https://raw.githubusercontent.com/dosordie/FoxAir_updater/testvm/fake-adb-server/tools/testvm/fake_adb/install.sh \
  | sudo env FOXAIR_FAKE_ADB_REF=testvm/fake-adb-server sh
```

Das Setup:

1. prüft die benötigten Debian-Basistools,
2. prüft, dass das vorhandene QEMU-RootFS ein `/data/phnixIot4G` enthält,
3. installiert nur ADB-Server, QEMU-Adapter und Admin-CLI nach `/opt/foxair-fake-adb`,
4. schreibt `/etc/default/foxair-fake-adb` auf den QEMU-Adapter um,
5. aktiviert `foxair-fake-adb.service` auf TCP **5038**,
6. verändert oder rekonstruiert das QEMU-RootFS **nicht**.

Bei einer bereits installierten älteren PR-#6-Version wird der bisherige Python-Simulator nicht weiter verwendet. Dessen State wird nur noch als `legacy-python-simulator` archiviert; `phnix_ota_simulator.py` wird aus `/opt/foxair-fake-adb` entfernt.

## Windows verbinden

In der FoxAir-Updater-GUI:

```text
Remote ADB Server: EIN
IP:   <IP der Debian-VM>
Port: 5038
```

Direkter Test:

```powershell
$env:ADB_SERVER_SOCKET="tcp:<VM-IP>:5038"

adb.exe devices -l
adb.exe get-state
adb.exe shell "pidof phnixIot4G || true"
adb.exe pull /data/phnixIot4G phnixIot4G-from-qemu
```

`phnixIot4G-from-qemu` muss danach Größe und SHA-256 des Originals unter `/opt/phnix-lab/rootfs/data/phnixIot4G` besitzen.

## Pfad-Mapping

```text
ADB-Pfad                              Debian-QEMU-Lab
────────────────────────────────────────────────────────────────────────────
/data/phnixIot4G                  -> /opt/phnix-lab/rootfs/data/phnixIot4G
/data/phnixIot_device_OTA_INFO    -> /opt/phnix-lab/rootfs/data/phnixIot_device_OTA_INFO
/data/phnixIot_device_statisic    -> /opt/phnix-lab/rootfs/data/phnixIot_device_statisic
/cache/phnixIot_device_OTA        -> /opt/phnix-lab/rootfs/cache/phnixIot_device_OTA
/tmp/...                          -> /opt/phnix-lab/rootfs/tmp/...
```

`adb push` und `adb pull` arbeiten über das echte ADB-SYNC-Protokoll direkt auf diesen Dateien.

## QEMU-Prozesssicht

Der Adapter sucht in `/proc` nach einem laufenden QEMU-Prozess, dessen Kommandozeile sowohl `qemu-arm(-static)` als auch `/data/phnixIot4G` enthält. Dadurch wird

```sh
adb shell "pidof phnixIot4G || true"
```

auf den realen Host-PID des emulierten ARM-Dienstes abgebildet.

Normale updater-relevante Shell-Kommandos werden über den im RootFS vorhandenen `qemu-arm-static` und die ARM-`/bin/sh` im **gleichen RootFS** ausgeführt. Einige Produktionsmerkmale wie Cloud-TCP-Verbindung und Watchdog-PIDs werden im isolierten Lab bewusst als Originalbetriebszustand repräsentiert, ohne das QEMU-Lab ans Internet zu hängen.

## Szenarien umschalten

Die bekannten Testnamen bleiben erhalten:

```sh
sudo foxair-fake-adbctl scenario success
sudo foxair-fake-adbctl scenario same-version
sudo foxair-fake-adbctl scenario stall-c350
sudo foxair-fake-adbctl scenario stall-c5a8

sudo foxair-fake-adbctl cancel-scenario retry-success
sudo foxair-fake-adbctl handshake-scenario c5a8-leak
sudo foxair-fake-adbctl same-version-scenario c357-leak
```

Der Adapter schreibt bei jeder Änderung einen stabilen Vertrag nach:

```text
/opt/phnix-lab/control/foxair-ota-scenario.json
```

Beispiel:

```json
{
  "schema": "foxair-qemu-ota-scenario-v1",
  "scenario": "stall-c5a8",
  "cancel_scenario": "success",
  "handshake_scenario": "success",
  "same_version_scenario": "success"
}
```

### Anbindung an den laufenden Mainboard-Emulator

Da die bisherigen Reverse-Engineering-Logs den Namen/API des zuletzt von Work verwendeten Scenario-Control-Skripts nicht vollständig festhalten, behauptet der Adapter hier **keine erfundene Schnittstelle**. Er verbindet sich in dieser Reihenfolge:

1. `FOXAIR_QEMU_SCENARIO_SOCKET`, falls gesetzt,
2. `FOXAIR_QEMU_SCENARIO_HOOK`, falls gesetzt,
3. bekannte Namen unter `/opt/phnix-lab/tools`, unter anderem `mainboard-simctl`, `phnix-labctl`, `foxair-scenarioctl` und `*scenario*ctl*`,
4. bekannte Unix-Sockets unter `/opt/phnix-lab/run`.

Hook-Vertrag:

```text
<HOOK> scenario stall-c5a8
<HOOK> cancel-scenario retry-success
<HOOK> handshake-scenario c5a8-leak
<HOOK> same-version-scenario c357-leak
```

Zusätzlich stehen dem Hook diese Variablen zur Verfügung:

```text
FOXAIR_QEMU_LAB_ROOT
FOXAIR_QEMU_LAB_ROOTFS
FOXAIR_QEMU_SCENARIO_FILE
```

Wenn kein Control-Endpunkt gefunden wird, wird die JSON-Datei geschrieben, aber `foxair-fake-adbctl scenario ...` endet mit **Exit 3** und meldet ausdrücklich, dass der laufende Emulator noch nicht bestätigt umgeschaltet wurde. Damit entsteht kein falscher grüner Testzustand.

Mit

```sh
sudo foxair-fake-adbctl status
```

werden erkannter RootFS-Pfad, `phnixIot4G`-Größe/SHA-256, QEMU-PIDs sowie erkannter Scenario-Hook/Socket angezeigt.

## ADB online/offline simulieren

```sh
sudo foxair-fake-adbctl offline
sudo foxair-fake-adbctl online
```

Die alten Aliase funktionieren weiter:

```sh
sudo foxair-fake-adbctl simulator-stop
sudo foxair-fake-adbctl simulator-start
```

Diese Befehle ändern **nur die ADB-Sicht**. Sie beenden oder starten ausdrücklich **nicht** den echten QEMU-`phnixIot4G`-Prozess.

## Konfiguration

`/etc/default/foxair-fake-adb`:

```sh
FOXAIR_FAKE_ADB_BIND=0.0.0.0
FOXAIR_FAKE_ADB_PORT=5038
FOXAIR_FAKE_ADB_SERIAL=foxair-vm
FOXAIR_FAKE_ADB_STATE=/var/lib/foxair-fake-adb
FOXAIR_FAKE_ADB_SIMULATOR=/opt/foxair-fake-adb/qemu_lab_adapter.py
FOXAIR_QEMU_LAB_ROOT=/opt/phnix-lab
FOXAIR_QEMU_LAB_ROOTFS=/opt/phnix-lab/rootfs
FOXAIR_QEMU_SCENARIO_FILE=/opt/phnix-lab/control/foxair-ota-scenario.json
```

Optional:

```sh
FOXAIR_QEMU_SCENARIO_HOOK=/opt/phnix-lab/tools/<vorhandenes-control-tool>
# oder
FOXAIR_QEMU_SCENARIO_SOCKET=/opt/phnix-lab/run/<vorhandener-control-socket>
```

Nach Änderungen:

```sh
sudo systemctl restart foxair-fake-adb
```

## Dateien im Repository

```text
tools/testvm/fake_adb/
├── README.md
├── install.sh
├── foxair_fake_adb_server.py       # ADB Smart-Socket + SYNC
├── qemu_lab_adapter.py             # vorhandenes Work-QEMU-Lab als Backend
├── foxair-fake-adb.service
└── foxair-fake-adbctl
```

Der OTA-Core, Runtime-Hook und das vorhandene Work-QEMU-Lab werden durch diese ADB-Schicht nicht ersetzt.
