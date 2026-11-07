#!/usr/bin/env python3
"""
Collecte hebdomadaire des sources prioritaires de l'Info lettre IANE.

Lit les flux publics (RSS) et pages publiques des sources prioritaires,
ne garde que les publications qui portent sur l'IA ou le numérique,
et écrit infolettre-iane/flux.json, que la préparation mensuelle lit.

Aucune dépendance, aucune clé API. Usage : python3 scripts/collecte_flux.py
"""
import datetime as dt
import html
import json
import pathlib
import re
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

RACINE = pathlib.Path(__file__).resolve().parent.parent
SORTIE = RACINE / "infolettre-iane" / "flux.json"
UA = "Mozilla/5.0 (compatible; InfolettreIANE/1.0; veille pedagogique academie de Lille)"
JOURS = 120  # profondeur conservée

# Sources : (identifiant, nom affiché, priorité, type, url)
SOURCES = [
    ("crcom", "CRCOM (réseau national communication, management, économie-droit)", 1, "rss",
     "https://crcom.ac-versailles.fr/spip.php?page=backend"),
    ("creg", "CREG – académie de Versailles", 1, "rss",
     "https://creg.ac-versailles.fr/spip.php?page=backend"),
    ("edunum", "Éduscol – Cahiers ÉduNum", 1, "edunum",
     "https://eduscol.education.gouv.fr/6699/les-cahiers-edunum-sur-le-numerique-educatif"),
    ("lille-ecogest", "Académie de Lille – pédagogie économie-gestion", 2, "rss",
     "https://pedagogie.ac-lille.fr/ecogestion/feed/"),
    ("drane-lille", "DRANE de Lille", 2, "rss",
     "https://dane.site.ac-lille.fr/feed/"),
]

# Filtre IA / numérique (sur titre + résumé), en minuscules
MOTS = [
    r"\bia\b", r"intelligence artificielle", r"\bia générative", r"numériqu", r"digital",
    r"donnée", r"\bdata\b", r"rgpd", r"cyber", r"algorithm", r"plateforme", r"chatbot",
    r"agent conversationnel", r"prompt", r"compar:?ia", r"mistral", r"chatgpt", r"\bllm\b",
    r"automatis", r"robot", r"blockchain", r"chaîne de blocs", r"cloud", r"logiciel",
    r"progiciel", r"\berp\b", r"tableur", r"base de données", r"\bsql\b", r"réseaux? sociaux?",
    r"e-commerce", r"commerce en ligne", r"identité numérique", r"traces? numériques?",
    r"cookies?", r"éléa", r"magistère", r"édubase", r"traam", r"pix", r"\bent\b", r"capytale",
    r"système d.information", r"cybersécurité", r"dématérialis",
]
RE_MOTS = re.compile("|".join(MOTS), re.I)


def lire(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def texte(s, n=400):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(re.sub(r"\s+", " ", s)).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


def date_iso(s):
    if not s:
        return ""
    s = s.strip()
    try:
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:
        pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else ""


def flux_rss(src_id, nom, prio, url):
    racine = ET.fromstring(lire(url).encode("utf-8"))
    ns = {"dc": "http://purl.org/dc/elements/1.1/", "atom": "http://www.w3.org/2005/Atom"}
    sortie = []
    items = racine.findall(".//item") or racine.findall(".//atom:entry", ns)
    for it in items:
        titre = (it.findtext("title") or it.findtext("atom:title", default="", namespaces=ns) or "").strip()
        lien = (it.findtext("link") or "").strip()
        if not lien:
            l = it.find("atom:link", ns)
            lien = l.get("href") if l is not None else ""
        date = date_iso(it.findtext("pubDate") or it.findtext("dc:date", default="", namespaces=ns)
                        or it.findtext("atom:updated", default="", namespaces=ns))
        resume = texte(it.findtext("description") or it.findtext("atom:summary", default="", namespaces=ns))
        rubrique = ""
        m = re.search(r'rel="directory">([^<]+)<', it.findtext("description") or "")
        if m:
            rubrique = html.unescape(m.group(1))
        sortie.append({"source": src_id, "nom_source": nom, "priorite": prio, "titre": html.unescape(titre),
                       "url": lien, "date": date, "resume": resume, "rubrique": rubrique})
    return sortie


class _Liens(HTMLParser):
    def __init__(self):
        super().__init__()
        self.liens, self._href, self._txt = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._txt = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._txt.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.liens.append((self._href, " ".join("".join(self._txt).split())))
            self._href = None


MOIS = {m: i for i, m in enumerate(["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
                                    "août", "septembre", "octobre", "novembre", "décembre"], 1)}


def page_edunum(src_id, nom, prio, url):
    """Page éduscol des Cahiers ÉduNum, lue via le service public de lecture r.jina.ai
    (éduscol refuse les robots directs). Titre attendu : « Cahier ÉduNum … n° NN - mois AAAA »."""
    md = lire("https://r.jina.ai/" + url)
    sortie, vus = [], set()
    for m in re.finditer(r"\[((?:Cahier|Lettre)s?[^\]]*?[ÉE]du\s*Num[^\]]*?n\s*°\s*\d+[^\]]*?)\]\((https?://[^)\s]+)\)", md, re.I):
        titre, lien = " ".join(m.group(1).split()), m.group(2)
        d = re.search(r"-\s*([a-zéû]+)\s+(\d{4})", titre, re.I)
        if not d or titre in vus:
            continue
        vus.add(titre)
        mois = MOIS.get(d.group(1).lower(), 1)
        suite = md[m.end(): m.end() + 1200]
        suite = re.sub(r"^.*?Ajouter aux favoris[^\n]*\n", "", suite, flags=re.S)
        resume = texte(re.split(r"Consulter les lettres|S'abonner", suite)[0].replace("*", ""), 400)
        sortie.append({"source": src_id, "nom_source": nom, "priorite": prio, "titre": titre,
                       "url": lien, "date": f"{d.group(2)}-{mois:02d}-01", "resume": resume,
                       "rubrique": "Cahiers ÉduNum", "page": url})
    return sortie


def main():
    limite = (dt.date.today() - dt.timedelta(days=JOURS)).isoformat()
    tous, etat = [], []
    for src_id, nom, prio, typ, url in SOURCES:
        try:
            lot = flux_rss(src_id, nom, prio, url) if typ == "rss" else page_edunum(src_id, nom, prio, url)
            garde = [x for x in lot if (not x["date"] or x["date"] >= limite)
                     and RE_MOTS.search(x["titre"] + " " + x["resume"] + " " + x["rubrique"])]
            tous += garde
            etat.append({"source": src_id, "nom": nom, "url": url, "ok": True, "lus": len(lot), "retenus": len(garde)})
        except Exception as e:  # une source en panne ne bloque pas les autres
            etat.append({"source": src_id, "nom": nom, "url": url, "ok": False, "erreur": str(e)[:200]})
    # dédoublonnage par URL, tri : priorité puis date décroissante
    vus, uniques = set(), []
    for x in sorted(tous, key=lambda x: (x["priorite"], "" if not x["date"] else "~" + x["date"]), reverse=False):
        if x["url"] in vus:
            continue
        vus.add(x["url"])
        uniques.append(x)
    uniques.sort(key=lambda x: (x["priorite"], -int((x["date"] or "0000-00-00").replace("-", ""))))
    ancien = {}
    if SORTIE.exists():
        try:
            ancien = json.loads(SORTIE.read_text(encoding="utf-8"))
        except Exception:
            ancien = {}
    deja = {x["url"] for x in ancien.get("items", [])}
    for x in uniques:
        x["nouveau_depuis_derniere_collecte"] = x["url"] not in deja
    donnees = {
        "genere_le": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "perimetre": "IA et numérique uniquement (filtre par mots-clés, à valider éditorialement)",
        "sources": etat,
        "items": uniques,
    }
    SORTIE.write_text(json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for s in etat:
        if not s["ok"]:
            print(f"ERREUR {s['source']} ({s['url']}) : {s['erreur']}")
    print(f"{len(uniques)} publications retenues ; " +
          ", ".join(f"{s['source']}={'ok ' + str(s.get('retenus')) if s['ok'] else 'ERREUR'}" for s in etat))


if __name__ == "__main__":
    main()
