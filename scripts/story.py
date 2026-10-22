#!/usr/bin/env python3
"""Baut automatisch ein Story-Video (1080x1920, MP4 mit Musik) zum neuesten
Instagram-Beitrag der Villa Palmera, der noch keine Story hat.

Ablauf (GitHub Actions, .github/workflows/story.yml):
  1. Beiträge vom Worker holen: https://meta.tobias-lagmoeller.workers.dev/oeffentlich/beitraege.json
  2. Neuesten Beitrag (max. 3 Tage alt) ohne Story wählen, der noch nicht in stories/fertig.json steht
  3. Bilder laden, Musik (noch nicht/am längsten nicht benutzt) aus musik.json von Google Drive laden
  4. Video bauen -> stories/<datum>-<post_id>.mp4, Eintrag in stories/fertig.json
  5. Der Worker „meta“ veröffentlicht die Story danach selbst (IG + FB, max. 1 pro Tag).
"""
import json, os, random, re, subprocess, sys, tempfile, urllib.request
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

W, H = 1080, 1920
DAUER = 12          # Sekunden je Story
MAX_ALTER_TAGE = 3
WORKER = 'https://meta.tobias-lagmoeller.workers.dev/oeffentlich/beitraege.json'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {'User-Agent': 'Mozilla/5.0 (villa-palmera story bot)'}
FONTS = '/usr/share/fonts/truetype/dejavu/'


def lade(url, ziel=None):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        daten = r.read()
    if ziel:
        open(ziel, 'wb').write(daten)
    return daten


def drive_download(fid, ziel):
    for url in (f'https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t',
                f'https://drive.google.com/uc?export=download&id={fid}'):
        try:
            d = lade(url)
            if d[:3] == b'ID3' or d[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2') or len(d) > 200_000:
                open(ziel, 'wb').write(d)
                return True
        except Exception as e:  # noqa
            print('Drive:', url, e)
    return False


def ohne_emoji(t):
    t = re.sub(r'[\U0001F000-\U0001FAFF☀-➿️‍⃣]', '', t)
    return re.sub(r'\s+', ' ', t).strip(' .–-')


def ueberschrift(text):
    zeilen = [ohne_emoji(z) for z in (text or '').split('\n')]
    zeilen = [z for z in zeilen if z and not z.startswith('#') and not z.startswith('@')]
    kopf = zeilen[0] if zeilen else 'Villa Palmera'
    kopf = re.split(r'(?<=[.!?])\s', kopf)[0].strip(' .')
    return kopf[:60]


def umbrechen(d, text, font, breite):
    woerter, zeilen, z = text.split(), [], ''
    for w in woerter:
        t = (z + ' ' + w).strip()
        if d.textlength(t, font=font) <= breite:
            z = t
        else:
            if z:
                zeilen.append(z)
            z = w
    if z:
        zeilen.append(z)
    return zeilen[:3]


# Sicherheitszonen (Regel Tobias 22.10.2026): oben 250 px (Profilbild, Balken),
# unten 340 px (Name, Antwortfeld), seitlich 80 px frei. Kernaussage mittig,
# damit sie auch in der Facebook-Vorschaukachel sichtbar ist. Nur EINE Textebene.
OBEN, UNTEN, RAND = 250, 340, 80
BOX_Y0 = OBEN + 40            # Bildbereich 290 … 1540, kein Zusatztext (Bild trägt seinen eigenen Text)
BOX_Y1 = H - UNTEN - 40        # 1540
BOX_W = W - 2 * RAND           # 920


def overlay(titel, pfad):
    """Keine zweite Textebene über dem Beitrag (Regel 22.10.2026): leeres Overlay."""
    Image.new('RGBA', (W, H), (0, 0, 0, 0)).save(pfad)


def bild_vorbereiten(src, ziel_bg, ziel_fg):
    im = ImageOps.exif_transpose(Image.open(src)).convert('RGB')
    s = max(W / im.width, H / im.height)
    bg = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
    l, o = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((l, o, l + W, o + H)).filter(ImageFilter.GaussianBlur(40))
    ImageEnhance.Brightness(bg).enhance(0.55).save(ziel_bg)
    # Vordergrund: komplett sichtbar im Bildbereich (nichts abschneiden), gerade Maße für ffmpeg
    f = min(BOX_W / im.width, (BOX_Y1 - BOX_Y0) / im.height)
    bw, bh = int(im.width * f) // 2 * 2, int(im.height * f) // 2 * 2
    im.resize((bw, bh), Image.LANCZOS).save(ziel_fg)
    return bw, bh


def video_bauen(bilder, musik, titel, ausgabe, tmp):
    n = len(bilder)
    seg = DAUER / n
    teile = []
    for i, b in enumerate(bilder):
        bg, fg = f'{tmp}/bg{i}.png', f'{tmp}/fg{i}.png'
        bw, bh = bild_vorbereiten(b, bg, fg)
        out = f'{tmp}/s{i}.mp4'
        frames = int(seg * 30) + 15
        # Bild steht ruhig und vollständig im sicheren Bereich (kein Zoom, nichts abgeschnitten)
        x0 = (W - bw) // 2
        y0 = BOX_Y0 + ((BOX_Y1 - BOX_Y0) - bh) // 2
        filt = f"[0:v][1:v]overlay={x0}:{y0},format=yuv420p,fps=30"
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-loop', '1', '-t', f'{seg + 0.5:.2f}', '-i', bg,
                        '-loop', '1', '-t', f'{seg + 0.5:.2f}', '-i', fg, '-filter_complex', filt,
                        '-frames:v', str(frames), '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', out], check=True)
        teile.append(out)
    # Überblendungen
    if n > 1:
        cmd = ['ffmpeg', '-y', '-loglevel', 'error']
        for t in teile:
            cmd += ['-i', t]
        f, letzt, off = [], '0:v', seg - 0.5
        for i in range(1, n):
            lab = f'x{i}'
            f.append(f'[{letzt}][{i}:v]xfade=transition=fade:duration=0.5:offset={off:.2f}[{lab}]')
            letzt, off = lab, off + seg - 0.5
        cmd += ['-filter_complex', ';'.join(f), '-map', f'[{letzt}]', '-c:v', 'libx264', '-crf', '20', f'{tmp}/roh.mp4']
        subprocess.run(cmd, check=True)
    else:
        os.replace(teile[0], f'{tmp}/roh.mp4')
    overlay(titel, f'{tmp}/ov.png')
    # Musik: ab Sekunde 5 (Intro überspringen), ein- und ausblenden
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', f'{tmp}/roh.mp4', '-i', f'{tmp}/ov.png',
                    '-ss', '5', '-i', musik,
                    '-filter_complex', f"[0:v][1:v]overlay=0:0,format=yuv420p[v];"
                                       f"[2:a]afade=t=in:st=0:d=1,afade=t=out:st={DAUER - 1.5}:d=1.5,volume=0.9[a]",
                    '-map', '[v]', '-map', '[a]', '-t', str(DAUER), '-r', '30',
                    '-c:v', 'libx264', '-profile:v', 'high', '-pix_fmt', 'yuv420p', '-crf', '21', '-preset', 'medium',
                    '-c:a', 'aac', '-b:a', '160k', '-ar', '44100', '-movflags', '+faststart', ausgabe], check=True)


def main():
    fertig_pfad = os.path.join(ROOT, 'stories', 'fertig.json')
    fertig = json.load(open(fertig_pfad)) if os.path.exists(fertig_pfad) else []
    musik = json.load(open(os.path.join(ROOT, 'musik.json')))
    erzwinge = os.environ.get('POST_ID', '').strip()

    beitraege = json.loads(lade(WORKER))
    if isinstance(beitraege, dict):
        sys.exit(f'Worker-Fehler: {beitraege}')
    bekannt = {x['post_id'] for x in fertig}
    jetzt = datetime.now(timezone.utc)
    kandidat = None
    for b in beitraege:
        if erzwinge and b['id'] != erzwinge:
            continue
        alt = jetzt - datetime.fromisoformat(b['zeit'].replace('+0000', '+00:00'))
        if not erzwinge and (b.get('story') or b['id'] in bekannt or alt > timedelta(days=MAX_ALTER_TAGE)):
            continue
        if 'gewinnspiel' in (b.get('text') or '').lower() and not erzwinge:
            continue
        kandidat = b
        break
    if not kandidat:
        print('Kein neuer Beitrag ohne Story.')
        return

    # Musik: noch nie benutzt zuerst, sonst die am längsten nicht benutzte
    genutzt = {}
    for i, x in enumerate(fertig):
        genutzt[x.get('musik')] = i
    musik.sort(key=lambda m: (m['titel'] in genutzt, genutzt.get(m['titel'], -1)))  # unbenutzte in Listen-Reihenfolge

    with tempfile.TemporaryDirectory() as tmp:
        bilder = []
        for i, u in enumerate([u for u in kandidat['bilder'] if u][:3]):
            p = f'{tmp}/b{i}.jpg'
            lade(u, p)
            bilder.append(p)
        if not bilder:
            sys.exit('Keine Bilder im Beitrag.')
        wahl = None
        for m in musik:
            if drive_download(m['drive'], f'{tmp}/musik.mp3'):
                wahl = m
                break
        if not wahl:
            sys.exit('Keine Musik ladbar (Drive-Ordner „Musik“ für „Jeder mit dem Link“ freigegeben?)')
        titel = ueberschrift(kandidat.get('text'))
        datum = jetzt.strftime('%Y-%m-%d')
        name = f'stories/{datum}-{kandidat["id"]}.mp4'
        video_bauen(bilder, f'{tmp}/musik.mp3', titel, os.path.join(ROOT, name), tmp)

    fertig.append({'post_id': kandidat['id'], 'titel': titel, 'video': name, 'musik': wahl['titel'],
                   'erstellt': jetzt.strftime('%Y-%m-%dT%H:%M:%SZ'), 'link': kandidat.get('link')})
    json.dump(fertig[-200:], open(fertig_pfad, 'w'), ensure_ascii=False, indent=1)
    print(f'Story gebaut: {name} | {titel} | Musik: {wahl["titel"]}')
    with open(os.environ.get('GITHUB_STEP_SUMMARY', os.devnull), 'a') as s:
        s.write(f'Story gebaut: {name} – {titel} – {wahl["titel"]}\n')


if __name__ == '__main__':
    main()
