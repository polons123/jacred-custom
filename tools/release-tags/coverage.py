"""Verify archived title coverage, including JacRed's exhausted-attempt population."""
import base64
import collections
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
import yaml
from scan import unpack,track_index
from urllib.parse import unquote

data, target = map(Path,sys.argv[1:3])
config=yaml.safe_load((data.parent/'init.yaml').read_text())
limit=int(config.get('tracksatempt',5))
tracks=track_index(data/'tracks')
master=unpack(data/'masterDb.bz')
buckets=collections.defaultdict(list)
for name in master:
    d=hashlib.md5(name.encode()).hexdigest()
    buckets[d[:2]].append(d[2:])
del master
db=sqlite3.connect('file:'+str(target/'tags.sqlite')+'?mode=ro',uri=True,timeout=30)
report=collections.defaultdict(collections.Counter)
btih=re.compile(r'btih:([A-Za-z0-9]+)',re.I)
technical={'source','resolution','codec','bitDepth','hdr','audio','channels','editions','seasons','episodes','subtitleLanguages','originalAudioLanguages','dubbed','subbed','dubLabel'}
def check(rows):
    titles=list(dict.fromkeys(row.get('title') or '' for row in rows))
    found={}
    for start in range(0,len(titles),500):
        group=titles[start:start+500]
        found.update(db.execute('select title,data from tags where title in ('+','.join('?' for _ in group)+')',group))
    for row in rows:
        counts=report[row.get('trackerName') or '(unknown)']
        counts['rows']+=1
        m=btih.search(unquote(row.get('magnet') or ''))
        h=m[1].lower() if m else ''
        if len(h)==32:
            try:h=base64.b32decode(h.upper()).hex()
            except ValueError:pass
        measured=bool(row.get('ffprobe') or h in tracks)
        exhausted=int(row.get('ffprobe_tryingdata') or 0)>=limit
        group='measured' if measured else ('exhausted' if exhausted else 'unmeasured_other')
        counts[group]+=1
        raw=found.get(row.get('title') or '')
        if raw is None:
            counts['new_or_missing_title']+=1
            continue
        tags=json.loads(raw)
        if technical.intersection(tags):
            counts[group+'.with_release_metadata']+=1
        if not measured and exhausted:
            for k in technical.intersection(tags):
                counts['exhausted.'+k]+=1
        # Additional named audio/subtitle languages, the release medium and edition
        # have no corresponding source-derived track fields in the 3.20.0 row.
        if not measured:
            for k in ('source','codec','bitDepth','editions','audio','channels','subtitleLanguages','originalAudioLanguages'):
                if tags.get(k):counts['unmeasured.added.'+k]+=1
for prefix,names in sorted(buckets.items()):
    deadline=time.monotonic()+3600
    while not db.execute('select 1 from progress where prefix=?',(prefix,)).fetchone():
        if time.monotonic()>deadline:raise TimeoutError(prefix)
        time.sleep(5)
    rows=[]
    for name in names:
        try:rows.extend(unpack(data/'fdb'/prefix/name).values())
        except FileNotFoundError:
            report['(index)']['missing_shards']+=1
        if len(rows)>=300:
            check(rows);rows=[]
    if rows:check(rows)
    if int(prefix,16)%16==15: print(prefix,flush=True)
all_counts=collections.Counter()
for c in report.values():all_counts.update(c)
out=target/'coverage.json'
out.with_suffix('.tmp').write_text(json.dumps(dict(attempt_limit=limit,total=all_counts,trackers=report),ensure_ascii=False,indent=2))
out.with_suffix('.tmp').replace(out)
