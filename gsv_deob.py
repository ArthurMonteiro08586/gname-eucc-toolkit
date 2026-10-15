# Bulk de-obfuscate gsv.min.js using decoded string table
import json, re

t = {int(k): v for k, v in json.load(open('gsv_strings.json', encoding='utf-8')).items()}
h = open('gsv.min.js', encoding='utf-8', errors='ignore').read()
print('orig size:', len(h))

aliases = set(re.findall(r'var (_0x[0-9a-f]+)=a0_0x5f56', h))
aliases |= set(re.findall(r'(_0x[0-9a-f]+)=a0_0x5f56[;,]', h))
aliases.add('a0_0x5f56')
print('aliases:', len(aliases))

pat = re.compile(r'(' + '|'.join(re.escape(a) for a in aliases) + r')\((0x[0-9a-f]+)\)')
cnt = 0
def rep(m):
    global cnt
    idx = int(m.group(2), 16)
    if idx in t:
        cnt += 1
        s = t[idx]
        # encode as JS string literal safely
        return json.dumps(s)
    return m.group(0)
h2 = pat.sub(rep, h)
print('replaced:', cnt)
open('gsv_deob.js', 'w', encoding='utf-8').write(h2)
print('deob size:', len(h2))
