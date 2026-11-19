#!/usr/bin/env python3
"""
Baut data/manhattan.json aus OpenStreetMap-Daten (Overpass API).

Ablauf:
  1. Rohdaten lesen: bevorzugt aus dem BBBike-Auszug tools/cache/NewYork.osm.pbf
     (https://download.bbbike.org/osm/bbbike/NewYork/NewYork.osm.pbf),
     sonst über die Overpass API (wird in tools/cache/ zwischengespeichert)
  2. Koordinaten in Meter umrechnen und um 29° drehen, damit das Straßenraster
     von Manhattan achsparallel liegt (Avenues laufen entlang der z-Achse)
  3. Land/Wasser aus der Küstenlinie bestimmen
  4. Gebäude (mit Höhen), Straßen (mit Namen, Breite, Einbahn), Parks, Wasser
     und Kreuzungen kompakt als JSON speichern (Koordinaten in Dezimetern,
     Punkte als Differenzen zum Vorgänger)

Daten: © OpenStreetMap-Mitwirkende, Lizenz ODbL (https://www.openstreetmap.org/copyright)

Aufruf:  python3 tools/build_manhattan.py
"""
import json, math, os, re, sys, time, urllib.parse, urllib.request
from collections import defaultdict

from shapely.geometry import LineString, Point, Polygon, MultiPolygon, box
from shapely.ops import polygonize, unary_union, linemerge
from shapely.strtree import STRtree
from shapely.validation import make_valid

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'cache')
OUT = os.path.join(HERE, '..', 'data', 'manhattan.json')
os.makedirs(CACHE, exist_ok=True)
os.makedirs(os.path.dirname(OUT), exist_ok=True)

OVERPASS = 'https://overpass-api.de/api/interpreter'
UA = 'manhattan-pixel-prototype/0.1 (educational game)'
AREA = 'area["wikidata"="Q11299"]->.a;'           # Borough Manhattan
BBOX = '40.675,-74.065,40.895,-73.885'            # Manhattan + Umgebung (für die Küstenlinie)

QUERIES = {
    'buildings': f'[out:json][timeout:600][maxsize:2000000000];{AREA}'
                 '(way["building"](area.a);rel["building"](area.a);'
                 'way["building:part"](area.a);rel["building:part"](area.a););out tags geom qt;',
    'roads':     f'[out:json][timeout:600];{AREA}way["highway"](area.a);out body geom qt;',
    'areas':     f'[out:json][timeout:600];{AREA}'
                 '(way["leisure"~"^(park|garden|playground|pitch|dog_park|recreation_ground)$"](area.a);'
                 'rel["leisure"~"^(park|garden)$"](area.a);'
                 'way["landuse"~"^(grass|recreation_ground|cemetery|village_green|forest)$"](area.a);'
                 'way["natural"~"^(water|wood|scrub|grassland)$"](area.a);rel["natural"~"^(water|wood)$"](area.a););'
                 'out tags geom qt;',
    'coast':     f'[out:json][timeout:300];way["natural"="coastline"]({BBOX});out geom qt;',
}


PBF = os.path.join(CACHE, 'NewYork.osm.pbf')
LAT_MIN, LAT_MAX, LON_MIN, LON_MAX = 40.675, 40.895, -74.065, -73.885
_pbf = None


def load_pbf():
    """Liest Gebäude, Straßen, Flächen und Küstenlinie aus der PBF-Datei (pyosmium)."""
    import osmium

    def inbox(lat, lon):
        return LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX

    out = {'buildings': [], 'roads': [], 'areas': [], 'coast': []}

    class H(osmium.SimpleHandler):
        def way(self, w):
            t = w.tags
            hw, nat = t.get('highway'), t.get('natural')
            if not hw and nat != 'coastline':
                return
            try:
                g = [{'lat': n.lat, 'lon': n.lon} for n in w.nodes]
            except osmium.InvalidLocationError:
                return
            if not g or not any(inbox(p['lat'], p['lon']) for p in g[::max(1, len(g) // 8)] + [g[-1]]):
                return
            el = {'type': 'way', 'tags': dict(t), 'geometry': g, 'nodes': [n.ref for n in w.nodes]}
            out['coast' if nat == 'coastline' else 'roads'].append(el)

        def area(self, a):
            t = a.tags
            bkey = 'building' in t or 'building:part' in t
            akey = (t.get('leisure') in ('park', 'garden', 'playground', 'pitch', 'dog_park', 'recreation_ground')
                    or t.get('landuse') in ('grass', 'recreation_ground', 'cemetery', 'village_green', 'forest')
                    or t.get('natural') in ('water', 'wood', 'scrub', 'grassland'))
            if not bkey and not akey:
                return
            rings = []
            try:
                for r in a.outer_rings():
                    ring = [(n.lat, n.lon) for n in r]
                    if len(ring) >= 4 and inbox(*ring[0]):
                        rings.append(ring)
            except osmium.InvalidLocationError:
                return
            if rings:
                (out['buildings'] if bkey else out['areas']).append({'type': 'poly', 'tags': dict(t), 'rings': rings})

    print('  lese', PBF, '(dauert einige Minuten) …', flush=True)
    H().apply_file(PBF, locations=True)
    for k, v in out.items():
        print(f'  {k}: {len(v)}', flush=True)
    return out


def fetch(name):
    global _pbf
    if os.path.exists(PBF):
        if _pbf is None:
            _pbf = load_pbf()
        return {'elements': _pbf[name]}
    path = os.path.join(CACHE, name + '.json')
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return json.load(open(path))
    q = QUERIES[name]
    for attempt in range(8):
        try:
            print(f'  lade {name} … (Versuch {attempt + 1})', flush=True)
            req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({'data': q}).encode(),
                                         headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=900) as r:
                raw = r.read()
            data = json.loads(raw)
            open(path, 'wb').write(raw)
            print(f'  {name}: {len(raw) / 1e6:.1f} MB, {len(data["elements"])} Elemente', flush=True)
            return data
        except Exception as e:  # Server ausgelastet o. ä. -> kurz warten
            print('   Fehler:', e, flush=True)
            time.sleep(15 + attempt * 15)
    sys.exit(f'Download von {name} fehlgeschlagen')


# ---------------------------------------------------------------- Projektion
LAT0, LON0 = 40.7580, -73.9855          # Times Square = Ursprung
ROT = math.radians(28.9)                # Neigung des Manhattan-Rasters
phi = math.radians(LAT0)
M_LAT = 111132.954 - 559.822 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
M_LON = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
CR, SR = math.cos(ROT), math.sin(ROT)


def en(lat, lon):
    """Ost/Nord in Metern, gedreht (Raster-Nord = +n)."""
    e = (lon - LON0) * M_LON
    n = (lat - LAT0) * M_LAT
    return (e * CR - n * SR, e * SR + n * CR)


def ring_of(geom):
    return [en(p['lat'], p['lon']) for p in geom]


def xz(p):
    """Spielkoordinaten: x = Raster-Ost, z = -Raster-Nord (Norden ist -z)."""
    return (p[0], -p[1])


def pack(coords):
    """Liste von (x, z) in Metern -> [x0, z0, dx1, dz1, ...] in Dezimetern."""
    out, px, pz = [], 0, 0
    for i, (x, z) in enumerate(coords):
        qx, qz = int(round(x * 10)), int(round(z * 10))
        if i == 0:
            out += [qx, qz]
        else:
            if qx == px and qz == pz:
                continue
            out += [qx - px, qz - pz]
        px, pz = qx, qz
    return out


def num(v):
    if v is None:
        return None
    m = re.match(r'^\s*(-?[0-9]+(?:\.[0-9]+)?)\s*(m|ft|\')?', str(v))
    if not m:
        return None
    x = float(m.group(1))
    if m.group(2) in ('ft', "'"):
        x *= 0.3048
    return x


def rel_polys(el):
    """Äußere Ringe einer Multipolygon-Relation als Shapely-Polygone."""
    lines = [LineString(ring_of(m['geometry'])) for m in el.get('members', [])
             if m.get('role') in ('outer', '') and m.get('type') == 'way' and len(m.get('geometry', [])) >= 2]
    if not lines:
        return []
    return [p for p in polygonize(linemerge(lines)) if p.area > 1]


def el_polys(el):
    if el['type'] == 'poly':
        res = []
        for ring in el['rings']:
            p = Polygon([en(lat, lon) for lat, lon in ring])
            if not p.is_valid:
                p = make_valid(p)
            if isinstance(p, MultiPolygon):
                res += [q for q in p.geoms if q.area > 1]
            elif isinstance(p, Polygon) and p.area > 1:
                res.append(p)
        return res
    if el['type'] == 'way':
        g = el.get('geometry') or []
        if len(g) < 4:
            return []
        p = Polygon(ring_of(g))
        if not p.is_valid:
            p = make_valid(p)
        if isinstance(p, MultiPolygon):
            return [q for q in p.geoms if q.area > 1]
        return [p] if isinstance(p, Polygon) and p.area > 1 else []
    return rel_polys(el)


# ---------------------------------------------------------------- 1) Land / Wasser
print('Küstenlinie …')
coast = fetch('coast')
coast_lines = [LineString(ring_of(w['geometry'])) for w in coast['elements'] if len(w.get('geometry', [])) >= 2]
s, w_, n_, e_ = map(float, BBOX.split(','))
corners = [en(s, w_), en(s, e_), en(n_, e_), en(n_, w_)]
bb = Polygon(corners).buffer(0)
pieces = list(polygonize(unary_union(coast_lines + [bb.exterior])))
coast_union = unary_union(coast_lines)
seg_tree_lines = []
for ln in coast_lines:
    c = list(ln.coords)
    for i in range(len(c) - 1):
        seg_tree_lines.append(LineString([c[i], c[i + 1]]))
seg_tree = STRtree(seg_tree_lines)


def is_land(poly):
    pt = poly.representative_point()
    idx = seg_tree.nearest(pt)
    seg = seg_tree_lines[idx]
    (ax, ay), (bx, by) = seg.coords
    cross = (bx - ax) * (pt.y - ay) - (by - ay) * (pt.x - ax)
    return cross > 0     # OSM: Land liegt links der Küstenlinie


lands = [p for p in pieces if p.area > 5000 and is_land(p)]
origin = Point(0, 0)
manhattan = max([p for p in lands if p.contains(origin)] or [max(lands, key=lambda p: p.area)], key=lambda p: p.area)
manhattan_buf = manhattan.buffer(60)
print(f'  {len(lands)} Landflächen, Manhattan {manhattan.area / 1e6:.1f} km²')
land_out = []
for p in lands:
    q = p.simplify(2.5)
    if q.is_empty or q.area < 5000:
        continue
    for poly in (q.geoms if isinstance(q, MultiPolygon) else [q]):
        land_out.append([1 if poly.intersects(origin) or poly.within(manhattan_buf) else 0] + pack([xz(c) for c in poly.exterior.coords[:-1]]))

# ---------------------------------------------------------------- 2) Gebäude
print('Gebäude …')
bdata = fetch('buildings')
RES = {'apartments', 'residential', 'house', 'dormitory', 'hotel', 'terrace', 'detached', 'semidetached_house'}
COM = {'office', 'commercial', 'retail', 'supermarket', 'kiosk', 'bank'}
CIV = {'church', 'cathedral', 'chapel', 'synagogue', 'mosque', 'temple', 'school', 'university', 'college', 'public',
       'government', 'civic', 'hospital', 'museum', 'library', 'courthouse', 'train_station', 'transportation', 'fire_station'}
IND = {'industrial', 'warehouse', 'garage', 'garages', 'parking', 'service', 'storage_tank', 'hangar', 'shed'}

outlines, parts = [], []
for el in bdata['elements']:
    t = el.get('tags', {})
    if t.get('building') in ('construction', 'no') or t.get('location') == 'underground':
        continue
    if t.get('layer') and str(t['layer']).lstrip('-').isdigit() and int(t['layer']) < 0:
        continue
    h = num(t.get('height'))
    lv = num(t.get('building:levels'))
    if h is None:
        h = lv * 3.3 + 1 if lv else None
    mh = num(t.get('min_height'))
    if mh is None:
        ml = num(t.get('building:min_level'))
        mh = ml * 3.3 if ml else 0.0
    kind = t.get('building') or t.get('building:part') or 'yes'
    cls = 1 if kind in RES else 2 if kind in COM else 3 if kind in CIV else 4 if kind in IND else 0
    if t.get('building') == 'roof' or t.get('building:part') == 'roof':
        cls = 5
    for poly in el_polys(el):
        if not manhattan_buf.contains(poly.centroid):
            continue
        hh = h if h is not None else (4.0 if cls == 5 else 12.0)
        if hh - mh < 0.5:
            continue
        rec = (poly, hh, mh, cls)
        (parts if 'building:part' in t and 'building' not in t else outlines).append(rec)

# Umrisse ausblenden, wenn sie Gebäudeteile enthalten (OSM "Simple 3D Buildings")
if parts:
    tree = STRtree([p[0].representative_point() for p in parts])
    keep = []
    for rec in outlines:
        hits = tree.query(rec[0])
        if any(rec[0].contains(parts[i][0].representative_point()) for i in hits):
            continue
        keep.append(rec)
    outlines = keep
blds = []
for poly, h, mh, cls in outlines + parts:
    q = poly.simplify(0.25)
    if q.is_empty or not isinstance(q, Polygon) or q.area < 4:
        continue
    pts = [xz(c) for c in q.exterior.coords[:-1]]
    if len(pts) < 3:
        continue
    blds.append([int(round(h * 10)), int(round(mh * 10)), cls] + pack(pts))
print(f'  {len(blds)} Gebäude/Gebäudeteile')

# ---------------------------------------------------------------- 3) Straßen
print('Straßen …')
rdata = fetch('roads')
RCLS = {'motorway': 1, 'motorway_link': 1, 'trunk': 2, 'trunk_link': 2, 'primary': 3, 'primary_link': 3,
        'secondary': 4, 'secondary_link': 4, 'tertiary': 5, 'tertiary_link': 5, 'residential': 6, 'unclassified': 6,
        'living_street': 7, 'service': 8, 'pedestrian': 9, 'footway': 10, 'path': 10, 'cycleway': 10, 'track': 10, 'bridleway': 10}
DEFW = {1: 14, 2: 13, 3: 15, 4: 13, 5: 11, 6: 9.5, 7: 6, 8: 5, 9: 6, 10: 2.6}
ways = []
for el in rdata['elements']:
    t = el.get('tags', {})
    hw = t.get('highway')
    cls = RCLS.get(hw)
    if not cls or t.get('area') == 'yes':
        continue
    if t.get('tunnel') in ('yes', 'building_passage') or t.get('bridge') in ('yes', 'viaduct'):
        continue
    if t.get('layer') and str(t['layer']).lstrip('-').isdigit() and int(t['layer']) != 0:
        continue
    if cls == 10 and t.get('footway') in ('sidewalk', 'crossing'):
        continue
    if cls == 8 and t.get('service') in ('parking_aisle', 'driveway', 'drive-through'):
        continue
    g = el.get('geometry') or []
    if len(g) < 2:
        continue
    lanes = num(t.get('lanes'))
    wid = num(t.get('width'))
    width = wid if wid and 2 < wid < 40 else (lanes * 3.3 + 1.0 if lanes and cls <= 7 else DEFW[cls])
    ow = t.get('oneway')
    oneway = 1 if ow in ('yes', '1', 'true') or hw in ('motorway', 'motorway_link') else (-1 if ow == '-1' else 0)
    pts = ring_of(g)
    nodes = el.get('nodes') or []
    if oneway == -1:
        pts, nodes, oneway = pts[::-1], nodes[::-1], 1
    ways.append({'cls': cls, 'w': width, 'one': oneway, 'name': t.get('name', ''), 'pts': pts, 'nodes': nodes})

# Wege mit gleichem Namen zu langen Linien verketten (für Verkehr und Fußgänger)
by_start = defaultdict(list)
for i, w in enumerate(ways):
    if w['nodes']:
        by_start[(w['name'], w['nodes'][0])].append(i)
used = [False] * len(ways)
lines = []
for i, w in enumerate(ways):
    if used[i]:
        continue
    used[i] = True
    pts, nodes = list(w['pts']), list(w['nodes'])
    while w['name'] and nodes:
        nxt = [j for j in by_start.get((w['name'], nodes[-1]), []) if not used[j] and ways[j]['one'] == w['one']]
        if len(nxt) != 1:
            break
        j = nxt[0]
        used[j] = True
        pts += ways[j]['pts'][1:]
        nodes += ways[j]['nodes'][1:]
    lines.append({**w, 'pts': pts, 'nodes': nodes})

names = sorted({l['name'] for l in lines if l['name']})
name_idx = {n: i for i, n in enumerate(names)}
road_out = []
for l in lines:
    ls = LineString(l['pts'])
    if not manhattan_buf.intersects(ls):
        continue
    q = ls.simplify(0.4)
    road_out.append([l['cls'], int(round(l['w'] * 10)), l['one'], name_idx.get(l['name'], -1)] + pack([xz(c) for c in q.coords]))

# Kreuzungen: Knoten, an denen sich zwei unterschiedlich benannte Fahrstraßen treffen
node_roads = defaultdict(list)
for l in lines:
    if l['cls'] > 7 or not l['name']:
        continue
    for k, nid in enumerate(l['nodes']):
        a = l['pts'][max(0, k - 1)]
        b = l['pts'][min(len(l['pts']) - 1, k + 1)]
        ang = math.atan2(-(b[1] - a[1]), b[0] - a[0])   # Richtung in Spielkoordinaten (x, z)
        node_roads[nid].append((l['name'], ang, l['w'], l['pts'][k]))
inter = []
seen = set()
for nid, rs in node_roads.items():
    nm = {}
    for r in rs:
        nm.setdefault(r[0], r)
    if len(nm) < 2:
        continue
    (n1, a1, w1, p), (n2, a2, w2, _) = list(nm.values())[:2]
    if not manhattan_buf.contains(Point(p)):
        continue
    key = (round(p[0] / 6), round(p[1] / 6))
    if key in seen:
        continue
    seen.add(key)
    x, z = xz(p)
    inter.append([int(round(x * 10)), int(round(z * 10)), name_idx[n1], name_idx[n2],
                  int(round(math.degrees(a1))), int(round(math.degrees(a2))), int(round(w1 * 10)), int(round(w2 * 10))])
print(f'  {len(road_out)} Straßenzüge, {len(names)} Namen, {len(inter)} Kreuzungen')

# ---------------------------------------------------------------- 4) Parks, Wasser
print('Parks und Wasser …')
adata = fetch('areas')
area_out = []
for el in adata['elements']:
    t = el.get('tags', {})
    if t.get('natural') == 'water' or t.get('water'):
        cls = 2
    elif t.get('natural') in ('wood', 'scrub') or t.get('landuse') == 'forest':
        cls = 3
    elif t.get('leisure') in ('pitch',):
        cls = 4
    elif t.get('leisure') in ('playground',):
        cls = 5
    else:
        cls = 1
    for poly in el_polys(el):
        if not manhattan_buf.intersects(poly):
            continue
        q = poly.simplify(1.0)
        if q.is_empty or not isinstance(q, Polygon) or q.area < 30:
            continue
        area_out.append([cls] + pack([xz(c) for c in q.exterior.coords[:-1]]))
area_out.sort(key=lambda a: a[0] != 1)   # Wiesen zuerst, Wasser/Wald darüber
print(f'  {len(area_out)} Flächen')

out = {
    'attribution': '© OpenStreetMap-Mitwirkende (ODbL)',
    'origin': [LAT0, LON0], 'rotationDeg': math.degrees(ROT), 'unit': 'dm',
    'land': land_out, 'buildings': blds, 'roads': road_out, 'names': names, 'intersections': inter, 'areas': area_out,
}
json.dump(out, open(OUT, 'w'), separators=(',', ':'))
print(f'Fertig: {OUT} ({os.path.getsize(OUT) / 1e6:.1f} MB)')
