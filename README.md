# KVB-Zug: Neu-Render für den Pitch

Zwei kurze Clips, die in PowerPoint direkt hintereinander laufen. Folie 1 ist rot mit Logo, dann fährt die Bahn ein (Intro), beim nächsten Klick fährt sie wieder ab (Outro) und das Bild endet wieder rot mit Logo. Danach morpht PowerPoint in die nächste Folie.

**Pitch ist am 1.12.** Bitte die Bilder bis **Sa 29.11.** zurückschicken, damit wir sie noch einbauen und prüfen können.

## Was im Repo ist

| Ordner | Inhalt |
|---|---|
| `referenz/` | `kvb-intro.mp4`, `kvb-outro.mp4`: jetziger Stand als Vorlage für Ablauf und Timing |
| `blender/` | `kvb-intro.blend`, `kvb-outro.blend` (Blender 5.2, Schriften eingepackt), `szene.py` = Skript, aus dem die Szene gebaut wird |
| `kamera/` | `kvb-intro.fbx`, `kvb-outro.fbx`: Kamera- und Zugbewegung für andere Programme (C4D, Max, Unreal …) |
| `vorgaben/` | Pflicht-Bilder für Anfang und Ende, Logos (SVG + PNG), Foto einer echten DFI-Anzeige, `titel.json` mit allen Texten |

## Frei

Alles, was gut aussieht: Zugmodell, Fahrgäste, Bahnsteig, Stadt, Dom, Licht, Wetter, Render-Engine, Kamerafahrt im Detail. Die `.blend` darf als Startpunkt dienen oder komplett ersetzt werden.

## Pflicht (sonst springt das Bild beim Folienwechsel)

1. **Format:** 1920 x 1080, **30 fps**. Intro genau **150 Bilder** (0-149), Outro genau **90 Bilder** (0-89).
2. **Intro Bild 0** = exakt `vorgaben/frame0-intro-rot-logo.png`: Vollbild-Rot **#E10023**, weißes KVB-Logo in genau dieser Größe und Position.
3. **Outro letztes Bild (89)** = exakt dasselbe Rot-mit-Logo-Bild.
4. **Intro letztes Bild (149) = Outro Bild 0**, pixelgleich. Zwischen den beiden Clips liegt ein Folienwechsel, der darf nicht sichtbar sein.
5. **Farbe:** View Transform **Standard** (nicht AgX/Filmic), Look None, Exposure 0. Sonst wird das Rot verschoben. Am einfachsten: Bild 0 und Bild 89 als flache Fläche bzw. Überblendung auf die Vorlage, nicht über Licht.
6. **Anzeige (DFI)** am Bahnsteig: Texte genau aus `titel.json` (Kopfzeile, 9 Zeilen, Laufschrift), im Endbild gut lesbar. Echte Optik siehe `vorgaben/dfi-referenz.jpg`.
7. **Zielanzeige** vorne an der Bahn: Linie `EB`, Text `Employer Branding`.

## Abgabe

- **PNG-Bildfolge**, 8 Bit RGB, ohne Alpha, ohne Videokompression
- Ordner `render_intro/` mit `f_0000.png` … `f_0149.png` und `render_outro/` mit `f_0000.png` … `f_0089.png`
- Zusammen ca. 150-300 MB, per WeTransfer oder Google Drive

Aus den Bildern bauen wir die Videos und die PowerPoint selbst.
## Holen und abgeben

```
git clone <Repo-Link>
cd kvb-zug-render
```

Die Render-Ordner `render_intro/` und `render_outro/` sind in `.gitignore` und kommen **nicht** ins Repo (zu groß). Bilder bitte per WeTransfer oder Google Drive schicken. Änderungen an der Szene (eigene .blend, Skripte) gern auf einem eigenen Branch pushen.

