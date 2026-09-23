"""
Veille scientifique hebdomadaire Mau Plan.

Section 1 : travaux dont au moins un auteur est affilié à une institution africaine.
Section 2 : travaux sur l'Afrique ou les populations noires, sans auteur affilié en Afrique.
Chaque section : domaines Mau Plan classés, puis top hors domaines.

Sources : OpenAlex (principale), PubMed (complément section 1), AfricArXiv via OSF.
Une source en panne n'arrête pas le rapport : elle est signalée en tête.
"""

import csv
import datetime as dt
import html
import json
import os
import re
import time
from pathlib import Path

import requests

import config as C

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
SEEN_FILE = DATA_DIR / "seen.json"

MAILTO = os.environ.get("OPENALEX_MAILTO", "")
OA_KEY = os.environ.get("OPENALEX_API_KEY", "")
NCBI_KEY = os.environ.get("NCBI_API_KEY", "")

SESSION = requests.Session()
SESSION.headers["User-Agent"] = f"MauPlan-Veille/1.0 (mailto:{MAILTO or 'non-renseigne'})"

OA_SELECT = (
    "id,doi,title,publication_date,type,open_access,best_oa_location,"
    "primary_location,authorships,primary_topic,abstract_inverted_index"
)


# ════════════════════════════════════════════════════════════════════
# HTTP
# ════════════════════════════════════════════════════════════════════
def http(method, url, **kw):
    """Requête avec reprises sur 429/5xx."""
    for attempt in range(5):
        try:
            r = SESSION.request(method, url, timeout=60, **kw)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt + 1)
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"Échec après 5 tentatives : {url}")


# ════════════════════════════════════════════════════════════════════
# OPENALEX
# ════════════════════════════════════════════════════════════════════
def openalex(filter_str, max_results):
    out, cursor, truncated = [], "*", False
    while cursor:
        params = {"filter": filter_str, "per-page": 200, "cursor": cursor, "select": OA_SELECT}
        if MAILTO:
            params["mailto"] = MAILTO
        if OA_KEY:
            params["api_key"] = OA_KEY
        data = http("GET", "https://api.openalex.org/works", params=params).json()
        results = data.get("results", [])
        out.extend(results)
        if not results:
            break
        if len(out) >= max_results:
            truncated = True
            break
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(0.15)
    return out, truncated


def rebuild_abstract(inv):
    if not inv:
        return ""
    pos = [(p, w) for w, ps in inv.items() for p in ps]
    return " ".join(w for _, w in sorted(pos))


def clean_doi(doi):
    if not doi:
        return ""
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.I).lower()


def norm_openalex(w):
    title = (w.get("title") or "").strip()
    if not title:
        return None
    auths = w.get("authorships") or []
    names = [(a.get("author") or {}).get("display_name", "") for a in auths]
    countries_per_author = [set(c.lower() for c in (a.get("countries") or [])) for a in auths]
    african = set()
    n_afr = 0
    for cs in countries_per_author:
        hit = cs & set(C.AFRICA_CC)
        african |= hit
        n_afr += bool(hit)
    first_afr = bool(countries_per_author and countries_per_author[0] & set(C.AFRICA_CC))
    all_countries = set().union(*countries_per_author) if countries_per_author else set()

    prim = w.get("primary_location") or {}
    src = prim.get("source") or {}
    best = w.get("best_oa_location") or {}
    oa = w.get("open_access") or {}
    topic = w.get("primary_topic") or {}
    doi = clean_doi(w.get("doi"))

    return {
        "key": doi or w.get("id", ""),
        "doi": doi,
        "title": title,
        "authors": names,
        "african_countries": sorted(african),
        "all_countries": sorted(all_countries),
        "first_author_african": first_afr,
        "african_share": (n_afr / len(auths)) if auths else 0.0,
        "journal": src.get("display_name") or "",
        "publisher": src.get("host_organization_name") or "",
        "is_core": bool(src.get("is_core")),
        "is_in_doaj": bool(src.get("is_in_doaj")),
        "date": w.get("publication_date") or "",
        "type": w.get("type") or "",
        "is_oa": bool(oa.get("is_oa")),
        "pdf_url": best.get("pdf_url") or "",
        "landing_url": prim.get("landing_page_url") or best.get("landing_page_url") or "",
        "abstract": rebuild_abstract(w.get("abstract_inverted_index")),
        "topic": topic.get("display_name") or "",
        "field": ((topic.get("field") or {}).get("display_name")) or "",
        "source": "OpenAlex",
    }


def or_query(terms):
    return " OR ".join(f'"{t}"' if " " in t or "-" in t or "'" in t else t for t in terms)


# ════════════════════════════════════════════════════════════════════
# PUBMED (complément section 1 : indexation souvent plus rapide)
# ════════════════════════════════════════════════════════════════════
def pubmed(days):
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    term = " OR ".join(f'"{n}"[ad]' for n in C.COUNTRY_NAMES_EN)
    p = {"db": "pubmed", "term": term, "reldate": days, "datetype": "edat",
         "retmax": 0, "usehistory": "y", "retmode": "json"}
    if NCBI_KEY:
        p["api_key"] = NCBI_KEY
    es = http("POST", base + "esearch.fcgi", data=p).json()["esearchresult"]
    count = int(es.get("count", 0))
    webenv, qk = es.get("webenv"), es.get("querykey")
    recs = []
    for start in range(0, min(count, 10000), 400):
        q = {"db": "pubmed", "WebEnv": webenv, "query_key": qk,
             "retstart": start, "retmax": 400, "retmode": "json"}
        if NCBI_KEY:
            q["api_key"] = NCBI_KEY
        res = http("POST", base + "esummary.fcgi", data=q).json().get("result", {})
        for uid in res.get("uids", []):
            it = res.get(uid, {})
            doi = ""
            for aid in it.get("articleids", []):
                if aid.get("idtype") == "doi":
                    doi = clean_doi(aid.get("value"))
            title = (it.get("title") or "").strip()
            if not title:
                continue
            pubtypes = [t.lower() for t in it.get("pubtype", [])]
            recs.append({
                "key": doi or f"pmid:{uid}",
                "doi": doi,
                "title": title,
                "authors": [a.get("name", "") for a in it.get("authors", [])],
                "african_countries": ["?"],
                "all_countries": [],
                "first_author_african": False,
                "african_share": 0.0,
                "journal": it.get("fulljournalname") or it.get("source") or "",
                "date": it.get("sortpubdate", "")[:10].replace("/", "-"),
                "type": "review" if "review" in pubtypes else "article",
                "is_oa": False,
                "pdf_url": "",
                "landing_url": f"https://pubmed.ncbi.nlm.nih.gov/{uid}/",
                "abstract": "",
                "topic": "",
                "field": "",
                "source": "PubMed",
            })
        time.sleep(0.12 if NCBI_KEY else 0.4)
    return recs


# ════════════════════════════════════════════════════════════════════
# AFRICARXIV (preprints, via OSF)
# ════════════════════════════════════════════════════════════════════
def africarxiv(since):
    url = "https://api.osf.io/v2/preprints/"
    params = {"filter[provider]": "africarxiv",
              "filter[date_created][gte]": since, "page[size]": 100}
    recs = []
    while url:
        data = http("GET", url, params=params).json()
        params = None  # le lien "next" contient déjà les paramètres
        for it in data.get("data", []):
            a = it.get("attributes", {})
            links = it.get("links", {})
            doi = clean_doi(links.get("preprint_doi") or "")
            title = (a.get("title") or "").strip()
            if not title:
                continue
            recs.append({
                "key": doi or links.get("html", it.get("id", "")),
                "doi": doi,
                "title": title,
                "authors": [],
                "african_countries": ["?"],
                "all_countries": [],
                "first_author_african": False,
                "african_share": 0.0,
                "journal": "AfricArXiv",
                "date": (a.get("date_published") or a.get("date_created") or "")[:10],
                "type": "preprint",
                "is_oa": True,
                "pdf_url": "",
                "landing_url": links.get("html", ""),
                "abstract": a.get("description") or "",
                "topic": "",
                "field": "",
                "source": "AfricArXiv",
            })
        url = (data.get("links") or {}).get("next")
        time.sleep(0.3)
    return recs


# ════════════════════════════════════════════════════════════════════
# CLASSEMENT
# ════════════════════════════════════════════════════════════════════
KW_RX = {
    dom: [re.compile(r"(?<!\w)" + re.escape(k) + r"(?!\w)", re.I) for k in cfg["keywords"]]
    for dom, cfg in C.DOMAINS.items()
}


def domain_scores(rec):
    t, a = rec["title"], rec["abstract"]
    scores = {}
    for dom, rxs in KW_RX.items():
        s = 0
        for rx in rxs:
            if rx.search(t):
                s += 3
            elif a and rx.search(a):
                s += 1
        scores[dom] = s
    return scores


def quality_bonus(rec, section):
    b = 0
    if rec.get("is_core"):      # revue reconnue (sources "core" OpenAlex/CWTS)
        b += 3
    if rec.get("is_in_doaj"):   # libre accès contrôlé par le DOAJ
        b += 1
    if rec["is_oa"]:
        b += 1
    if rec["abstract"]:
        b += 1
    if rec["type"] == "review":
        b += 1
    if section == 1:
        if rec["first_author_african"]:
            b += 2
        b += round(rec["african_share"] * 2)
    return b


def classify(recs, section):
    domains = {d: [] for d in C.DOMAINS}
    outside = []
    for r in recs:
        sc = domain_scores(r)
        best = max(sc, key=sc.get)
        bonus = quality_bonus(r, section)
        if sc[best] >= C.MIN_DOMAIN_SCORE:
            r["domain"] = best
            r["score"] = sc[best] + bonus
            domains[best].append(r)
        else:
            r["domain"] = ""
            r["score"] = bonus
            outside.append(r)
    for d in domains:
        domains[d].sort(key=lambda x: (-x["score"], x["title"]))
    # Hors domaines : on n'y met que des travaux avec résumé, sinon impossible de juger.
    outside = [r for r in outside if r["abstract"]]
    outside.sort(key=lambda x: (-x["score"], not x.get("is_core"), -x["african_share"]))
    return domains, outside


def is_excluded(r):
    doi = r.get("doi") or ""
    if any(doi.startswith(p + "/") for p in C.EXCLUDED_DOI_PREFIXES):
        return True
    names = f"{r.get('journal', '')} {r.get('publisher', '')}".lower()
    if any(p in names for p in C.EXCLUDED_NAME_PATTERNS):
        return True
    t = r["title"].lower()
    return any(t.startswith(p) for p in C.EXCLUDED_TITLE_PATTERNS)


def title_key(t):
    return re.sub(r"\W+", "", t.lower())[:150]


def clean(recs):
    """Retire éditeurs exclus, annexes et doublons de titre. Renvoie (gardés, nb exclus)."""
    kept, titles, n = [], set(), 0
    for r in recs:
        tk = title_key(r["title"])
        if is_excluded(r) or tk in titles:
            n += 1
            continue
        titles.add(tk)
        kept.append(r)
    return kept, n


# ════════════════════════════════════════════════════════════════════
# MÉMOIRE DES ENVOIS
# ════════════════════════════════════════════════════════════════════
def load_seen():
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    return {}


def save_seen(seen, today):
    # On oublie ce qui a plus de 120 jours : la fenêtre n'en couvre que 21.
    limit = (today - dt.timedelta(days=120)).isoformat()
    seen = {k: v for k, v in seen.items() if v >= limit}
    DATA_DIR.mkdir(exist_ok=True)
    SEEN_FILE.write_text(json.dumps(seen, ensure_ascii=False, indent=0), encoding="utf-8")


# ════════════════════════════════════════════════════════════════════
# RENDU
# ════════════════════════════════════════════════════════════════════
def authors_short(names):
    names = [n for n in names if n]
    if not names:
        return "auteurs non renseignés"
    return ", ".join(names[:3]) + (" et al." if len(names) > 3 else "")


def countries_label(r):
    if r["african_countries"] == ["?"]:
        return "affiliation africaine (détail non fourni)"
    if r["african_countries"]:
        return ", ".join(c.upper() for c in r["african_countries"])
    if r["all_countries"]:
        return "auteurs : " + ", ".join(c.upper() for c in r["all_countries"][:5])
    return ""


def links(r):
    out = []
    if r["doi"]:
        out.append(("DOI", f"https://doi.org/{r['doi']}"))
    elif r["landing_url"]:
        out.append(("Page", r["landing_url"]))
    if r["pdf_url"]:
        out.append(("PDF libre", r["pdf_url"]))
    return out


def snippet(text, n):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + "…"


def type_label(t):
    return {"preprint": "PREPRINT, non évalué", "review": "revue de littérature"}.get(t, "article")


def md_item(r):
    link_str = " | ".join(f"[{lbl}]({u})" for lbl, u in links(r)) or "lien indisponible"
    lines = [
        f"- **{r['title']}**",
        f"  {r['journal'] or 'revue non renseignée'}, {r['date']} | {type_label(r['type'])} | {countries_label(r)}",
        f"  {authors_short(r['authors'])} | score {r['score']} | {link_str}",
    ]
    if r["abstract"]:
        lines.append(f"  > {snippet(r['abstract'], C.ABSTRACT_SNIPPET)}")
    return "\n".join(lines)


def build_markdown(today, window, s1, s2, status, totals):
    L = [f"# Veille scientifique Mau Plan — semaine du {today.isoformat()}", ""]
    L.append(f"Fenêtre : {window[0]} → {window[1]} (déjà signalés exclus).")
    L.append("")
    L.append("**État des sources :** " + " ; ".join(f"{k} : {v}" for k, v in status.items()))
    L.append("")
    L.append(f"**Volumes :** section 1 = {totals['s1']} nouveaux travaux ; section 2 = {totals['s2']}.")
    L.append("")
    for num, title, (domains, outside) in (
        (1, "Auteurs affiliés en Afrique", s1),
        (2, "Sujet Afrique ou populations noires, auteurs hors Afrique", s2),
    ):
        L += [f"## Section {num} — {title}", ""]
        for d, cfg in C.DOMAINS.items():
            items = domains[d]
            shown = items[: C.MD_MAX_PER_DOMAIN]
            L.append(f"### {cfg['icon']} {cfg['label']} — {len(shown)} affichés sur {len(items)}")
            L.append("")
            L += [md_item(r) for r in shown] or ["_Aucun travail cette semaine._"]
            L.append("")
        top = outside[: C.TOP_OUTSIDE]
        L += [f"### Top {len(top)} hors domaines Mau Plan", ""]
        L += [md_item(r) for r in top] or ["_Aucun._"]
        L.append("")
    L.append("---")
    L.append("Liste complète : fichier veille.csv du même dossier. "
             "Les preprints ne sont pas évalués par les pairs.")
    return "\n".join(L)


HTML_CSS = """
:root{--deep:#3D1C02;--warm:#A0522D;--gold:#D4A017;--red:#C0392B;--savanna:#E8C97E;
--baobab:#2C4A3E;--pale:#F0DDD0;--ultra:#FBF5F0;--cream:#FEF9F5;--muted:#7A5C44;--ink:#1A0A00}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Plus Jakarta Sans',system-ui,sans-serif;background:var(--cream);color:var(--ink);line-height:1.6}
.kente{height:8px;background:repeating-linear-gradient(90deg,var(--gold) 0 8px,var(--red) 8px 16px,var(--warm) 16px 24px,var(--baobab) 24px 32px)}
header{background:var(--deep);color:#fff;padding:48px 6vw 40px}
header h1{font-family:'Fraunces',Georgia,serif;font-weight:900;font-size:clamp(28px,4vw,44px);line-height:1.1;max-width:22ch}
header p{color:rgba(255,255,255,.7);margin-top:12px;max-width:70ch;font-size:15px}
.status{background:rgba(255,255,255,.08);border-radius:6px;padding:12px 16px;margin-top:20px;font-size:13px;color:var(--savanna)}
main{padding:32px 6vw 64px;max-width:1100px}
h2{font-family:'Fraunces',Georgia,serif;font-size:28px;color:var(--deep);margin:40px 0 16px}
details{background:var(--ultra);border-radius:8px;margin-bottom:14px}
summary{cursor:pointer;padding:16px 20px;font-weight:600;color:var(--deep);font-size:16px}
summary span{color:var(--muted);font-weight:400;font-size:13px;margin-left:8px}
.item{background:#fff;border-radius:6px;margin:0 16px 12px;padding:16px 18px}
.item h3{font-family:'Fraunces',Georgia,serif;font-size:17px;line-height:1.35;color:var(--deep);font-weight:600}
.meta{font-size:12.5px;color:var(--muted);margin-top:6px}
.abs{font-size:13.5px;margin-top:8px;color:#4a3a2e;max-width:75ch}
.links{margin-top:10px;display:flex;gap:8px;flex-wrap:wrap}
.links a{background:var(--deep);color:#fff;text-decoration:none;font-size:12px;font-weight:600;padding:6px 12px;border-radius:4px}
.links a.pdf{background:var(--baobab)}
.pre{background:#FDECEA;color:var(--red);font-size:11px;font-weight:700;padding:2px 8px;border-radius:3px;margin-left:6px}
.empty{padding:0 20px 16px;color:var(--muted);font-size:14px}
a:focus-visible,summary:focus-visible{outline:3px solid var(--gold);outline-offset:2px}
"""


def html_item(r):
    e = html.escape
    pre = '<span class="pre">preprint</span>' if r["type"] == "preprint" else ""
    lk = "".join(
        f'<a class="{"pdf" if lbl == "PDF libre" else ""}" href="{e(u)}" target="_blank" rel="noopener">{e(lbl)}</a>'
        for lbl, u in links(r)
    )
    abs_ = f'<p class="abs">{e(snippet(r["abstract"], 420))}</p>' if r["abstract"] else ""
    return (
        f'<article class="item"><h3>{e(r["title"])}{pre}</h3>'
        f'<p class="meta">{e(r["journal"] or "revue non renseignée")}, {e(r["date"])} · '
        f'{e(type_label(r["type"]))} · {e(countries_label(r))}<br>{e(authors_short(r["authors"]))} · score {r["score"]}</p>'
        f'{abs_}<div class="links">{lk}</div></article>'
    )


def build_html(today, window, s1, s2, status, totals):
    e = html.escape
    parts = [
        '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>Veille Mau Plan — {today.isoformat()}</title>",
        '<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@600;900&family=Plus+Jakarta+Sans:wght@400;600&display=swap" rel="stylesheet">',
        f"<style>{HTML_CSS}</style></head><body><div class='kente'></div>",
        f"<header><h1>Veille scientifique de la semaine du {today.strftime('%d/%m/%Y')}</h1>",
        f"<p>{totals['s1']} nouveaux travaux d'auteurs affiliés en Afrique, {totals['s2']} sur l'Afrique "
        f"ou les populations noires par des auteurs d'ailleurs. Publiés entre le {window[0]} et le {window[1]}.</p>",
        "<div class='status'>" + " · ".join(f"{e(k)} : {e(v)}" for k, v in status.items()) + "</div></header><main>",
    ]
    for title, (domains, outside) in (
        ("Auteurs affiliés en Afrique", s1),
        ("Sur l'Afrique et les populations noires, auteurs hors Afrique", s2),
    ):
        parts.append(f"<h2>{e(title)}</h2>")
        for i, (d, cfg) in enumerate(C.DOMAINS.items()):
            items = domains[d]
            shown = items[: C.HTML_MAX_PER_DOMAIN]
            op = " open" if i == 0 else ""
            parts.append(f"<details{op}><summary>{cfg['icon']} {e(cfg['label'])}"
                         f"<span>{len(shown)} affichés sur {len(items)}</span></summary>")
            parts += [html_item(r) for r in shown] or ["<p class='empty'>Rien cette semaine.</p>"]
            parts.append("</details>")
        top = outside[: C.TOP_OUTSIDE]
        parts.append(f"<details><summary>Hors domaines Mau Plan<span>top {len(top)}</span></summary>")
        parts += [html_item(r) for r in top] or ["<p class='empty'>Rien cette semaine.</p>"]
        parts.append("</details>")
    parts.append("</main></body></html>")
    return "\n".join(parts)


def write_csv(path, s1, s2):
    cols = ["section", "domaine", "score", "titre", "auteurs", "pays_africains", "revue",
            "date", "type", "doi", "lien_pdf", "lien_page", "source"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cols)
        for sec, (domains, outside) in ((1, s1), (2, s2)):
            rows = [r for d in domains.values() for r in d] + outside
            for r in rows:
                w.writerow([sec, r["domain"] or "hors domaines", r["score"], r["title"],
                            "; ".join(r["authors"]), ",".join(r["african_countries"]),
                            r["journal"], r["date"], r["type"],
                            f"https://doi.org/{r['doi']}" if r["doi"] else "",
                            r["pdf_url"], r["landing_url"], r["source"]])


# ════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════
def main():
    today = dt.date.today()
    seen = load_seen()
    days = C.FIRST_RUN_DAYS if not seen else C.ROLLING_DAYS
    d0, d1 = (today - dt.timedelta(days=days)).isoformat(), today.isoformat()
    date_f = f"from_publication_date:{d0},to_publication_date:{d1},type:{C.WORK_TYPES}"
    status = {}

    # ── Section 1 ──
    s1_recs = []
    try:
        raw, trunc = openalex(f"institutions.country_code:{'|'.join(C.AFRICA_CC)},{date_f}",
                              C.MAX_FETCH_SECTION1)
        s1_recs = [r for r in map(norm_openalex, raw) if r]
        status["OpenAlex S1"] = f"{len(s1_recs)} reçus" + (" (plafond atteint)" if trunc else "")
    except Exception as ex:
        status["OpenAlex S1"] = f"ÉCHEC ({ex})"

    known = {r["doi"] for r in s1_recs if r["doi"]}
    for name, fn in (("PubMed", lambda: pubmed(days)), ("AfricArXiv", lambda: africarxiv(d0))):
        try:
            extra = fn()
            new = [r for r in extra if not (r["doi"] and r["doi"] in known)]
            known |= {r["doi"] for r in new if r["doi"]}
            s1_recs += new
            status[name] = f"{len(extra)} reçus, {len(new)} ajoutés"
        except Exception as ex:
            status[name] = f"ÉCHEC ({ex})"

    # ── Section 2 ──
    s2_recs = []
    try:
        raw2, trunc_total = [], False
        terms = C.AFRICA_TERMS + C.BLACK_POP_TERMS + C.COUNTRY_NAMES_EN
        chunks = [terms[i:i + C.S2_CHUNK] for i in range(0, len(terms), C.S2_CHUNK)]
        ok = 0
        for chunk in chunks:
            try:
                part, trunc = openalex(f"title_and_abstract.search:{or_query(chunk)},{date_f}",
                                       C.MAX_FETCH_SECTION2)
                raw2 += part
                trunc_total |= trunc
                ok += 1
            except Exception:
                continue
        if ok == 0:
            raise RuntimeError(f"les {len(chunks)} requêtes ont échoué")
        s2_keys = set()
        for r in map(norm_openalex, raw2):
            if not r or r["african_countries"] or r["key"] in s2_keys:
                continue  # affiliés Afrique = section 1
            s2_keys.add(r["key"])
            s2_recs.append(r)
        status["OpenAlex S2"] = (f"{len(s2_recs)} retenus, {ok}/{len(chunks)} requêtes réussies"
                                 + (" (plafond atteint)" if trunc_total else ""))
    except Exception as ex:
        status["OpenAlex S2"] = f"ÉCHEC ({ex})"

    # ── Dédoublonnage interne + déjà signalés ──
    def fresh(recs):
        out, keys = [], set()
        for r in recs:
            k = r["key"]
            if k and k not in seen and k not in keys:
                keys.add(k)
                out.append(r)
        return out

    s1_recs = fresh(s1_recs)
    s1_keys = {r["key"] for r in s1_recs}
    s2_recs = [r for r in fresh(s2_recs) if r["key"] not in s1_keys]
    for r in s1_recs + s2_recs:          # mémorisés même si exclus : inutile de les revoir
        seen[r["key"]] = today.isoformat()
    s1_recs, x1 = clean(s1_recs)
    s2_recs, x2 = clean(s2_recs)
    status["Exclus"] = f"{x1 + x2} (éditeurs écartés, annexes, doublons)"

    s1 = classify(s1_recs, 1)
    s2 = classify(s2_recs, 2)
    totals = {"s1": len(s1_recs), "s2": len(s2_recs)}

    # ── Écriture ──
    out_dir = REPORTS_DIR / today.isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    md = build_markdown(today, (d0, d1), s1, s2, status, totals)
    ht = build_html(today, (d0, d1), s1, s2, status, totals)
    (out_dir / "veille.md").write_text(md, encoding="utf-8")
    (out_dir / "veille.html").write_text(ht, encoding="utf-8")
    write_csv(out_dir / "veille.csv", s1, s2)
    (REPORTS_DIR / "latest.md").write_text(md, encoding="utf-8")
    (REPORTS_DIR / "latest.html").write_text(ht, encoding="utf-8")

    save_seen(seen, today)

    print(f"Rapport : {out_dir}")
    for k, v in status.items():
        print(f"  {k}: {v}")
    if all(v.startswith("ÉCHEC") for k, v in status.items() if k != "Exclus"):
        raise SystemExit("Toutes les sources ont échoué.")


if __name__ == "__main__":
    main()
