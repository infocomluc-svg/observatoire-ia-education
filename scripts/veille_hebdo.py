#!/usr/bin/env python3
"""
Veille hebdomadaire IA & éducation — Observatoire IA Éducation.

Appelle l'API Claude (modèle Haiku, recherche web limitée) et écrit :
  - veille/derniere.json      -> lu par la section 7 de index.html
  - veille/AAAA-MM-JJ.json    -> archive de la semaine

Budget : la clé est lue dans la variable d'environnement ANTHROPIC_API_KEY
(fournie par le secret GitHub du même nom). Aucune dépendance externe.
"""

import datetime as dt
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

# ---------------------------------------------------------------- 1. Réglages budget
MODELE = "claude-haiku-4-5"      # modèle le plus économique
MAX_TOKENS = 3000                # plafond de la réponse
MAX_RECHERCHES = 5               # plafond de recherches web par exécution (0,01 $ l'une)
PRIX_ENTREE = 1.00 / 1_000_000   # $ par token d'entrée (Haiku 4.5)
PRIX_SORTIE = 5.00 / 1_000_000   # $ par token de sortie (Haiku 4.5)
PRIX_RECHERCHE = 0.01            # $ par recherche web

# ---------------------------------------------------------------- 2. Consigne de veille
AUJOURDHUI = dt.date.today()
DEPUIS = AUJOURDHUI - dt.timedelta(days=7)

CONSIGNE = f"""Tu es l'agent de veille de l'Observatoire IA Éducation (France).
Nous sommes le {AUJOURDHUI.isoformat()}. Recherche les actualités publiées entre le
{DEPUIS.isoformat()} et le {AUJOURDHUI.isoformat()} sur :
1. l'IA en éducation et en pédagogie (ministère de l'Éducation nationale, éduscol, CREIA, IFé, UNESCO, OCDE, réseau Canopé) ;
2. la réglementation de l'IA touchant l'école (AI Act / Commission européenne, CNIL, RGPD).

Règles :
- Privilégie les sources institutionnelles primaires ; ignore les sites commerciaux.
- Ne retiens que des faits trouvés dans tes résultats de recherche, avec leur URL exacte.
- Maximum 8 actualités. S'il n'y a rien de notable, renvoie une liste vide.

Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour, de la forme :
{{"synthese": "2 à 3 phrases en français résumant la semaine",
  "items": [{{"titre": "...", "source": "nom de l'institution", "url": "https://...",
             "date": "AAAA-MM-JJ ou vide", "categorie": "education" | "reglementation" | "ia-generale",
             "resume": "1 à 2 phrases en français"}}]}}"""


def appeler_claude(cle: str) -> dict:
    corps = {
        "model": MODELE,
        "max_tokens": MAX_TOKENS,
        "tools": [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": MAX_RECHERCHES,
            "user_location": {"type": "approximate", "country": "FR", "timezone": "Europe/Paris"},
        }],
        "messages": [{"role": "user", "content": CONSIGNE}],
    }
    requete = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(corps).encode("utf-8"),
        headers={
            "x-api-key": cle,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(requete, timeout=300) as rep:
            return json.load(rep)
    except urllib.error.HTTPError as err:
        # On n'affiche jamais la clé, seulement le message d'erreur de l'API.
        sys.exit(f"Erreur API {err.code} : {err.read().decode('utf-8', 'replace')[:500]}")


def extraire_json(reponse: dict) -> dict:
    texte = "".join(b.get("text", "") for b in reponse.get("content", []) if b.get("type") == "text")
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut == -1 or fin == -1:
        return {"synthese": "Aucune synthèse exploitable cette semaine.", "items": []}
    try:
        return json.loads(texte[debut:fin + 1])
    except json.JSONDecodeError:
        return {"synthese": "Réponse de l'agent illisible cette semaine.", "items": []}


def urls_trouvees(reponse: dict) -> set:
    """URL réellement renvoyées par la recherche web (garde-fou anti-invention)."""
    urls = set()
    for bloc in reponse.get("content", []):
        if bloc.get("type") == "web_search_tool_result" and isinstance(bloc.get("content"), list):
            urls.update(r.get("url") for r in bloc["content"] if r.get("url"))
    return urls


def main() -> None:
    cle = os.environ.get("ANTHROPIC_API_KEY")
    if not cle:
        sys.exit("Secret ANTHROPIC_API_KEY absent.")

    reponse = appeler_claude(cle)
    donnees = extraire_json(reponse)

    # Ne garder que les actualités dont l'URL provient vraiment des résultats de recherche.
    sources = urls_trouvees(reponse)
    items = [i for i in donnees.get("items", []) if isinstance(i, dict) and i.get("url") in sources]

    usage = reponse.get("usage", {})
    recherches = usage.get("server_tool_use", {}).get("web_search_requests", 0)
    cout = (usage.get("input_tokens", 0) * PRIX_ENTREE
            + usage.get("output_tokens", 0) * PRIX_SORTIE
            + recherches * PRIX_RECHERCHE)

    resultat = {
        "genere_le": AUJOURDHUI.isoformat(),
        "periode": {"du": DEPUIS.isoformat(), "au": AUJOURDHUI.isoformat()},
        "synthese": donnees.get("synthese", ""),
        "items": items[:8],
        "cout_estime_usd": round(cout, 4),
    }

    dossier = pathlib.Path(__file__).resolve().parent.parent / "veille"
    dossier.mkdir(exist_ok=True)
    for nom in ("derniere.json", f"{AUJOURDHUI.isoformat()}.json"):
        (dossier / nom).write_text(json.dumps(resultat, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"{len(resultat['items'])} actualités retenues · {recherches} recherches · "
          f"coût estimé {cout:.3f} $")


if __name__ == "__main__":
    main()
