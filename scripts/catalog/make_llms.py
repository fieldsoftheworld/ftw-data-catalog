#!/usr/bin/env python3
"""Generate an llms.txt for each item (and the collection) in the confidence collection.

Portolan-nl-style: a rich markdown brief per layer with access snippets, an asset table, a band
schema table, caveats, and links. Reads the built item JSONs for bands/proj/stats and HEADs the
public COG URLs for sizes (works whether files are at the flat or restructured location). Rerunnable.
"""
from __future__ import annotations
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # repo root (scripts/ -> ..)
COLL = ROOT / "predictions" / "confidence"
PUB = "https://data.source.coop/ftw/global-data/predictions/confidence"
PAPER = "https://arxiv.org/abs/2605.11055"
PAPER_CITE = (
    "Robinson, C., Muhawenayo, G., Khanal, S., Fang, Z., Corley, I., Tárano, A. M., Estes, L., "
    "Marcus, J., Jacobs, N., Kerner, H., Becker-Reshef, I., & Lavista Ferres, J. M. (2026). "
    "The first global agricultural field boundary map at 10 m resolution. arXiv:2605.11055."
)
ORDER = ["confidence", "field-density", "entropy", "crop-consensus", "precision-recall"]
TITLES = {
    "confidence": "Modeled confidence layer (500 m)",
    "field-density": "Field & boundary prediction density (500 m)",
    "entropy": "Model entropy (500 m)",
    "crop-consensus": "Cropland consensus count (500 m)",
    "precision-recall": "Precision & recall vs cropland agreement (500 m)",
}
# Optional per-item titiler preview (url-COG-relative, params) for a browser preview link.
PREVIEW = {
    "confidence": ("confidence/prue_v1_confidence_global.tif", "rescale=0,0.578178&colormap_name=rdylgn&nodata=-1"),
    "field-density": ("field-density/prue_v1_field_area_500m_fieldsonly.tif", "rescale=0,255&colormap_name=viridis&nodata=0"),
    "entropy": ("entropy/prue_v1_entropy_500m.tif", "rescale=0,20&colormap_name=magma&bidx=1"),
    "crop-consensus": ("crop-consensus/prue_v1_crop_count_mean_500m.tif", "rescale=0,8&colormap_name=ylgn&nodata=0"),
    "precision-recall": ("precision-recall/prue_v1_precision_recall_500m.tif", "rescale=0,1&colormap_name=viridis&bidx=1"),
}
NOTES = {
    "confidence": [
        "Conservative outside the FTW training distribution (e.g. smallholder systems): real fields "
        "there may receive low confidence. In such regions prefer the unfiltered density and the "
        "continuous confidence over the default 0.4 threshold.",
        "Cell-level reliability — do not infer individual-polygon geometric accuracy from it.",
    ],
    "field-density": [
        "The `_filtered` variant is a distinct default-filtered product; its exact threshold/method "
        "is pending author confirmation (its values differ from the explicit conf0.4/conf0.5 ones).",
        "Counts are per 500 m cell out of a maximum of 2500 (= 50×50 of the 10 m model pixels).",
    ],
    "entropy": [
        "Stored values exceed the raw 3-class Shannon-entropy range (≈0–1.1), so treat the layer as a "
        "relative uncertainty indicator rather than entropy in nats; see the paper Methods.",
    ],
    "crop-consensus": [
        "Year-independent external reference (not a PRUE output). Range 0–8; practical max 7 outside "
        "Africa, where Digital Earth Africa is unavailable.",
    ],
    "precision-recall": [
        "`*_gt1` bands use cropland agreement of ≥ 2 datasets; `*_gt2` use ≥ 3 (the paper's k∈{2,3}).",
        "Measured against the cropland-consensus layer, not ground truth.",
    ],
}


def head_size(url: str) -> str:
    # Try the given (restructured) URL, then the flat fallback (pre-restructure).
    flat = PUB + "/" + url.rsplit("/", 1)[1]
    for cand in (url, flat):
        try:
            req = urllib.request.Request(cand, method="HEAD", headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(req, timeout=30) as r:
                n = int(r.headers.get("Content-Length", 0))
                if n:
                    return human(n)
        except Exception:
            continue
    return "—"


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def fmt_range(stats):
    if not stats:
        return "—"
    return f"{stats['minimum']:.3g} – {stats['maximum']:.3g}"


def gen_item(item_id: str) -> str:
    j = json.loads((COLL / item_id / f"{item_id}.json").read_text())
    assets = {k: a for k, a in j["assets"].items() if "bands" in a}  # COG (data) assets only
    desc = j["properties"]["description"]
    L = []
    L.append(f"# {TITLES[item_id]} — Fields of the World / PRUE\n")
    L.append(desc + "\n")
    L.append(f"**Part of:** [FTW Global — Prediction Confidence & Quality Layers](../collection.json) "
             f"· [Fields of the World](https://fieldsofthe.world)  ")
    L.append(f"**Paper:** [Robinson et al. 2026]({PAPER})  ")
    L.append(f"**License:** [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)  ")
    L.append(f"**Temporal:** {j['properties']['start_datetime'][:10]} – {j['properties']['end_datetime'][:10]} "
             f"({j['properties']['ftw:temporal_basis']})\n")

    L.append("## How to access\n")
    L.append(f"Base URL: `{PUB}/{item_id}/`  ")
    L.append("Common grid: EPSG:4326, 86400×34560 px, bbox [-180, -60, 180, 84], ~0.004167°/px (~500 m). "
             "All files are Cloud-Optimized GeoTIFFs (range-request friendly).\n")
    L.append("| Asset | File | CRS | Bands | Size |")
    L.append("|---|---|---|---|---|")
    for key, a in assets.items():
        fname = a["href"].lstrip("./")
        size = head_size(f"{PUB}/{item_id}/{fname}")
        L.append(f"| `{key}` | `{fname}` | {a.get('proj:code','')} | {len(a['bands'])} | {size} |")
    L.append("")
    # pick the primary data asset for the snippet
    data_key = "data" if "data" in assets else next(iter(assets))
    data_file = assets[data_key]["href"].lstrip("./")
    L.append("```python")
    L.append("import rasterio")
    L.append(f'url = "{PUB}/{item_id}/{data_file}"')
    L.append("with rasterio.open(url) as ds:   # COG: only the bytes you read are fetched")
    L.append("    arr = ds.read(1, masked=True)   # add window=... to subset by bbox")
    L.append("```")
    if item_id in PREVIEW:
        cog, params = PREVIEW[item_id]
        L.append(f"\nBrowser preview (titiler): "
                 f"`https://titiler.xyz/cog/preview.png?url={PUB}/{cog}&{params}`\n")

    L.append("## Bands\n")
    L.append("| Asset | Band | dtype | nodata | range (min–max) | Meaning |")
    L.append("|---|---|---|---|---|---|")
    for key, a in assets.items():
        for b in a["bands"]:
            nd = b.get("nodata", "—")
            rng = fmt_range(b.get("statistics"))
            L.append(f"| `{key}` | `{b['name']}` | {b['data_type']} | {nd} | {rng} | {b.get('description','')} |")
    L.append("")

    L.append("## Notes\n")
    for n in NOTES.get(item_id, []):
        L.append(f"- {n}")
    L.append("")

    L.append("## Related layers\n")
    for sib in ORDER:
        if sib == item_id:
            continue
        L.append(f"- [{TITLES[sib]}](../{sib}/{sib}.json)")
    L.append(f"- Collection: [collection.json](../collection.json) · [README](../README.md)")
    L.append("")

    L.append("## Cite\n")
    L.append(PAPER_CITE)
    L.append("")
    return "\n".join(L)


def gen_collection() -> str:
    L = []
    L.append("# FTW Global — Prediction Confidence & Quality Layers (500 m)\n")
    L.append(
        "Global 500 m raster layers that quantify where the "
        "[PRUE](https://github.com/fieldsoftheworld/ftw-baselines/releases) global agricultural "
        "field-boundary predictions can be trusted, part of "
        "[Fields of the World](https://fieldsofthe.world) "
        "([Robinson et al. 2026]({p})). Derived from the full-resolution (10 m) model outputs on a "
        "common global grid (EPSG:4326, ~0.004167°/px, −180..180 lon, −60..84 lat; each 500 m cell "
        "≈ 50×50 of the 10 m pixels). Temporal coverage inferred as the 2025 prediction year "
        "(the cropland-consensus layer is year-independent); pending author confirmation.\n".format(p=PAPER)
    )
    L.append(f"**Catalog:** [collection.json]({PUB}/collection.json) · [README]({PUB}/README.md)  ")
    L.append(f"**License:** [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/)  ")
    L.append(f"**Base URL:** `{PUB}/`\n")
    L.append("## Layers (one STAC item each, with its own llms.txt)\n")
    blurbs = {
        "confidence": "Modeled confidence score (RF on model-internal indicators). Default filter conf ≥ 0.4.",
        "field-density": "Field & boundary pixel counts per cell — unfiltered, conf-filtered, fields-only, web-display.",
        "entropy": "Mean model entropy for the field and boundary classes (uncertainty).",
        "crop-consensus": "Mean agreement of 8 external global cropland datasets (0–8).",
        "precision-recall": "Per-cell precision/recall of fields vs cropland agreement (≥2 and ≥3 datasets).",
    }
    for it in ORDER:
        L.append(f"- **[{TITLES[it]}]({it}/{it}.json)** — {blurbs[it]} "
                 f"([llms.txt]({it}/llms.txt))")
    L.append("")
    L.append("## Visualization\n")
    L.append("Each item carries one or more named styles via the STAC "
             "[render extension](https://github.com/stac-extensions/render) "
             "(`properties.renders`): a colormap + rescale + nodata applied directly to a COG band "
             "(no tile server). Confidence uses an RdYlGn ramp rescaled 0–0.578 and field density a "
             "magenta→green ramp, matching the FTW inference app. Viewers such as the Portolan browser "
             "render these client-side; other tools (e.g. titiler) accept the same parameters.")
    L.append("")
    L.append("## Cite\n")
    L.append(PAPER_CITE)
    L.append("")
    return "\n".join(L)


def main():
    for it in ORDER:
        (COLL / it / "llms.txt").write_text(gen_item(it))
        print(f"wrote predictions/confidence/{it}/llms.txt")
    (COLL / "llms.txt").write_text(gen_collection())
    print("wrote predictions/confidence/llms.txt")


if __name__ == "__main__":
    main()
