import re, sys
s = open(sys.argv[1], encoding="utf-8").read()
for m in re.finditer(r'<rect data-group="(\w+)" x="\d+" y="([\d.]+)" width="\d+" height="([\d.]+)"', s):
    g, y, h = m.group(1), float(m.group(2)), float(m.group(3))
    print(f"bar {g}: y={y} height={h} baseline={y+h} score_from_height={h/2} score_from_top={(240-y)/2}")
for m in re.finditer(r'data-value-for="(\w+)"[^>]*>([^<]*)<', s):
    print(f"label {m.group(1)}: {m.group(2)}")
