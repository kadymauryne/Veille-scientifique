"""
Configuration de la veille scientifique Mau Plan.
Tout ce qui se règle sans toucher au code est ici.
"""

# ── Fenêtre de recherche ─────────────────────────────────────────────
# Premier lancement : 7 jours. Ensuite 21 jours glissants, en excluant
# ce qui a déjà été signalé (data/seen.json). Cela rattrape les articles
# indexés avec retard sans créer de doublons.
FIRST_RUN_DAYS = 7
ROLLING_DAYS = 21

# ── Plafonds ─────────────────────────────────────────────────────────
MAX_FETCH_SECTION1 = 30000   # garde-fou OpenAlex, section auteurs africains (12000 était atteint chaque semaine)
MAX_FETCH_SECTION2 = 6000    # garde-fou OpenAlex, section sujet Afrique/pop. noires
MD_MAX_PER_DOMAIN = 15       # rapport Markdown (celui qu'on lit ensemble)
HTML_MAX_PER_DOMAIN = 50     # rapport HTML (le CSV contient tout)
TOP_OUTSIDE = 10             # top hors domaines Mau Plan, par section
ABSTRACT_SNIPPET = 220       # caractères de résumé dans le Markdown
MIN_DOMAIN_SCORE = 3         # 1 mot-clé dans le titre, ou 3 dans le résumé

CSV_ABSTRACT_CHARS = 600     # résumé conservé dans le CSV (sert au mensuel)
S2_MIN_SUCCESS_RATIO = 0.6   # sous ce taux de requêtes S2 réussies, la veille est "dégradée"

WORK_TYPES = "article|review|preprint"
S2_CHUNK = 6   # termes par requête en section 2 (au-delà, OpenAlex sature)

# ── Exclusions (modifiable) ──────────────────────────────────────────
# Préfixes DOI d'éditeurs écartés :
#   10.56201 = IIARD ; 10.11648 = Science Publishing Group
EXCLUDED_DOI_PREFIXES = ["10.56201", "10.11648"]
# Motifs cherchés dans le nom de la revue ou de l'éditeur (minuscules).
# Zenodo et Figshare = dépôts, pas des revues (doublons, annexes).
EXCLUDED_NAME_PATTERNS = [
    "iiard", "science publishing group", "sciencepg",
    "iconic research and engineering", "zenodo", "figshare",
]
EXCLUDED_TITLE_PATTERNS = ["additional file", "supplementary material", "supplementary file"]

# ── 54 pays africains (ISO 3166-1 alpha-2) ───────────────────────────
AFRICA_CC = [
    "dz", "ao", "bj", "bw", "bf", "bi", "cv", "cm", "cf", "td", "km", "cg",
    "cd", "ci", "dj", "eg", "gq", "er", "sz", "et", "ga", "gm", "gh", "gn",
    "gw", "ke", "ls", "lr", "ly", "mg", "mw", "ml", "mr", "mu", "ma", "mz",
    "na", "ne", "ng", "rw", "st", "sn", "sc", "sl", "so", "za", "ss", "sd",
    "tz", "tg", "tn", "ug", "zm", "zw",
]

COUNTRY_NAMES_EN = [
    "Algeria", "Angola", "Benin", "Botswana", "Burkina Faso", "Burundi",
    "Cabo Verde", "Cape Verde", "Cameroon", "Central African Republic", "Chad",
    "Comoros", "Congo", "Democratic Republic of the Congo", "Cote d'Ivoire",
    "Ivory Coast", "Djibouti", "Egypt", "Equatorial Guinea", "Eritrea",
    "Eswatini", "Swaziland", "Ethiopia", "Gabon", "Gambia", "Ghana", "Guinea",
    "Guinea-Bissau", "Kenya", "Lesotho", "Liberia", "Libya", "Madagascar",
    "Malawi", "Mali", "Mauritania", "Mauritius", "Morocco", "Mozambique",
    "Namibia", "Niger", "Nigeria", "Rwanda", "Sao Tome and Principe",
    "Senegal", "Seychelles", "Sierra Leone", "Somalia", "South Africa",
    "South Sudan", "Sudan", "Tanzania", "Togo", "Tunisia", "Uganda", "Zambia",
    "Zimbabwe",
]

# ── Section 2 : sujet Afrique / populations noires, tout auteur ──────
AFRICA_TERMS = [
    "Africa", "African", "sub-Saharan", "Sahel", "West Africa", "East Africa",
    "Afrique", "africain", "africaine", "subsaharienne",
]
# Expressions exactes uniquement : "Black" seul ramènerait black carbon,
# black box, black tea…
BLACK_POP_TERMS = [
    "Black women", "Black men", "Black adults", "Black children",
    "Black patients", "Black people", "Black individuals", "Black Americans",
    "Black British", "African American", "African Americans",
    "African descent", "Afro-descendant", "Afro-Caribbean", "Afro-Brazilian",
    "African diaspora", "femmes noires", "afrodescendant",
]

# ── Domaines Mau Plan ────────────────────────────────────────────────
# Clés identiques aux data-cat du site (env, sante, alim, social).
# Mots-clés en minuscules, FR + EN. Expressions multi-mots autorisées.
DOMAINS = {
    "env": {
        "label": "Environnement & Eau",
        "icon": "🌿",
        "keywords": [
            "water quality", "drinking water", "groundwater", "lagoon", "lake",
            "river", "wetland", "pollution", "contamination", "contaminated",
            "heavy metal", "heavy metals", "arsenic", "mercury", "cadmium",
            "lead exposure", "microplastic", "microplastics", "plastic waste",
            "pesticide residue", "climate change", "climate variability",
            "rainfall", "drought", "flood", "flooding", "deforestation",
            "land use", "land cover", "erosion", "air quality", "air pollution",
            "pm2.5", "particulate matter", "e-waste", "solid waste", "landfill",
            "artisanal mining", "gold mining", "galamsey", "biodiversity",
            "medicinal plant", "medicinal plants", "ethnobotany",
            "ethnobotanical", "phytochemical", "endocrine disruptor",
            "endocrine disruptors", "pfas", "toxicity",
            "eau potable", "eaux souterraines", "lagune", "métaux lourds",
            "orpaillage", "déchets", "changement climatique", "inondation",
            "sécheresse", "plantes médicinales", "pharmacopée",
        ],
    },
    "sante": {
        "label": "Santé au travail & santé des femmes",
        "icon": "🩺",
        "keywords": [
            "occupational", "workplace", "workers", "health workers",
            "healthcare workers", "occupational exposure", "needlestick",
            "burnout", "work stress", "job stress", "sanitation workers",
            "waste collectors", "informal workers", "farmworkers",
            "respiratory symptoms", "musculoskeletal", "ergonomic",
            "personal protective equipment", "ppe", "fish smoking",
            "hair relaxer", "hair relaxers", "skin lightening", "skin bleaching",
            "menopause", "uterine fibroids", "fibroids", "maternal health",
            "cervical cancer", "breast cancer", "preeclampsia", "stroke",
            "hypertension",
            "santé au travail", "travailleurs", "exposition professionnelle",
            "défrisage", "dépigmentation", "ménopause", "fibromes",
        ],
    },
    "alim": {
        "label": "Alimentation & Sécurité",
        "icon": "🌾",
        "keywords": [
            "food safety", "street food", "street-vended", "food security",
            "food insecurity", "nutrition", "nutritional", "diet", "dietary",
            "malnutrition", "stunting", "wasting", "micronutrient", "anaemia",
            "anemia", "fermented", "fermentation", "aflatoxin", "aflatoxins",
            "mycotoxin", "mycotoxins", "cassava", "attieke", "maize", "sorghum",
            "millet", "yam", "plantain", "cowpea", "cocoa", "smoked fish",
            "food packaging", "post-harvest", "value chain", "food processing",
            "ultra-processed", "breastfeeding", "complementary feeding",
            "sécurité alimentaire", "sécurité sanitaire des aliments",
            "alimentation de rue", "manioc", "attiéké", "igname", "malnutrition",
            "poisson fumé", "transformation agroalimentaire",
        ],
    },
    "social": {
        "label": "Sciences sociales & Psychologie",
        "icon": "🧠",
        "keywords": [
            "psychology", "psychological", "mental health", "depression",
            "anxiety", "behaviour change", "behavior change",
            "urban mobility", "transport", "urbanization", "urbanisation",
            "informal settlement", "informal economy", "gender", "women's empowerment",
            "out-of-school", "migration", "corruption",
            "governance", "social norms", "poverty", "inequality",
            "livelihood", "livelihoods", "stigma",
            "santé mentale", "mobilité urbaine", "genre", "gouvernance",
            "pauvreté", "économie informelle", "jeunesse", "migrations",
        ],
    },
}


# ── Mensuel newsletter (mensuel.py) ──────────────────────────────────
# Le mensuel ne réinterroge aucune API : il relit les CSV hebdomadaires
# du mois écoulé (déjà dédoublonnés) et garde une sélection courte.
MONTHLY_PER_DOMAIN = 5           # par domaine et par section
MONTHLY_TOP_OUTSIDE = 5          # hors domaines, par section
MONTHLY_EXCLUDE_PREPRINTS = True # une newsletter ne relaie pas du non-évalué
MONTHLY_REQUIRE_DOI = True       # traçabilité : pas de DOI, pas de sélection
MONTHLY_REQUIRE_ABSTRACT = True  # impossible de juger (et d'écrire) sans résumé
