"""
Sélection mensuelle Mau Plan — matière première de la newsletter.

Ne réinterroge aucune API. Relit les CSV hebdomadaires du mois (reports/AAAA-MM-JJ/veille.csv),
qui sont déjà dédoublonnés entre semaines, et garde une sélection courte et traçable :
  - Section 1 : auteurs affiliés en Afrique
  - Section 2 : sujet Afrique, auteurs hors Afrique
  - Bloc Diaspora : travaux de la section 2 qui portent sur les populations noires hors Afrique
Chaque rapport commence par un bilan de couverture : semaines manquantes ou dégradées.
Une newsletter qui dit « ce mois-ci » doit savoir ce qu'elle n'a pas vu.

Usage : python mensuel.py            → mois précédent
        python mensuel.py 2026-10    → mois donné
"""

import csv
import datetime as dt
import html
import re
import sys
from pathlib import Path

import config as C
from veille import HTML_CSS, snippet, title_key

ROOT = Path(__file__).parent
REPORTS_DIR = ROOT / "reports"
OUT_ROOT = REPORTS_DIR / "mensuel"

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

DIASPORA_RX = [re.compile(r"(?<!\w)" + re.escape(t) + r"(?!\w)", re.I) for t in C.BLACK_POP_TERMS]


# ════════════════════════════════════════════════════════════════════
# LECTURE
# ════════════════════════════════════════════════════════════════════
def target_month(argv):
    if len(argv) > 1:
        y, m = map(int, argv[1].split("-"))
        return y, m
    first = dt.date.today().replace(day=1)
    prev = first - dt.timedelta(days=1)
    return prev.year, prev.month


def weekly_dirs(y, m):
    prefix = f"{y:04d}-{m:02d}-"
    return sorted(d for d in REPORTS_DIR.iterdir() if d.is_dir() and d.name.startswith(prefix))


def read_rows(csv_path):
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        has_abstract = "resume" in (reader.fieldnames or [])
        rows = []
        for r in reader:
            r["has_abstract_col"] = has_abstract
            r["score"] = int(r.get("score") or 0)
            r["resume"] = r.get("resume", "") or ""
            rows.append(r)
    return rows


def coverage(y, m, dirs):
    """Une ligne par vendredi du mois : rapport présent, sources en échec."""
    today = dt.date.today()
    d = dt.date(y, m, 1)
    fridays = []
    while d.month == m:
        if d.weekday() == 4 and d <= today:
            fridays.append(d)
        d += dt.timedelta(days=1)

    by_date = {dd.name: dd for dd in dirs}
    lines, n_bad = [], 0
    for fr in fridays:
        # Le run peut tomber un autre jour (lancement manuel) : on prend le rapport le plus proche.
        near = sorted((k for k in by_date if abs((dt.date.fromisoformat(k) - fr).days) <= 3),
                      key=lambda k: abs((dt.date.fromisoformat(k) - fr).days))
        if not near:
            lines.append((fr.isoformat(), "MANQUANT", "aucun rapport cette semaine"))
            n_bad += 1
            continue
        md = (by_date[near[0]] / "veille.md")
        status = ""
        if md.exists():
            mm = re.search(r"\*\*État des sources :\*\* (.+)", md.read_text(encoding="utf-8"))
            status = mm.group(1) if mm else ""
        issues = []
        for part in status.split(" ; "):
            if "ÉCHEC" in part:
                issues.append(part.split(" : ")[0] + " en échec")
            q = re.search(r"(\d+)/(\d+) requêtes", part)
            if q and int(q.group(1)) < int(q.group(2)) * C.S2_MIN_SUCCESS_RATIO:
                issues.append(f"S2 {q.group(1)}/{q.group(2)} requêtes")
            if "plafond atteint" in part:
                issues.append(part.split(" : ")[0] + " plafonné (liste incomplète)")
        state = "DÉGRADÉ" if any("échec" in i or "requêtes" in i for i in issues) else "OK"
        n_bad += state != "OK"
        lines.append((near[0], state, ", ".join(issues) or "sources complètes"))
    return lines, n_bad


# ════════════════════════════════════════════════════════════════════
# SÉLECTION
# ════════════════════════════════════════════════════════════════════
def eligible(r):
    if C.MONTHLY_EXCLUDE_PREPRINTS and r.get("type") == "preprint":
        return False
    if C.MONTHLY_REQUIRE_DOI and not r.get("doi"):
        return False
    # Le résumé n'est exigé que pour les CSV qui l'enregistrent (à partir du 23/10/2026).
    if C.MONTHLY_REQUIRE_ABSTRACT and r["has_abstract_col"] and not r["resume"]:
        return False
    return True


def is_diaspora(r):
    text = f"{r.get('titre', '')} {r.get('resume', '')}"
    return any(rx.search(text) for rx in DIASPORA_RX)


def select(rows):
    seen, pool = set(), []
    for r in sorted(rows, key=lambda x: -x["score"]):
        k = (r.get("doi") or "").lower() or title_key(r.get("titre", ""))
        if k in seen or not eligible(r):
            continue
        seen.add(k)
        pool.append(r)

    out = {}
    for sec in ("1", "2"):
        sec_rows = [r for r in pool if r["section"] == sec]
        doms = {d: [r for r in sec_rows if r["domaine"] == d][: C.MONTHLY_PER_DOMAIN]
                for d in C.DOMAINS}
        outside = [r for r in sec_rows if r["domaine"] == "hors domaines"][: C.MONTHLY_TOP_OUTSIDE]
        out[sec] = (doms, outside, len(sec_rows))
    diaspora = [r for r in pool if r["section"] == "2" and is_diaspora(r)]
    return out, diaspora[: C.MONTHLY_PER_DOMAIN * 2], len(diaspora), len(pool)


# ════════════════════════════════════════════════════════════════════
# RENDU
# ════════════════════════════════════════════════════════════════════
def authors_short(s):
    names = [n.strip() for n in (s or "").split(";") if n.strip()]
    if not names:
        return "auteurs non renseignés"
    return ", ".join(names[:3]) + (" et al." if len(names) > 3 else "")


def item_links(r):
    out = []
    if r.get("doi"):
        out.append(("DOI", r["doi"]))
    if r.get("lien_pdf"):
        out.append(("PDF libre", r["lien_pdf"]))
    return out


def md_item(r):
    lk = " | ".join(f"[{a}]({u})" for a, u in item_links(r))
    pays = f" | {r['pays_africains'].upper()}" if r.get("pays_africains") not in ("", "?") else ""
    L = [f"- **{r['titre']}**",
         f"  {r.get('revue') or 'revue non renseignée'}, {r.get('date')} | {r.get('type')}{pays}",
         f"  {authors_short(r.get('auteurs'))} | score {r['score']} | {lk}"]
    if r["resume"]:
        L.append(f"  > {snippet(r['resume'], 300)}")
    elif not r["has_abstract_col"]:
        L.append("  > _résumé non enregistré (semaine antérieure au 23/10/2026) — à lire via le DOI_")
    return "\n".join(L)


def build_md(y, m, cov, n_bad, sel, diaspora, n_dia, n_pool, n_raw):
    L = [f"# Sélection mensuelle Mau Plan — {MOIS[m - 1]} {y}", ""]
    L.append(f"{n_raw} travaux signalés dans les veilles hebdomadaires du mois ; "
             f"{n_pool} remplissent les critères newsletter "
             f"(évalués par les pairs, DOI, résumé quand il est disponible).")
    L += ["", "## Couverture du mois", ""]
    if n_bad:
        L.append(f"**Attention : {n_bad} semaine(s) incomplète(s).** Ne pas écrire « les études du mois » "
                 "sans le préciser aux lecteurs.")
        L.append("")
    L += [f"- {d} — **{s}** — {txt}" for d, s, txt in cov] or ["- aucun vendredi écoulé"]
    L.append("")
    for sec, title in (("1", "Auteurs affiliés en Afrique"),
                       ("2", "Sur l'Afrique, auteurs hors Afrique")):
        doms, outside, n = sel[sec]
        L += [f"## Section {sec} — {title} ({n} éligibles)", ""]
        for d, cfg in C.DOMAINS.items():
            L += [f"### {cfg['icon']} {cfg['label']}", ""]
            L += [md_item(r) for r in doms[d]] or ["_Rien de retenu._"]
            L.append("")
        L += ["### Hors domaines Mau Plan", ""]
        L += [md_item(r) for r in outside] or ["_Rien de retenu._"]
        L.append("")
    L += [f"## Populations noires hors Afrique ({n_dia} éligibles)", "",
          "_Travaux de la section 2 dont le titre ou le résumé nomme explicitement une population "
          "noire ou afrodescendante (liste BLACK_POP_TERMS de config.py)._", ""]
    L += [md_item(r) for r in diaspora] or ["_Rien de retenu._"]
    L += ["", "---", "Sélection automatique par score : elle trie, elle ne juge pas. "
          "Lire l'étude avant de la citer."]
    return "\n".join(L)


def html_item(r):
    e = html.escape
    lk = "".join(f'<a class="{"pdf" if a == "PDF libre" else ""}" href="{e(u)}" target="_blank" '
                 f'rel="noopener">{e(a)}</a>' for a, u in item_links(r))
    abs_ = f'<p class="abs">{e(snippet(r["resume"], 420))}</p>' if r["resume"] else ""
    return (f'<article class="item"><h3>{e(r["titre"])}</h3>'
            f'<p class="meta">{e(r.get("revue") or "revue non renseignée")}, {e(r.get("date", ""))} · '
            f'{e(authors_short(r.get("auteurs")))} · score {r["score"]}</p>{abs_}'
            f'<div class="links">{lk}</div></article>')


def build_html(y, m, cov, n_bad, sel, diaspora, n_dia, n_pool, n_raw):
    e = html.escape
    warn = (f"<div class='status'>⚠ {n_bad} semaine(s) incomplète(s) ce mois-ci</div>" if n_bad
            else "<div class='status'>Couverture complète</div>")
    P = ['<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1">',
         f"<title>Sélection Mau Plan — {MOIS[m - 1]} {y}</title>",
         '<link href="https://fonts.googleapis.com/css2?family=Fraunces:wght@600;900&family='
         'Plus+Jakarta+Sans:wght@400;600&display=swap" rel="stylesheet">',
         f"<style>{HTML_CSS}</style></head><body><div class='kente'></div>",
         f"<header><h1>La sélection de {MOIS[m - 1]} {y}</h1>",
         f"<p>{n_pool} travaux retenus sur {n_raw} signalés dans le mois.</p>{warn}</header><main>",
         "<h2>Couverture du mois</h2><details open><summary>Semaine par semaine</summary>"]
    P += [f"<p class='empty'><strong>{e(d)} — {e(s)}</strong> · {e(t)}</p>" for d, s, t in cov]
    P.append("</details>")
    for sec, title in (("1", "Auteurs affiliés en Afrique"),
                       ("2", "Sur l'Afrique, auteurs hors Afrique")):
        doms, outside, _ = sel[sec]
        P.append(f"<h2>{e(title)}</h2>")
        for i, (d, cfg) in enumerate(C.DOMAINS.items()):
            P.append(f"<details{' open' if i == 0 else ''}><summary>{cfg['icon']} {e(cfg['label'])}"
                     f"<span>{len(doms[d])}</span></summary>")
            P += [html_item(r) for r in doms[d]] or ["<p class='empty'>Rien de retenu.</p>"]
            P.append("</details>")
        P.append(f"<details><summary>Hors domaines<span>{len(outside)}</span></summary>")
        P += [html_item(r) for r in outside] or ["<p class='empty'>Rien de retenu.</p>"]
        P.append("</details>")
    P.append(f"<h2>Populations noires hors Afrique</h2><details open><summary>Diaspora"
             f"<span>{len(diaspora)} sur {n_dia}</span></summary>")
    P += [html_item(r) for r in diaspora] or ["<p class='empty'>Rien de retenu.</p>"]
    P.append("</details></main></body></html>")
    return "\n".join(P)


def write_csv(path, sel, diaspora):
    cols = ["bloc", "section", "domaine", "score", "titre", "auteurs", "pays_africains", "revue",
            "date", "type", "doi", "lien_pdf", "resume"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cols)
        for sec, (doms, outside, _) in sel.items():
            for r in [x for v in doms.values() for x in v] + outside:
                w.writerow([f"section {sec}"] + [r.get(c, "") for c in cols[1:]])
        for r in diaspora:
            w.writerow(["diaspora"] + [r.get(c, "") for c in cols[1:]])


# ════════════════════════════════════════════════════════════════════
def main():
    y, m = target_month(sys.argv)
    dirs = weekly_dirs(y, m)
    rows = []
    for d in dirs:
        if (d / "veille.csv").exists():
            rows += read_rows(d / "veille.csv")
    cov, n_bad = coverage(y, m, dirs)
    sel, diaspora, n_dia, n_pool = select(rows)
    args = (y, m, cov, n_bad, sel, diaspora, n_dia, n_pool, len(rows))

    out = OUT_ROOT / f"{y:04d}-{m:02d}"
    out.mkdir(parents=True, exist_ok=True)
    md, ht = build_md(*args), build_html(*args)
    (out / "selection.md").write_text(md, encoding="utf-8")
    (out / "selection.html").write_text(ht, encoding="utf-8")
    write_csv(out / "selection.csv", sel, diaspora)
    (OUT_ROOT / "latest.md").write_text(md, encoding="utf-8")
    (OUT_ROOT / "latest.html").write_text(ht, encoding="utf-8")
    print(f"Sélection {y}-{m:02d} : {n_pool} éligibles sur {len(rows)}, {n_bad} semaine(s) dégradée(s) → {out}")


if __name__ == "__main__":
    main()
