# Liveergebnis: C350 mit bereits installierter V3.3

Am 23. August 2026 wurde über den originalen LTE-Dienst ein ausschließlich auf
`C350` begrenzter Versuch durchgeführt. Das Mainboard lief bereits mit V3.3.
Der passive Rohmitschnitt ist die maßgebliche Busbeobachtung.

## Beobachtete Frames

```text
19:52:48.548  C350 Anfrage   63 10 C3 50 00 07 0E 00 63 38 32 34 30 30 36 34 34 30 30 33 33 59 4D
19:52:48.549  C350 ACK       63 10 C3 50 00 07 B5 DC
19:52:49.093  C36E Antwort   63 10 C3 6E 00 02 04 00 63 00 00 35 59
```

Alle drei Frames besitzen eine gültige CRC. Die C350-Nutzdaten enthalten:

- Gerätekennung `0x0063`;
- Softwarecode `82400644`;
- interne Version `0033`.

Die C36E-Nutzdaten enthalten Gerätekennung `0x0063` und Status `0`. Die
Antwortzeit ab vollständigem C350 lag bei ungefähr 545 ms.

Im vollständigen relevanten Mitschnitt wurden gezählt:

| Adresse | Bedeutung | Frames |
|---|---|---:|
| `C350` | Angebot plus ACK | 2 |
| `C36E` | Boardstatus | 1 |
| `C357` | Dateimetadaten | 0 |
| `C5A8` | Firmwaredaten | 0 |

## Interpretation

Status 0 ist bei C350 kein Nachweis einer Updatefreigabe. Die Mainboardanalyse
ordnet ihn dem nicht passenden Ziel oder einem bereits identischen Build zu.
Da Code und Version zur laufenden V3.3 passen, ist der identische Build hier
die erwartete Erklärung.

Der Versuch belegt daher:

- der originale LTE-Dienst kann lokal bis zum echten C350-Busangebot geführt
  werden;
- das Mainboard erkennt die angebotene Gleichversion und geht nicht zu C357
  oder C5A8 über;
- V3.3 wurde bei diesem Versuch weder übertragen noch erneut installiert.

## Persistenzfund

Der lokale `0033`-Handler kürzte
`/data/phnixIot_device_OTA_INFO` bereits vor Abschluss des Boardhandshakes auf
null Byte. Die zuvor gesicherte 220-Byte-Datei wurde danach bytegenau mit dem
ursprünglichen SHA-256
`2a8f2207089b2a99f390ede4d1e7170e2f1fda135e4c1dd59ad4383194b5c4a4`
wiederhergestellt.

Jeder weitere Launcher muss deshalb vor `0033` sichern, den kurzzeitig leeren
Zustand als bekannten Übergang behandeln und den Originalzustand vor dem
Freigeben des Dienstes bytegenau verifizieren.

