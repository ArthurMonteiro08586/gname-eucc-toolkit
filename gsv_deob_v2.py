# Pass1 v2: transitive decoder-alias resolution, bulk string replacement
import json, re, time

t = {int(k): v for k, v in json.load(open('gsv_strings.json', encoding='utf-8')).items()}
h = open('C:/Users/User/tmp/gsv.min.js', encoding='utf-8', errors='ignore').read()
print('orig:', len(h))

t0 = time.time()
aliases = {'a0_0x5f56'}
assign_re = re.compile(r'(_0x[0-9a-f]{4,8})\s*=\s*(' + '|'.join(re.escape(a) for a in list(aliases)) + r')(?![A-Za-z0-9_])')
for round_i in range(8):
    before = len(aliases)
    for m in assign_re.finditer(h):
        aliases.add(m.group(1))
    if len(aliases) == before:
        break
    assign_re = re.compile(r'(_0x[0-9a-f]{4,8})\s*=\s*(' + '|'.join(re.escape(a) for a in sorted(aliases, key=len, reverse=True)) + r')(?![A-Za-z0-9_])')
print('alias rounds done:', round_i, 'aliases:', len(aliases), 'in %.1fs' % (time.time() - t0))

pat = re.compile(r'\b(' + '|'.join(re.escape(a) for a in sorted(aliases, key=len, reverse=True)) + r')\((0x[0-9a-f]+)\)')
cnt = 0
def rep(m):
    global cnt
    idx = int(m.group(2), 16)
    if idx in t:
        cnt += 1
        return json.dumps(t[idx])
    return m.group(0)
h2 = pat.sub(rep, h)
print('replaced:', cnt)
open('gsv_deob.js', 'w', encoding='utf-8').write(h2)
print('deob:', len(h2), '%.1fs total' % (time.time() - t0))
