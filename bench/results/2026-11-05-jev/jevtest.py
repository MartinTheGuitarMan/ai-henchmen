import sys, time, json, importlib.util
sys.path.insert(0, 'bench')
import dataset as D
import os, glob
W = glob.glob(os.path.expanduser('~/.lmstudio/models/chaoliangUNSW/*/jev_style_mlx.py'))[0]
spec = importlib.util.spec_from_file_location('jm', W); jm = importlib.util.module_from_spec(spec); spec.loader.exec_module(jm)
J = jm.JevStyle(os.path.dirname(W)); J.decide('warm up', 'ok?', ['yes','no'])
rows = []; lat = []
for c in D.CLASSIFY:
    t = time.time()
    r = J.decide(c['text'], 'Which category does this customer support message belong to?', D.TICKET_LABELS)
    lat.append(time.time() - t)
    rows.append((c['tag'], c['expected'], r[0][0], round(r[0][1], 2)))
ok = [e == p for _, e, p, _ in rows]
print('classify 32 items:', sum(ok), '/', len(ok), ' plain', sum(o for o, r in zip(ok, rows) if r[0] == 'plain'), '/30  traps', sum(o for o, r in zip(ok, rows) if r[0] == 'trap'), '/2')
lat.sort(); print('p50 %.2fs  p95 %.2fs' % (lat[len(lat)//2], lat[int(len(lat)*.95)]))
for r in rows:
    if r[1] != r[2]: print('WRONG', r)
print('mean confidence right/wrong:', round(sum(r[3] for r, o in zip(rows, ok) if o)/max(1, sum(ok)), 2), round(sum(r[3] for r, o in zip(rows, ok) if not o)/max(1, len(ok)-sum(ok)), 2))
