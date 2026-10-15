# Pass 2: readable names for string-dict keys in gsv_deob.js
import re, json

h = open('gsv_deob.js', encoding='utf-8').read()
print('size:', len(h))

# entries: 'AbCdE':"literal"  or  'AbCdE':'literal'
ent = re.compile(r"([\"'])([A-Za-z][A-Za-z0-9]{3,6})\1\s*:\s*([\"'])((?:[^\\\"']|\\.){1,60}?)\3")
names = {}
used = set()
def mangle(v):
    s = re.sub(r'[^A-Za-z0-9]+', '_', v).strip('_')[:26]
    if not s:
        s = 'x'
    if s[0].isdigit():
        s = '_' + s
    base = s
    n = 2
    while s in used:
        s = base + str(n)
        n += 1
    used.add(s)
    return 'S_' + s

count = 0
def rep_ent(m):
    global count
    q1, key, q2, val = m.group(1), m.group(2), m.group(3), m.group(4)
    # only string-literal values (skip function entries which don't match this regex anyway)
    if re.fullmatch(r'[A-Za-z][A-Za-z0-9]{3,6}', key):
        nm = mangle(val)
        names[key] = nm
        count += 1
        return f'{q1}{nm}{q1}:{q2}{val}{q2}'
    return m.group(0)

h2 = ent.sub(rep_ent, h)
print('entries mapped:', count)

# replace usage sites DICT['KEY'] and DICT.KEY -> DICT.S_name
def rep_use(m):
    key = m.group(2)
    if key in names:
        return m.group(1) + names[key] + m.group(3)
    return m.group(0)
h3 = re.sub(r"(\[)(['\"])([A-Za-z][A-Za-z0-9]{3,6})\2(\])", lambda m: m.group(1) + m.group(2) + names.get(m.group(3), m.group(3)) + m.group(2) + m.group(4), h2)
n1 = sum(1 for _ in re.finditer(r"S_[A-Za-z0-9_]+", h3))
h4 = re.sub(r"\.([A-Za-z][A-Za-z0-9]{3,6})\b", lambda m: '.' + names[m.group(1)] if m.group(1) in names and not m.group(1).startswith('S_') else '.' + m.group(1), h3)
print('S_ refs total:', len(re.findall(r"S_", h4)))
open('gsv_deob2.js', 'w', encoding='utf-8').write(h4)
json.dump(names, open('gsv_keynames.json', 'w'), indent=0)
print('done, size:', len(h4))
