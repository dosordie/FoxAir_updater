# VM: DTU-Abbruch und Mainboard-Resume

Stand 2026-09-21. Nur Branch `VM_OTA_Simulator`, kein produktiver Runner-Fix.

## Bedienung

Vor einem neuen Test (Reset verwirft den vorherigen Laborlauf):

```sh
sudo foxair-fake-adbctl reset resume-fast
```

Alternativ mit originalen Mainboard-Wartezeiten:

```sh
sudo foxair-fake-adbctl reset resume-original
```

Anschließend das Update wie gewohnt in der Windows-/Linux-GUI starten.
Nach einigen übertragenen Blöcken, beispielsweise bei 50 Prozent:

```sh
sudo foxair-fake-adbctl service-crash
```

Der Befehl sendet SIGKILL ausschließlich an die eindeutig identifizierte
QEMU-Instanz von `/data/phnixIot4G.tls-lab`. Kein Reset, kein Löschen von Cache,
OTA_INFO oder Board-Resume-Datei. Zwischen Crash und Resume **kein reset** und
kein erneutes `scenario`/`board-version` ausführen.

## Zeit und Protokoll

Die Analyse vom 21.09.2026 ergibt für V3.4 zwei aufeinanderfolgende Timer:

| Profil | Interblock-Timeout | Fallback bis C544 | Gesamt ab letztem gültigen Block |
|---|---:|---:|---:|
| resume-original | 466,667 s | 466,667 s | 933,333 s (15:33 min) |
| resume-fast | 10 s | 10 s | 20 s |

Die Übertragung selbst verwendet bei beiden Szenarien das schnelle bestehende
Profil. `original` bezeichnet hier ausschließlich die Resume-Wartezeiten.
Für V3.3 sind die gleichen Zeiten eine Modellannahme; die Timerberechnung
wurde an V3.4 verifiziert.

Der Timer beginnt mit einem gültigen C5A8-Block und wird bei einem gültigen
Duplikat erneut gestartet. Nach Interblock-Timeout werden C350/C357 wieder
zugelassen. Nach dem zweiten Timer sendet das Board unaufgefordert C544 mit
seiner installierten Version. Ein normales FC03/0004 löst während dieses
Tests keinen vorzeitigen C544-Resume aus (bewusste Testisolation).

Im beschleunigten Test kann die DTU-Initialisierung länger als 20 Sekunden
dauern. Der Simulator hält deshalb das fällige C544 bis zum ProductKey-
Handshake zurück. Diese Lab-Abweichung verhindert, dass der einmalige Frame
vor Öffnen des Empfängers verloren geht.

Der Originaldienst entscheidet anhand seines erhaltenen OTA_INFO, ob Resume
zulässig ist. Er muss selbst C350/C357 senden und C5A8 fortsetzen. Der Simulator
behält `next_block`, Blockzeit und Timeoutphase in
`/data/foxair_board_ota_resume.json`. C544 alleine gilt nicht als Resume-Erfolg.

Im RS485-Transcript stehen `RESUME interblock-timeout` und
`c544-resume-timeout`. Danach C350/C357, den ersten fortgesetzten Block und den
terminalen Status prüfen. Nach vollständigem Empfang ist der Resume-Timer aus.

## Grenzen und Prüfung

Aktuell startet der vorhandene **Simulator-Watchdog** QEMU nach dem Crash neu.
Er erhält die OTA-Dateien und startet in diesen Szenarien den Originaldienst
ohne den initialen GDB-Halt. Die Board-Teilposition und verstrichene Wartezeit
werden beim Neuaufbau des Laborprozesses geladen. Dies prüft DTU-/Board-Resume,
beweist aber nicht die Restart-Policy eines neuen produktiven OTA-Runners.
Insbesondere der Neuaufbau des QEMU-Netzraums ist nicht identisch mit einem
einfachen Dienstneustart auf echter Hardware.

Linux-PTY-Tests prüfen echte C544-Frames samt CRC, erhaltene Blockposition,
Originalzeit ohne vorzeitiges C544 und bereits abgelaufene Originalzeit.
Die lange Wartezeit wird dort über eine zurückdatierte persistierte Blockzeit
geprüft. Ein vollständiger GUI-Crash/Resume-Lauf ist noch vom Anwender zu testen.

```sh
python3 tests/test_board_resume_timing.py
```

Installation des Branch-Standes auf der VM:

```sh
wget -qO- https://raw.githubusercontent.com/dosordie/FoxAir_updater/VM_OTA_Simulator/tools/testvm/fake_adb/install.sh | sudo sh
```

Nur außerhalb eines laufenden Tests installieren. Danach das gewünschte
Resume-Szenario wie oben auswählen.
