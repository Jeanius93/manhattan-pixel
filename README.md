# Manhattan Pixel

Manhattan als frei befahrbare Open World im Pixel-Art-Stil, im Browser.

## Aktueller Stand: Look-Prototyp (Tag)

- 3D-Stadt, die mit niedriger Auflösung gerendert und dann pixelig hochskaliert wird (Pixel-Art-Look mit Konturen und leichtem Dithering)
- Realistische Oberflächen: Backstein (mit Feuertreppen), Kalkstein, Art déco, Beton, Glasfassaden, Läden im Erdgeschoss
- Sonne mit Schatten, Dunst in der Ferne, Bäume, parkende Autos, Ampelmasten, Wassertürme auf den Dächern
- Mit einem gelben Taxi durch die Straßenschluchten fahren oder mit dem Helikopter darüber fliegen (Taste H oder Knopf oben)
- Fließender Verkehr, Straßenlaternen, Hydranten

**Wichtig:** Straßenraster und Gebäude sind in diesem Prototyp noch *ausgedacht* (Midtown-ähnlich).
Der nächste große Schritt ist die echte 1:1-Stadt aus OpenStreetMap und den NYC-Gebäudedaten.

## Steuerung

| Taste | Funktion |
|---|---|
| W / ↑ | Gas |
| S / ↓ | Bremse / Rückwärts |
| A D / ← → | Lenken |
| H | Zwischen Taxi und Helikopter wechseln |
| Leertaste / E | Helikopter: steigen |
| Shift / Q | Helikopter: sinken |
| + / − | Pixelgröße ändern (auch per Knopf oben) |

Am Handy erscheinen Touch-Knöpfe.

## Starten

`index.html` in einem Browser öffnen (braucht Internet für die 3D-Bibliothek three.js).
