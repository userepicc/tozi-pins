"""Tozi Packaging Pinterest pins, published through RSS feeds (Pinterest auto-publish).

Each run takes the next products from tozipackaging.com (public WooCommerce Store API), draws a
1000x1500 pin from the product's own photo and the product page's own words, and adds it to the
RSS feed of the matching Pinterest board. Pinterest reads each feed once a day and pins new items.

  python pins.py              # add PER_RUN new pins (used by the daily GitHub Action)
  python pins.py --count 3    # add a custom number
  python pins.py --dry-run    # draw into preview/ only, change nothing

Rules: only the product's own photos and wording (no invented claims, no AI images), every pin
links to its product page with a trailing slash, no em-dashes in pin copy.
"""
import argparse
import datetime as dt
import email.utils
import html
import io
import json
import os
import re
import urllib.request
from xml.sax.saxutils import escape

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = 'https://userepicc.github.io/tozi-pins/'
SHOP = 'https://tozipackaging.com/wp-json/wc/store/v1/products'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36'}
PER_RUN = 3
KEEP = 30  # items kept in each feed

# WooCommerce category -> Pinterest board (boards already exist on pinterest.com/tozipackaging/)
BOARDS = {
    'Custom Gift Boxes': 'Custom Gift Boxes', 'Custom Soap boxes': 'Custom Soap Boxes',
    'Custom Cardboard Boxes': 'Custom Cardboard Boxes', 'Custom Corrugated Boxes': 'Custom Cardboard Boxes',
    'Custom Kraft Boxes': 'Custom Cardboard Boxes', 'Custom Candle Boxes': 'Custom Candle Boxes',
    'Custom Cereal Boxes': 'Custom Cereal Boxes', 'Custom Rigid Boxes': 'Custom Rigid Boxes',
    'Custom Apparel Boxes': 'Custom Apparel Boxes', 'Custom Mailer Boxes': 'Custom Mailer Boxes',
    'Custom Shoe Boxes': 'Custom Shoe Boxes', 'Custom Jewelry boxes': 'Custom Jewellery Boxes',
    'Custom Chocolate Boxes': 'Custom Chocolate Boxes', 'Custom Pizza Boxes': 'Custom Pizza Boxes with Logo',
    'Custom Cosmetic boxes': 'Custom Cosmetic Boxes', 'Custom Eyelash Boxes': 'Custom Cosmetic Boxes',
    'Custom Nail Polish Boxes': 'Custom Cosmetic Boxes', 'Custom Lipstick Boxes': 'Custom Cosmetic Boxes',
    'Custom Skincare Boxes': 'Custom Cosmetic Boxes', 'Custom Perfume Boxes': 'Custom Cosmetic Boxes',
    'Hair Extension Boxes': 'Custom Cosmetic Boxes',
}
DEFAULT_BOARD = 'Products'

BG, INK, SUB, ACC = (245, 240, 233), (38, 33, 28), (92, 83, 74), (139, 92, 52)


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def fetch(url):
    """The shop's firewall drops some clients; try a plain and a browser User-Agent with retries."""
    import time
    import urllib.parse
    url = urllib.parse.quote(url, safe=':/?&=%#+,;@')  # some image names contain non-ASCII dashes
    err = None
    for attempt in range(6):
        headers = UA if attempt % 2 else {'User-Agent': 'tozi-pins/1.0 (+https://tozipackaging.com/)'}
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                return r.read()
        except Exception as e:  # connection reset, 403, timeouts
            err = e
            time.sleep(2 + attempt * 2)
    raise RuntimeError(f'Could not fetch {url}: {err}')


def products():
    out, page = [], 1
    while True:
        batch = json.loads(fetch(f'{SHOP}?per_page=100&page={page}'))
        if not batch:
            return out
        out += batch
        page += 1


def clean(text):
    text = html.unescape(re.sub(r'<[^>]+>', ' ', text))
    text = text.replace('—', ',').replace('–', '-').replace(' -- ', ', ').replace(' - ', ', ')
    return re.sub(r'\s+', ' ', text).replace(' ,', ',').strip()


GENERIC = re.compile(r'^(why|what|how|faq|frequently|introduction|overview|conclusion|customi[sz]ation|'
                     r'best for|wholesale|send|get|order|request|sizes?|dimensions|materials?|sustainab|printing|print|finish|'
                     r'features|benefits|specifications|design|add-ons|applications|uses|types|styles|structural|interior)'
                     r'(?![a-z])|elevate your brand|options$|^\W*$', re.I)


def subtitle(p):
    """First specific heading of the product description (the page's own words); skips emoji and slogans."""
    for h in re.findall(r'<h[23][^>]*>(.*?)</h[23]>', p['description'], re.S):
        h = re.sub(r'[^\x20-\x7EÀ-ɏ]', '', clean(h)).strip(' :|')
        if 12 <= len(h) <= 90 and not GENERIC.search(h) and not h.endswith('?'):
            return h
    return ''


def description(p, limit=480):
    sents = re.split(r'(?<=[.!?])\s+', clean(p['description']))
    out = ''
    for s in sents:
        if len(out) + len(s) + 1 > limit:
            break
        out = (out + ' ' + s).strip()
    return out or clean(p['description'])[:limit]


def font(name, size, weight):
    f = ImageFont.truetype(os.path.join(ROOT, 'fonts', name), size)
    f.set_variation_by_name(weight)
    return f


def wrap(d, text, f, width):
    lines, cur = [], ''
    for w in text.split():
        t = (cur + ' ' + w).strip()
        if d.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur)
            cur = w
    return [l for l in lines + [cur] if l]


def draw_pin(photo_bytes, title, sub):
    src = Image.open(io.BytesIO(photo_bytes)).convert('RGB')
    ph = 1040
    want = 1000 / ph
    if src.width / src.height > want:
        cw = int(src.height * want)
        x0 = (src.width - cw) // 2
        src = src.crop((x0, 0, x0 + cw, src.height))
    else:
        chh = int(src.width / want)
        y0 = (src.height - chh) // 2
        src = src.crop((0, y0, src.width, y0 + chh))
    pin = Image.new('RGB', (1000, 1500), BG)
    pin.paste(src.resize((1000, ph), Image.LANCZOS), (0, 0))
    d = ImageDraw.Draw(pin)
    tf = font('Lora.ttf', 64, 'Bold')
    lines = wrap(d, title, tf, 860)
    if len(lines) > 2:
        tf = font('Lora.ttf', 54, 'Bold')
        lines = wrap(d, title, tf, 860)[:3]
    sf = font('Inter.ttf', 34, 'Regular')
    y = ph + 48
    d.rectangle([70, y, 150, y + 5], fill=ACC)
    y += 28
    for line in lines:
        d.text((70, y), line, font=tf, fill=INK)
        y += int(tf.size * 1.22)
    y += 6
    for line in wrap(d, sub, sf, 860)[:2]:
        if y > 1500 - 120:
            break
        d.text((70, y), line, font=sf, fill=SUB)
        y += 46
    d.text((70, 1500 - 78), 'tozipackaging.com', font=font('Inter.ttf', 32, 'SemiBold'), fill=ACC)
    buf = io.BytesIO()
    pin.save(buf, 'JPEG', quality=86, optimize=True, progressive=True)
    return buf.getvalue()


def load_state():
    path = os.path.join(ROOT, 'state.json')
    return json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {'published': []}


def next_items(prods, state, count):
    """Round 0 uses each product's first photo, round 1 the second photo, and so on. Boards rotate."""
    if count <= 0:
        return []
    done = {(x['product_id'], x['image']) for x in state['published']}
    queue = []
    for rnd in range(4):
        for p in sorted(prods, key=lambda p: p['id']):
            if rnd < len(p['images']) and (p['id'], rnd) not in done:
                queue.append((p, rnd))
    picked, boards = [], []
    last = [x['board'] for x in state['published'][-6:]]
    for p, rnd in queue:  # prefer a board not used in the last few pins
        b = board_of(p)
        if b not in last + boards:
            picked.append((p, rnd)); boards.append(b)
        if len(picked) == count:
            return picked
    for p, rnd in queue:
        if (p, rnd) not in picked:
            picked.append((p, rnd))
        if len(picked) == count:
            break
    return picked


def board_of(p):
    for c in p['categories']:
        if c['name'] in BOARDS:
            return BOARDS[c['name']]
    return DEFAULT_BOARD


def write_feeds(state):
    os.makedirs(os.path.join(ROOT, 'feeds'), exist_ok=True)
    by_board = {}
    for x in state['published']:
        by_board.setdefault(x['board'], []).append(x)
    for board, items in by_board.items():
        parts = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/"><channel>',
                 f'<title>Tozi Packaging: {escape(board)}</title>', '<link>https://tozipackaging.com/</link>',
                 f'<description>{escape(board)} from Tozi Packaging</description>']
        for x in sorted(items, key=lambda x: x['date'], reverse=True)[:KEEP]:
            img = BASE + x['file']
            parts.append(
                '<item>'
                f'<title>{escape(x["title"])}</title><link>{escape(x["link"])}</link>'
                f'<guid isPermaLink="false">{escape(x["file"])}</guid>'
                f'<pubDate>{email.utils.format_datetime(dt.datetime.fromisoformat(x["date"]))}</pubDate>'
                f'<description>{escape(x["description"])}</description>'
                f'<enclosure url="{escape(img)}" length="{x["bytes"]}" type="image/jpeg"/>'
                f'<media:content url="{escape(img)}" medium="image" type="image/jpeg"/>'
                '</item>')
        parts.append('</channel></rss>')
        open(os.path.join(ROOT, 'feeds', slug(board) + '.xml'), 'w', encoding='utf-8').write('\n'.join(parts))
    lines = [f'<li><a href="feeds/{slug(b)}.xml">{escape(b)}</a> ({len(v)} pins)</li>' for b, v in sorted(by_board.items())]
    open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8').write(
        '<!doctype html><meta charset="utf-8"><meta name="robots" content="noindex">'
        '<title>Tozi pin feeds</title><h1>Tozi Packaging pin feeds</h1><ul>' + ''.join(lines) + '</ul>')


def seed_items(prods, state):
    """One first-photo pin for every board that has no feed yet, so each feed URL exists before setup."""
    have = {x['board'] for x in state['published']}
    out = []
    for p in sorted(prods, key=lambda p: p['id']):
        b = board_of(p)
        if b not in have and p['images']:
            out.append((p, 0)); have.add(b)
    return out


def run(count, dry, seed=False):
    prods = products()
    state = load_state()
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    out_dir = 'preview' if dry else 'pins'
    os.makedirs(os.path.join(ROOT, out_dir), exist_ok=True)
    todo = seed_items(prods, state) if seed else next_items(prods, state, count)
    for i, (p, rnd) in enumerate(todo):
        title = clean(p['name'])[:100]
        sub = subtitle(p)
        data = draw_pin(fetch(p['images'][rnd]['src']), title, sub)
        fname = f'{out_dir}/{p["slug"]}-{rnd + 1}.jpg'
        open(os.path.join(ROOT, fname), 'wb').write(data)
        print(('preview ' if dry else 'added ') + fname, '->', board_of(p))
        if not dry:
            state['published'].append({
                'product_id': p['id'], 'image': rnd, 'board': board_of(p), 'title': title,
                'description': description(p), 'link': p['permalink'], 'file': fname, 'bytes': len(data),
                'date': (now + dt.timedelta(seconds=i)).isoformat()})
    if not dry:
        json.dump(state, open(os.path.join(ROOT, 'state.json'), 'w', encoding='utf-8'), indent=1)
        write_feeds(state)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--count', type=int, default=PER_RUN)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--seed-boards', action='store_true', help='one pin for each board without a feed')
    a = ap.parse_args()
    run(a.count, a.dry_run, a.seed_boards)
