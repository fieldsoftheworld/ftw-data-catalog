import glob, os, collections, json

D = "/u/cholmes/ftw-crs-fix/final_partitions"
codes = sorted({os.path.basename(f)[:-8].split("_")[0] for f in glob.glob(os.path.join(D, "*.parquet"))})

try:
    import pycountry
    have = True
except ImportError:
    have = False
print("pycountry:", have, "; codes:", len(codes))

OVERRIDES = {  # short, common names where ISO official is long/awkward
    "IR": "Iran", "BO": "Bolivia", "TZ": "Tanzania", "VE": "Venezuela",
    "KR": "South Korea", "KP": "North Korea", "LA": "Laos", "SY": "Syria",
    "MD": "Moldova", "RU": "Russia", "VN": "Vietnam", "BN": "Brunei",
    "CD": "DR Congo", "CG": "Congo", "CI": "Cote d'Ivoire", "FM": "Micronesia",
    "GB": "United Kingdom", "US": "United States", "TW": "Taiwan",
    "ZZ": "Unknown", "XK": "Kosovo", "PS": "Palestine", "CV": "Cape Verde",
    "CZ": "Czechia", "SZ": "Eswatini", "MK": "North Macedonia",
}

mapping = {}
for c in codes:
    if c in OVERRIDES:
        mapping[c] = OVERRIDES[c]; continue
    name = c
    if have:
        obj = pycountry.countries.get(alpha_2=c)
        if obj:
            name = getattr(obj, "common_name", None) or obj.name
    mapping[c] = name

# sanitized filename version (no spaces/punct issues): keep letters/digits, spaces->underscore
def fname(n):
    return "".join(ch if (ch.isalnum() or ch in " -") else "" for ch in n).strip().replace(" ", "_")

multi = {c: (n, fname(n)) for c, n in mapping.items() if " " in n or n == c}
print("\n--- multi-word / unresolved (code -> name -> filename) ---")
for c in sorted(multi): print(f"  {c}: {multi[c][0]!r} -> {multi[c][1]}.parquet")
print("\n--- sample resolved ---")
for c in ["TN", "FR", "ZA", "IN", "ZZ"]:
    print(f"  admin:{c}/{fname(mapping[c])}.parquet")

with open("/u/cholmes/ftw-crs-fix/country_names.json", "w") as f:
    json.dump({c: fname(mapping[c]) for c in codes}, f)
print("\nwrote country_names.json (code -> filename stem)")
print("any unresolved (name==code)?:", [c for c in codes if mapping[c] == c])
