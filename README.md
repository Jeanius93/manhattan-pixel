# Manhattan Pixel

Manhattan als frei befahrbare Open World im Pixel-Art-Stil, im Browser.

## Aktueller Stand: echtes Manhattan aus OpenStreetMap

- **Echte Stadt:** rund 56.000 Gebäude mit echten Grundrissen und Höhen, 14.600 Straßenzüge mit echten Namen, Spurenzahl und Einbahnregelung, Parks (z. B. Central Park), Teiche, Uferlinie
- 3D-Stadt, die mit niedriger Auflösung gerendert und pixelig hochskaliert wird (Konturen, leichtes Dithering)
- Fassaden (Backstein mit Feuertreppen, Kalkstein, Art déco, Beton, Glas) werden je nach Höhe und Gebäudeart gewählt
- Fließender Verkehr und Fußgänger entlang der echten Straßen, grüne Straßenschilder an den echten Kreuzungen
- Taxi und Helikopter, Sonne mit Schatten, weite Sicht

## Steuerung

| Taste | Funktion |
|---|---|
| W / ↑ | Gas (Helikopter: vorwärts) |
| S / ↓ | Bremse / Rückwärts |
| A D / ← → | Lenken / Drehen |
| H | Zwischen Taxi und Helikopter wechseln |
| Leertaste / E | Helikopter: steigen |
| Shift / Q | Helikopter: sinken |
| + / − | Pixelgröße ändern (auch per Knopf oben) |

## Daten neu erzeugen

```
pip install shapely osmium
curl -o tools/cache/NewYork.osm.pbf https://download.bbbike.org/osm/bbbike/NewYork/NewYork.osm.pbf
python3 tools/build_manhattan.py      # schreibt data/manhattan.json
```

## Starten

Die Seite lädt `data/manhattan.json` nach, braucht also einen kleinen Webserver, z. B. `python3 -m http.server` im Projektordner, dann http://localhost:8000 öffnen.

## Lizenz der Kartendaten

Kartendaten © OpenStreetMap-Mitwirkende, verfügbar unter der Open Database License (ODbL): https://www.openstreetmap.org/copyright
