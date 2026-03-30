#!/usr/bin/env python3
"""
Trainspotting – Praha-Dolní Počernice
Zobrazí vlaky projíždějící stanicí v příštích N minutách.
Zdroj: mapy.spravazeleznic.cz (Datel API, anonymní přístup)
"""

import base64
import json
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from html.parser import HTMLParser

# ─── Konfigurace ─────────────────────────────────────────────────────────────

STATION_SR70   = "53036"                  # Praha-Dolní Počernice
STATION_NAME   = "Praha-Dolní Počernice"
WINDOW_MINUTES = 30
WORKERS        = 30                       # paralelní loadDetail requesty

BASE_URL = "https://mapy.spravazeleznic.cz/serverside/request2.php"

# Geografický bounding box (S-JTSK/Křovák) – vlaky v dosahu stanice
# Dolní Počernice ≈ [-730000, -1047000], bbox 100km rezerva
BBOX = (-850000, -620000, -1150000, -950000)  # x_min, x_max, y_min, y_max


# ─── API ─────────────────────────────────────────────────────────────────────

def api_post(module: str, action: str, params: dict = {}) -> bytes:
    body = urllib.parse.urlencode({"module": module, "action": action, **params}).encode()
    url = f"{BASE_URL}?module={urllib.parse.quote(module)}&&action={urllib.parse.quote(action)}"
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0",
    })
    return urllib.request.urlopen(req, timeout=15).read()


def xor_decode(b64_data: str) -> list:
    """load2 response: base64 → XOR s dnešním datem (YYYYMMDD)."""
    raw = base64.b64decode(b64_data)
    for delta in [0, -1]:
        key = (date.today() + timedelta(days=delta)).strftime("%Y%m%d").encode()
        dec = bytes([raw[i] ^ key[i % len(key)] for i in range(len(raw))])
        try:
            return json.loads(dec.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
    raise RuntimeError("XOR decode selhal.")


# ─── HTML parser trasy vlaku ──────────────────────────────────────────────────

class RouteParser(HTMLParser):
    """Parsuje HTML z loadDetail. Každý řádek = stanice nebo průjezdní bod.
    data-infotabule = ZST_SR70 stanice (5 číslic, trailing space).
    td[0] = název, td[3+] = časy.
    """

    def __init__(self):
        super().__init__()
        self.stops = []
        self._row = {}
        self._in_td = False
        self._td_idx = 0
        self._text = ""
        self._in_tr = False
        self._times = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self._in_tr = True
            self._td_idx = 0
            self._times = []
            self._row = {}
        elif tag == "td" and self._in_tr:
            self._in_td = True
            self._text = ""
            if "data-infotabule" in attrs:
                self._row["sr70"] = attrs["data-infotabule"].strip()

    def handle_endtag(self, tag):
        if tag == "td" and self._in_tr:
            text = self._text.strip()
            if self._td_idx == 0:
                self._row["name"] = text
            elif self._td_idx >= 3 and text:
                self._times.append(text)
            self._in_td = False
            self._td_idx += 1
        elif tag == "tr" and self._row.get("name"):
            self._row["times"] = self._times[:]
            self.stops.append(dict(self._row))
            self._in_tr = False

    def handle_data(self, data):
        if self._in_td:
            self._text += data.strip()


# ─── Logika ───────────────────────────────────────────────────────────────────

def get_all_trains() -> list:
    resp = json.loads(api_post("Layers\\OsVlaky", "load2"))
    encoded = resp["result"]
    if isinstance(encoded, list):
        encoded = encoded[0]
    return xor_decode(encoded)


def get_train_route(train_id: str) -> list:
    b64 = base64.b64encode(train_id.encode()).decode()
    raw = api_post("Layers\\OsVlaky", "loadDetail", {
        "trainNumber": b64,
        "onlyCommercialStop": 0,
    })
    parser = RouteParser()
    parser.feed(json.loads(raw).get("detail", ""))
    return parser.stops


def time_in_window(time_str: str, now: datetime, window_min: int) -> bool:
    time_str = time_str.strip().strip("()")
    if not time_str or ":" not in time_str:
        return False
    try:
        h, m = map(int, time_str.split(":"))
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if t < now - timedelta(hours=2):
            t += timedelta(days=1)
        return now <= t <= now + timedelta(minutes=window_min)
    except ValueError:
        return False


def find_passing_trains(sr70: str, now: datetime) -> list:
    trains = get_all_trains()
    x_min, x_max, y_min, y_max = BBOX
    nearby = [
        t["p"] for t in trains
        if x_min <= t["g"]["c"][0] <= x_max and y_min <= t["g"]["c"][1] <= y_max
    ]

    print(f"  Aktivních vlaků: {len(trains)} | v oblasti: {len(nearby)}")
    print(f"  Stahuji trasy paralelně ({WORKERS} workerů)...")

    def fetch_and_match(t: dict):
        try:
            stops = get_train_route(t["id"])
        except Exception:
            return None
        for stop in stops:
            if stop.get("sr70", "").strip() != sr70:
                continue
            times = stop.get("times", [])
            sched  = times[0] if times else ""
            actual = times[1].strip("()") if len(times) > 1 else ""
            check  = actual if actual else sched
            if not time_in_window(check, now, WINDOW_MINUTES):
                return None
            return {
                "sched":      sched,
                "actual":     actual,
                "train_type": t.get("tt", ""),
                "train_num":  t.get("tn", ""),
                "from":       t.get("fn", ""),
                "to":         t.get("ln", ""),
                "delay":      t.get("de", 0),
            }
        return None

    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        for result in as_completed(executor.submit(fetch_and_match, t) for t in nearby):
            r = result.result()
            if r:
                results.append(r)

    return sorted(results, key=lambda r: r["sched"])


# ─── Výstup ───────────────────────────────────────────────────────────────────

def main():
    now = datetime.now()
    print(f"\n{'═'*62}")
    print(f"  {STATION_NAME}  |  příštích {WINDOW_MINUTES} min  |  {now.strftime('%H:%M:%S')}")
    print(f"{'═'*62}")

    results = find_passing_trains(STATION_SR70, now)

    if not results:
        print(f"\n  [žádné vlaky v příštích {WINDOW_MINUTES} min]\n")
        return

    print()
    for r in results:
        delay_str  = f"+{r['delay']} min" if r["delay"] else "včas  "
        actual_str = f"  → {r['actual']}" if r["actual"] and r["actual"] != r["sched"] else ""
        print(f"  {r['sched']}  {r['train_type']:<3} {r['train_num']:<6}  "
              f"{r['from'][:24]:<24} → {r['to'][:24]:<24}  {delay_str}{actual_str}")

    print(f"\n  {len(results)} vlaků\n{'═'*62}\n")


if __name__ == "__main__":
    main()
