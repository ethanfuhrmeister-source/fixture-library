#!/usr/bin/env python3
# Rebuilds index.html = template.html (the app shell) with data injected from the
# frozen base app (index_2.html) plus custom additions in new-fixtures.json.
# Runs in GitHub Actions; no deps beyond the standard library.
import json, re, sys, os

BASE = 'index_2.html'       # frozen base app — data source (bulk library)
TEMPLATE = 'template.html'  # app shell with a __DATA__ placeholder (the UI)
OUT = 'index.html'          # generated full app served by Pages
ADDS = 'new-fixtures.json'  # small list of custom additions (the "inbox")
MYGEAR = 'my-gear.json'     # authoritative list of fixtures flagged as "my gear"

def norm(s):
    s = (s or '').lower()
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def extract(html):
    m = re.search(r'const DATA = (.*?);\nconst \$', html, re.S)
    if not m:
        return None, None
    return m, json.loads(m.group(1).replace('<\\/', '</'))

def normalize_entry(nf):
    t = nf.get('type', 'Other')
    modes = []
    for md in nf.get('modes', []):
        modes.append({'name': md.get('name') or (str(md.get('count')) + '-channel'),
                      'count': int(md['count']), 'channels': None})
    return {
        'mfr': nf['mfr'], 'model': nf['model'], 'type': t, 'cats': [t],
        'modes': modes, 'mine': True, 'source': 'Manufacturer spec',
        'sourceUrl': nf.get('sourceUrl'), 'confidence': nf.get('confidence', 'medium'),
        'note': nf.get('note', ''), 'vaultNote': '', 'hasChannelDetail': False,
    }

def main():
    if not os.path.exists(BASE):
        print('ERROR: base app %s not found' % BASE); sys.exit(1)
    base_html = open(BASE, encoding='utf-8').read()
    bm, data = extract(base_html)
    if data is None:
        print('ERROR: could not find embedded DATA in %s' % BASE); sys.exit(1)

    adds = []
    if os.path.exists(ADDS):
        try:
            adds = json.load(open(ADDS, encoding='utf-8'))
        except Exception as e:
            print('ERROR: %s is not valid JSON: %s' % (ADDS, e)); sys.exit(1)
    if not isinstance(adds, list):
        print('ERROR: %s must be a JSON array' % ADDS); sys.exit(1)

    existing = {(norm(f['mfr']), norm(f['model'])) for f in data['fixtures']}
    added = 0
    for nf in adds:
        key = (norm(nf.get('mfr', '')), norm(nf.get('model', '')))
        if not key[0] or not key[1] or key in existing:
            continue
        data['fixtures'].append(normalize_entry(nf))
        existing.add(key); added += 1

    # Apply the "my gear" overlay: when my-gear.json is a non-empty list, it is
    # the single source of truth for which fixtures are flagged as Ethan's gear.
    # (Empty/missing = leave the baked-in flags untouched, so a stray empty file
    # can never silently wipe the whole list.)
    if os.path.exists(MYGEAR):
        try:
            mg = json.load(open(MYGEAR, encoding='utf-8'))
        except Exception as e:
            print('WARN: %s ignored (not valid JSON: %s)' % (MYGEAR, e)); mg = None
        if isinstance(mg, list) and mg:
            gearset = {(norm(x.get('mfr', '')), norm(x.get('model', '')))
                       for x in mg if x.get('mfr') and x.get('model')}
            for f in data['fixtures']:
                f['mine'] = (norm(f['mfr']), norm(f['model'])) in gearset
            print('Applied %s: %d fixtures flagged as my gear.' % (MYGEAR, len(gearset)))

    data['fixtures'].sort(key=lambda f: (not f['mine'], f['mfr'].lower(), f['model'].lower()))
    data['stats'] = {
        'total': len(data['fixtures']),
        'mine': sum(1 for f in data['fixtures'] if f['mine']),
        'curated': sum(1 for f in data['fixtures'] if f['source'] == 'Manufacturer spec'),
        'ofl': sum(1 for f in data['fixtures'] if f['source'] == 'Open Fixture Library'),
        'qlc': sum(1 for f in data['fixtures'] if f['source'] == 'QLC+ library'),
    }
    total = data['stats']['total']
    brands = len({f['mfr'] for f in data['fixtures']})
    payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')

    # Prefer the separate UI template (so UI changes don't need a big upload).
    # Fall back to re-injecting into the base app's own shell if it's absent.
    if os.path.exists(TEMPLATE):
        tpl = open(TEMPLATE, encoding='utf-8').read()
        if '__DATA__' not in tpl:
            print('ERROR: %s has no __DATA__ placeholder' % TEMPLATE); sys.exit(1)
        new_html = tpl.replace('__DATA__', payload)
        shell = TEMPLATE
    else:
        new_html = base_html[:bm.start(1)] + payload + base_html[bm.end(1):]
        shell = BASE

    new_html = re.sub(r'\d+ fixtures across \d+ manufacturers',
                      '%d fixtures across %d manufacturers' % (total, brands), new_html)
    new_html = re.sub(r'\d+ fixtures, \d+ manufacturers',
                      '%d fixtures, %d manufacturers' % (total, brands), new_html)

    open(OUT, 'w', encoding='utf-8').write(new_html)
    print('Built %s from %s: %d fixtures (%d added this run), %d brands.' % (OUT, shell, total, added, brands))

if __name__ == '__main__':
    main()
