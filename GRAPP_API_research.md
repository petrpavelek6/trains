# Czech Railway – Datel API dokumentace (mapy.spravazeleznic.cz)

> Aktualizováno: 2026-03-30 – plně funkční, otestováno na Praha-Dolní Počernice
> Cíl: real-time průjezdní časy vlaků na konkrétním bodě české železnice

---

## ✅ Co funguje (ověřeno)

- Stažení všech 500–580 aktivních vlaků na síti ČR + okolí
- Kompletní trasa každého vlaku včetně průjezdních bodů (km značky, výhybny, ...)
- Real-time zpoždění
- Vyhledání stanice podle názvu → SR70 kód
- Tabule stanice (příjezdy/odjezdy pro komerční zastávky)

---

## Autentizace

**API je zcela veřejné – žádná autentizace není potřeba.**

Ověřeno (30.3.2026): všechny endpointy fungují anonymně bez cookie i bez přihlášení:
- `load2` → 460 vlaků ✓
- `loadDetail` → plná trasa ✓
- `ZeleznicniStanice/load` → stanice ✓
- `InfoTabule/loadTabule` → tabule ✓

Cookie `ISPDMapPublic` existuje pro přihlášené uživatele (oblíbené stanice, notifikace), ale pro čtení dat není vyžadována. Script `test_dolni_pocernice.py` funguje bez jakékoliv cookie.

### Login endpoint (jen pro funkce přihlášeného účtu)
```
module=Users&action=login
params: email, heslo, rememberme (0/1), g-recaptcha-token
```
Login vyžaduje Google reCAPTCHA – **nelze automatizovat**. Ale není potřeba.

---

## Base URL a formát requestů

```
POST https://mapy.spravazeleznic.cz/serverside/request2.php
     ?module={MODULE}&&action={ACTION}

Headers:
  Content-Type: application/x-www-form-urlencoded; charset=UTF-8
  Cookie: ISPDMapPublic={SESSION_VALUE}
  X-Requested-With: XMLHttpRequest

Body (url-encoded):
  module={MODULE}&action={ACTION}&param1=val1&...
```

---

## Endpointy

### 1. `Layers\OsVlaky / load2` – Všechny aktivní vlaky

```
POST request2.php?module=Layers\OsVlaky&&action=load2
Body: module=Layers\OsVlaky&action=load2
```

Response: `{"cachedResult": false, "result": ["BASE64_XOR_ENCODED_STRING"]}`

**Dekódování (Python):**
```python
import base64, json
from datetime import date, timedelta

def xor_decode(b64_data: str) -> list:
    raw = base64.b64decode(b64_data)
    for delta in [0, -1]:  # zkusí dnešní datum, pak včerejší
        key = (date.today() + timedelta(days=delta)).strftime('%Y%m%d').encode()
        decrypted = bytes([raw[i] ^ key[i % len(key)] for i in range(len(raw))])
        try:
            return json.loads(decrypted.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    raise RuntimeError('XOR decode selhal')
```

**Struktura výsledku** – seznam GeoJSON Feature objektů:
```json
{
  "type": "Feature",
  "id": "TR/231/KASO--123456/00/2026/20260330",
  "g": {"type": "Point", "c": [-730000.0, -1047000.0]},
  "p": {
    "id": "TR/231/...",     // trainId pro loadDetail
    "tt": "Os",             // typ vlaku: Os/R/Sp/EC/IC/RJ/LE/...
    "tn": "9411",           // číslo vlaku
    "fn": "Praha hl.n.",    // výchozí stanice
    "ln": "Milovice",       // cílová stanice
    "cna": "Praha-Dolní Počernice",  // aktuální poloha
    "de": 1,                // zpoždění v minutách
    "nna": "Úvaly",         // příští zastávka (komerční)
    "nsn": "Úvaly",         // příští zastávka (plný název)
    "nsn70": "53096",       // SR70 příští zastávky
    "zst_sr70": "53036",    // SR70 aktuální polohy
    "cp": "09:34",          // plánovaný čas na aktuální stanici
    "cr": "09:35",          // reálný čas (s zpožděním)
    "pde": "1 min",         // zpoždění jako text
    "d": "České dráhy, a.s.", // dopravce
    "a": 95.5,              // azimut pohybu (stupně)
    "r": "231",             // číslo tratě/linky
    "nst": "09:38",         // plánovaný čas příští zastávky
    "nsp": "09:39"          // reálný čas příští zastávky
  }
}
```

**Souřadnicový systém:** S-JTSK / Křovák (EPSG:5514 nebo podobný)
- Praha: přibližně x ∈ (-760000, -700000), y ∈ (-1060000, -1030000)
- Bbox celá ČR: x ∈ (-950000, -400000), y ∈ (-1250000, -900000)

**Typy vlaků (tt):** `Os, R, Sp, EC, IC, SC, EN, Ex, LE, RJ, Rx, AEx, TLX, TL, Sv`
**Dopravci:** `České dráhy, RegioJet, Leo Express, GWTR, Die Länderbahn CZ, ...`

---

### 2. `Layers\OsVlaky / loadDetail` – Trasa vlaku + průjezdní body

```
POST request2.php?module=Layers\OsVlaky&&action=loadDetail
Body: module=Layers\OsVlaky&action=loadDetail
      &trainNumber={BASE64_TRAIN_ID}
      &onlyCommercialStop=0    ← 0 = vč. průjezdů, 1 = jen komerční zastávky
```

```python
import base64
train_b64 = base64.b64encode(train_id.encode()).decode()
```

Response: `{"detail": "<HTML>", "result": null, ...}`

**Struktura HTML:**
```html
<table class='detail-jizdy-vlaku'>
  <tr class='even'>
    <td class='text-blue showVlakyPrijOdjTabule'
        data-zstsr70='54530364'      ← 8místný interní kód
        data-infotabule='53036 '     ← ZST_SR70 (5 míst, trailing space)
        title='Příjezdové a odjezdové tabule'>
      <b class='station-name'>Praha-Dolní Počernice</b>
    </td>
    <td style=''></td>
    <td style=''></td>
    <td style='color:#77AA00'>09:34</td>      ← plánovaný příjezd
    <td style='color:#737373'>(09:35)</td>   ← reálný příjezd
    <td style='color:#77AA00'>09:34</td>      ← plánovaný odjezd
    <td style='color:#737373'>(09:35)</td>   ← reálný odjezd
  </tr>
  <!-- průjezdní bod (bez komerční zastávky): -->
  <tr class='odd'>
    <td data-zstsr70='54571265' data-infotabule=''>
      <span class='station-name'>km 2,500</span>
    </td>
    <!-- jen 2 časy: plán + reál -->
    <td style='color:#77AA00'>09:36</td>
    <td style='color:#737373'>(09:37)</td>
  </tr>
</table>
```

**Rozlišení zastávky vs. průjezdu:**
- Zastávka (zastavuje): `<b class='station-name'>`, `data-infotabule='XXXXX'` (neprázdné)
- Průjezdní bod: `<span class='station-name'>` nebo `data-infotabule=''`
- Zastávka má 4 časy (příjezd + odjezd), průjezdní bod má 2 časy

**Matchování stanice v trase:**
```python
# Podle SR70 (spolehlivé):
stop_sr70 = attrs.get('data-infotabule', '').strip()
if stop_sr70 == target_sr70:  # např. '53036'
    ...

# Podle názvu (fallback):
if 'Počernice' in station_name:
    ...
```

---

### 3. `Layers\ZeleznicniStanice / load` – Vyhledání stanice → SR70

```
POST request2.php?module=Layers\ZeleznicniStanice&&action=load
Body: module=Layers\ZeleznicniStanice&action=load&search=Dolní Počernice
```

Response: `{"result": [{"properties": {"ZST_SR70": "53036", "ZST_NAZEV": "Praha-Dolní Počernice", "X": ..., "Y": ...}, "g": {...}}, ...]}`

---

### 4. `Layers\InfoTabule / loadTabule` – Tabule příjezdů/odjezdů stanice

```
POST request2.php?module=Layers\InfoTabule&&action=loadTabule
Body: module=Layers\InfoTabule&action=loadTabule&SR70={ZST_SR70}0
```

`SR70` parametr = ZST_SR70 + `"0"` (např. `53036` → `530360`)

Vrací HTML tabuli s příjezdy a odjezdy. **Obsahuje pouze vlaky se komerční zastávkou** (ne průjezdy).

**Struktura HTML:**
```html
<div class="layer-infotabule">
  <div class="prijezd-odjezd" data-typ="prijezdy">
    <table>
      <tbody>
        <tr>
          <td class="inTaColP-1">Český Brod</td>          ← Ze směru
          <td class="inTaColP-2 d-none d-md-table-cell">S1</td>  ← Linka
          <td class="inTaColP-3 d-none d-md-table-cell">08:14</td> ← Plán. čas
          <td class="inTaColP-4 d-md-none d-table-cell">08:14<br>...</td>
          <td class="inTaColP-4 d-none d-md-table-cell">...</td>  ← Aktuální
          <td class="inTaColP-5" data-trainnumber="9320">Os 9320 ČD</td> ← Vlak
          <td class="inTaColP-6">Český Brod 08:12 (2 min)</td>   ← Posl. poloha
          <td class="inTaColP-7">2</td>                           ← Kolej
        </tr>
      </tbody>
    </table>
  </div>
  <div class="prijezd-odjezd" data-typ="odjezdy">...</div>
</div>
```

---

## Workflow pro trainspotting konkrétního bodu

```python
# 1. Najít SR70 cílové stanice
sr70, name = find_station("Dolní Počernice")  # → "53036", "Praha-Dolní Počernice"

# 2. Stáhnout všechny aktivní vlaky
trains_raw = api_post("Layers\\OsVlaky", "load2", {})
trains = xor_decode(json.loads(trains_raw)["result"][0])

# 3. Geografická filtrace (S-JTSK bbox)
# Praha oblast: x ∈ (-850000, -620000), y ∈ (-1150000, -950000)
nearby = [t["p"] for t in trains if bbox_filter(t["g"]["c"])]

# 4. Pro každý vlak v oblasti: stáhnout trasu
for train in nearby:
    train_b64 = base64.b64encode(train["id"].encode()).decode()
    detail = api_post("Layers\\OsVlaky", "loadDetail", {
        "trainNumber": train_b64,
        "onlyCommercialStop": 0,
    })
    route = parse_route_html(json.loads(detail)["detail"])

    # 5. Matchovat SR70 cílové stanice v trase
    for stop in route:
        if stop["sr70"] == sr70:
            # časy průjezdu nalezeny!
            sched_time = stop["times"][0]
            real_time = stop["times"][1].strip("()")
```

---

## Hotový proof-of-concept script

**Soubor:** `/Users/petr.pavelek/Documents/Claude_code/Trainspoting/test_dolni_pocernice.py`

Spuštění:
```bash
python3 test_dolni_pocernice.py          # 30 minut dopředu
```

Nebo s jiným oknem:
```python
import test_dolni_pocernice as t
t.WINDOW_MINUTES = 10
t.main()
```

---

## Výsledky testu (30.3.2026, Praha-Dolní Počernice)

```
09:29  R 945     Praha hl.n. → Hradec Králové hl.n.   včas
09:34  Os 9320   Poříčany → Praha M.n.-dvorana         včas
09:34  Os 9413   Praha hl.n. → Milovice                +1 min
09:35  Os 28217  Praha hl.n. → Úvaly                   včas
09:39  LE 1244   Bohumín → Praha hl.n.                 +7 min
```

Data odpovídají reálnému provozu.

---

## Další endpointy (neotestováno podrobně)

```
Layers\MimoradneUdalosti / load       ← mimořádné události
Layers\MimoradneUdalosti / loadALL    ← všechny MU
Layers\Stavby / search                ← stavební práce
Layers\JizdniRady / search            ← jízdní řády
Layers\Bezbarierovost / load          ← bezbariérová přístupnost
```

---

## Otevřené otázky pro příštní iteraci

1. Jak dlouho vydrží session cookie bez interakce?
2. Funguje `Users/login` pro programatické získání cookie (email + heslo)?
3. ~~Jak optimalizovat loadDetail volání – nyní ~300 requestů, trvá ~60s~~ **VYŘEŠENO:** ThreadPoolExecutor(30) → ~8s
4. Jak rozlišit v HTML průjezd (`<span>`) vs. zastávku (`<b>`) spolehlivě?
5. Má InfoTabule/loadTabule průjezdy nebo jen komerční zastávky? **ODPOVĚĎ:** Jen komerční zastávky.

---

## Aktuální stav – fungující Python script (30.3.2026)

**Soubor:** `test_dolni_pocernice.py`

### Co script dělá

Zobrazí seznam vlaků projíždějících stanicí Praha-Dolní Počernice v příštích N minutách (výchozí: 30), včetně vlaků, které ve stanici **nezastavují** (průjezdy).

### Workflow

```
1. GET všechny aktivní vlaky (load2) → XOR dekódování → ~460–580 vlaků
2. Bbox filtr (S-JTSK) → vlaky v okruhu Prahy → ~200–300 vlaků
3. Paralelně (30 workerů): loadDetail(onlyCommercialStop=0) pro každý vlak
4. Parsovat HTML trasy → najít zastávku s data-infotabule == '53036'
5. time_in_window() → filtrovat na příštích 30 minut
6. Seřadit podle plánovaného času → vypsat
```

### Klíčové parametry

| Parametr | Hodnota | Popis |
|---|---|---|
| `STATION_SR70` | `53036` | Praha-Dolní Počernice (ZST_SR70 kód) |
| `WINDOW_MINUTES` | `30` | Okno dopředu v minutách |
| `WORKERS` | `30` | Počet paralelních loadDetail requestů |
| `BBOX` | `(-850000,-620000,-1150000,-950000)` | S-JTSK bbox pro Prahu + okolí |

### Výkon

- Celkový čas: ~7–10 sekund (z toho ~6s paralelní loadDetail)
- Bez parallelizace by bylo ~90–120s (sekvenční)

### Ukázkový výstup

```
══════════════════════════════════════════════════════════════
  Praha-Dolní Počernice  |  příštích 30 min  |  09:29:05
══════════════════════════════════════════════════════════════

  09:29  R   945     Praha hl.n.              → Hradec Králové hl.n.   včas
  09:34  Os  9320    Poříčany                 → Praha M.n.-dvorana     včas
  09:34  Os  9413    Praha hl.n.              → Milovice                +1 min
  09:35  Os  28217   Praha hl.n.              → Úvaly                  včas
  09:39  LE  1244    Bohumín                  → Praha hl.n.            +7 min

  5 vlaků
══════════════════════════════════════════════════════════════
```

### Závislosti

Žádné – pouze Python 3 standard library (`urllib`, `base64`, `json`, `html.parser`, `concurrent.futures`).

### Spuštění

```bash
python3 test_dolni_pocernice.py
```

---

## Plán přepisu na HTML/JS (GitHub Pages + iPhone PWA)

### Cíl

Statická HTML stránka bez backendu, přístupná z iPhonu u trati. Přidatelná na plochu jako PWA (vypadá jako nativní app).

**Cílový soubor:** `index.html` (vše v jednom souboru, žádné závislosti)

### Proč jde HTML/JS přímý přístup na API

API vrací `Access-Control-Allow-Origin: *` → prohlížeč může volat API přímo z JS bez proxy serveru.

### Mapa Python → JavaScript

| Python | JavaScript | Poznámka |
|--------|-----------|----------|
| `urllib.request` | `fetch()` | nativní async |
| `base64.b64decode(x)` | `atob(x)` | vestavěný |
| `base64.b64encode(x)` | `btoa(x)` | vestavěný |
| XOR loop | stejný algoritmus s `Uint8Array` | |
| `json.loads()` | `JSON.parse()` | |
| `ThreadPoolExecutor(30)` | `Promise.all()` | nativně paralelní, bez limitu |
| `HTMLParser` | `DOMParser` | nativní DOM parsing |
| `datetime.now()` | `new Date()` | |
| `timedelta` | `Date` aritmetika | |

### Klíčové JS funkce

```js
// XOR decode – stejný algoritmus jako Python
function xorDecode(b64) {
  const raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0))
  for (const delta of [0, -1]) {
    const d = new Date(); d.setDate(d.getDate() + delta)
    const key = new TextEncoder().encode(
      d.getFullYear() +
      String(d.getMonth()+1).padStart(2,'0') +
      String(d.getDate()).padStart(2,'0')
    )
    const dec = raw.map((b, i) => b ^ key[i % key.length])
    try { return JSON.parse(new TextDecoder().decode(dec)) } catch {}
  }
  throw new Error('XOR decode selhal')
}

// API volání
async function apiPost(module, action, params = {}) {
  const body = new URLSearchParams({ module, action, ...params })
  const res = await fetch(
    `https://mapy.spravazeleznic.cz/serverside/request2.php?module=${encodeURIComponent(module)}&&action=${encodeURIComponent(action)}`,
    { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest' }, body }
  )
  return res.json()
}

// Paralelní fetch tras – ekvivalent ThreadPoolExecutor
const results = await Promise.all(nearbyTrains.map(t => fetchAndMatch(t)))
```

### UI design pro iPhone

- Tmavé pozadí (čitelné na slunci)
- Velký font (min 16px, čísla vlaků tučně)
- Jeden tlačítko **Refresh** (nebo automatické obnovení každé 2 min)
- Tabulka: `čas | typ | číslo | z → do | zpoždění`
- Barevné kódování zpoždění: zelená = včas, žlutá = 1–5 min, červená = ≥6 min
- Spinner / loading state během fetchování
- Zobrazit čas posledního obnovení

### PWA meta tagy

```html
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Vlaky">
```

### GitHub Pages nasazení

1. `index.html` nahrát do repozitáře `petrpavelek6/trains`
2. GitHub → Settings → Pages → Source: `main` branch, `/ (root)`
3. URL: `https://petrpavelek6.github.io/trains/`
4. iPhone: otevřít v Safari → Sdílet → Přidat na plochu

### Ověření

1. Otevřít `index.html` lokálně (`file://`) v Chrome → funguje?
2. Nahrát na GitHub → GitHub Pages URL → funguje?
3. Otevřít na iPhonu v Safari → přidat na plochu → funguje?
4. Porovnat výsledky s Python scriptem (stejné vlaky?)
