"""Read indexed FileDB shards and build the supplemental, title-keyed JacRed index."""
import argparse
import collections
import gzip
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BTIH = re.compile(r'btih:([a-f0-9]{40})(?![a-f0-9])', re.I)
NUMBER = re.compile(r'\d+')

def unpack(path):
    with gzip.open(path, 'rt', encoding='utf-8-sig') as stream:
        return json.load(stream)

def track_index(directory):
    result = {}
    for base, _, files in os.walk(directory):
        folder = Path(base)
        for name in files:
            h = (folder.parent.name + folder.name + name.split('.')[0]).lower()
            if re.fullmatch('[0-9a-f]{40}', h):
                if h not in result or name.endswith('.json'):
                    result[h] = folder / name
    return result

def norm_codec(s):
    s = re.sub('[^a-z0-9]', '', str(s).lower())
    return {'x264':'h264','avc':'h264','x265':'hevc','h265':'hevc','av1':'av1',
            'dd':'ac3','ddp':'eac3','dolbydigital':'ac3','dolbydigitalplus':'eac3',
            'dtslossless':'dts','dtshdma':'dts','dtshd':'dts','dolbytruehd':'truehd'}.get(s,s)

def compare(tags, streams, counts):
    video = [s for s in streams if s.get('codec_type')=='video']
    audio = [s for s in streams if s.get('codec_type')=='audio']
    for key, tracks, name in [('codec',video,'codec_name'), ('audio',audio,'codec_name'), ('channels',audio,'channels')]:
        values = tags.get(key)
        if not values: continue
        values = values if isinstance(values,list) else [values]
        if key == 'channels':
            predicted = {sum(map(int, str(v).split('.'))) for v in values if re.fullmatch(r'\d+(\.\d+)?',str(v))}
            measured = {t[name] for t in tracks if isinstance(t.get(name),int)}
        else:
            predicted = {norm_codec(v) for v in values}
            measured = {norm_codec(t[name]) for t in tracks if t.get(name)}
        if predicted and measured:
            counts[key + ('.overlap' if predicted & measured else '.different')] += 1
    if tags.get('hdr'):
        # Plain ffStream from JacRed 3.20 may omit all colour / side-data fields.
        transfer = {s.get('color_transfer') for s in video} - {None,'unknown','unspecified'}
        side = str([s.get('side_data_list',[]) for s in video]).lower()
        if transfer or 'dovi' in side:
            yes = bool(transfer & {'smpte2084','arib-std-b67'}) or 'dovi' in side
            counts['hdr.' + ('overlap' if yes else 'different')] += 1
        else:
            counts['hdr.no_measurement'] += 1

def connect(path):
    con=sqlite3.connect(path,timeout=90)
    con.execute('pragma journal_mode=WAL')
    con.execute('pragma synchronous=NORMAL')
    con.executescript("""
    create table if not exists tags(title text primary key, data text not null) without rowid;
    create table if not exists progress(prefix text primary key, started real not null, report text not null);
    """)
    return con

def main():
    p=argparse.ArgumentParser()
    p.add_argument('data',type=Path)
    p.add_argument('output',type=Path)
    p.add_argument('--node',default=str(HERE/'node'))
    p.add_argument('--refresh',action='store_true')
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    con=connect(args.output/'tags.sqlite')
    now=time.time()
    master=unpack(args.data/'masterDb.bz')
    buckets=collections.defaultdict(list)
    for key in master:
        h=hashlib.md5(key.encode()).hexdigest()
        buckets[h[:2]].append(h[2:])
    del master
    external=track_index(args.data/'tracks')
    print('snapshot',sum(map(len,buckets.values())),'shards',len(external),'external hashes',flush=True)
    parser=subprocess.Popen([args.node,str(HERE/'batch.mjs')],text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    def batch(rows, report):
        titles = list(dict.fromkeys(r.get('title') or '' for r in rows))
        cached={}
        for i in range(0,len(titles),400):
            part=titles[i:i+400]
            marks=','.join('?' for _ in part)
            cached.update(con.execute('select title,data from tags where title in ('+marks+')',part))
        missing=[t for t in titles if t not in cached]
        if missing:
            parser.stdin.write(json.dumps(missing)+'\n');parser.stdin.flush()
            result=json.loads(parser.stdout.readline())
            if len(result)!=len(missing): raise ValueError('parser batch size')
            updates=[(t,json.dumps(v,ensure_ascii=False,separators=(',',':'))) for t,v in zip(missing,result)]
            con.executemany('insert or ignore into tags values(?,?)',updates)
            cached.update(updates)
        for row in rows:
            tags=json.loads(cached[row.get('title') or ''])
            counts=report[row.get('trackerName') or '(unknown)']
            counts['rows']+=1
            m=BTIH.search(row.get('magnet') or '')
            h=m[1].lower() if m else ''
            streams=row.get('ffprobe') or []
            tracked=bool(streams or h in external)
            counts['with_track' if tracked else 'without_track']+=1
            if not tracked and row.get('ffprobe_tryingdata',0)>0: counts['without_track_previously_attempted']+=1
            for k,v in tags.items():
                counts['parsed.'+k]+=1
                if not tracked: counts['unprobed.'+k]+=1
                known={'localTitle':row.get('name'),'originalTitle':row.get('originalname'),
                       'year':str(row.get('relased') or ''),'seasons':sorted(row.get('seasons') or []),
                       'resolution':str(row.get('quality') or '')+'p'}.get(k)
                if k=='resolution' and v=='4k' and known=='2160p': continue
                if k=='hdr' and row.get('videotype')=='hdr' and v==['HDR']:continue
                if known!=v: counts['extra_or_changed.'+k]+=1
            # Reproducible sample by hash; no video reads or recognition retries.
            if tracked and h and int(h[:4],16)%64==0:
                if not streams and h in external:
                    path=external[h]
                    try:
                        value=json.loads(path.read_bytes().decode('utf-8-sig'))
                        streams=value if isinstance(value,list) else value.get('streams') or []
                    except (OSError,ValueError,AttributeError):
                        counts['sample_unreadable']+=1
                if streams:
                    counts['sample']+=1
                    compare(tags,streams,counts)
        con.commit()
    try:
        for prefix, names in sorted(buckets.items()):
            prior=con.execute('select started from progress where prefix=?',(prefix,)).fetchone()
            if prior and not args.refresh:continue
            counts=collections.defaultdict(collections.Counter)
            pending=[]
            for name in names:
                path=args.data/'fdb'/prefix/name
                try:
                    if args.refresh and prior and path.stat().st_mtime < prior[0]-2: continue
                    pending.extend(unpack(path).values())
                except FileNotFoundError:
                    counts['(index)']['missing_shards']+=1
                    continue
                if len(pending)>=240:
                    batch(pending,counts); pending=[]
            if pending:batch(pending,counts)
            report=json.dumps(counts,sort_keys=True)
            if args.refresh and prior:
                con.execute('update progress set started=? where prefix=?',(now,prefix))
            else:
                con.execute('insert or replace into progress values(?,?,?)',(prefix,now,report))
            con.commit()
            print(prefix,sum(c.get('rows',0) for c in counts.values()),flush=True)
        totals=collections.defaultdict(collections.Counter)
        for (data,) in con.execute('select report from progress'):
            for tracker,counts in json.loads(data).items():totals[tracker].update(counts)
        all_counts=collections.Counter()
        for c in totals.values():all_counts.update(c)
        dest=args.output/'audit.json'
        dest.with_suffix('.tmp').write_text(json.dumps(dict(total=all_counts,trackers=totals),indent=2,ensure_ascii=False))
        dest.with_suffix('.tmp').replace(dest)
    finally:
        parser.stdin.close();parser.wait();con.close()
if __name__=='__main__':main()
