# medien
Medien für Villa Palmera Stories (öffentlich über GitHub Pages).

- `stories/` – fertige Story-Videos, `stories/fertig.json` = Liste für den Worker „meta“
- `scripts/story.py` + `.github/workflows/story.yml` – baut 3× täglich automatisch eine Story zum neuesten Instagram-Beitrag ohne Story
- `musik.json` – Musik aus Google Drive › Bildspeicher V+V › Musik (Pixabay, ohne Content ID)
- `reels/` – fertige Reels und Videos für Beiträge
- `geplant.json` – Veröffentlichungen zur festen Uhrzeit. Der Worker „meta“ (ab v1.3.0) prüft alle 15 Minuten und veröffentlicht fällige Einträge einmal auf IG/FB, meldet per Mail an tl@syltiges.de und als Notiz in der Aufgabenliste. Nur Einträge mit Feld `freigabe` (OK von Tobias) werden veröffentlicht. Beispiel:

```json
[{"id": "2026-10-20-tisch", "titel": "Ein Tisch für acht", "zeit": "2026-10-20T12:00:00+02:00",
  "art": "reel", "ziel": "beide", "video": "reels/2026-10-20-tisch.mp4",
  "text": "Abends sitzen alle an einem Tisch. …", "freigabe": "Tobias 15.10.2026 14:00", "aufgabe": "vv-123"}]
```
`art`: beitrag | reel | story · `ziel`: ig | fb | beide · Medien: `video` oder `bilder` (Liste), Pfad im Repo oder https-URL.
