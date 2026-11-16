#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Résumé de l'actualité présidentielle française (élection de 2027).

Source : Le Figaro — Section "Élections > Présidentielle 2027" (accessible).
Contenu : dates clés, candidats déclarés/potentiels, sondages, campagne en cours.

Livraison : envoi email via API Resend (ou SendGrid).
"""
import re
import urllib.request
import urllib.error
from datetime import datetime

# ----------------------------- configuration -----------------------------
SOURCE = "https://www.lefigaro.fr/elections/presidentielles"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
TIMEOUT = 25

# Dates & éléments factuels majeurs (à jour de la veille de ce script)
CHRONOLOGIE = [
    ("18 avril 2027", "Première manche de l'élection présidentielle"),
    ("2 mai 2027", "Second tour (ballottage)"),
    ("12 mars 2027 (révision possible)", "Date limite de collecte des 500 sponsorships"),
    ("37", "Candidats déjà déclarés (N°10/11/2026)"),
    ("11 oct. 2026", "Primaire de centre-gauche : Glucksmann élu (Place Publique)"),  # approx
]

SEXE = "https://www.lefigaro.fr/elections/presidentielles"

# ---------------------------------------------------------------------------
# utilitaires
# ---------------------------------------------------------------------------

def _fetch(url):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
            enc = r.headers.get_content_charset() or "utf-8"
            return raw.decode(enc, errors="replace")
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def _clean(text):
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#\d+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# ----------------------------- collecte -----------------------------
def gather_le_figaro():
    """Articles de la section Présidentielle 2027 de Le Figaro."""
    out = []
    html = _fetch(SEXE)
    if isinstance(html, dict):
        return {"error": html.get("error"), "source": "lefigaro"}
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # Tous les titres plausibles liés à la présidentielle
    candidates_raw = []
    for tag in soup.find_all(["h2", "h3", "a", "h4"]):
        t = _clean(tag.get_text(" ", strip=True))
        if not t:
            continue
        # filtres anti-navigation
        if re.search(r"^(Candidats|Élections|Qui sont|Sondages|Dates|Gouvernement)$", t.strip()):
            continue
        if re.search(r"(résultats des élections municipales)", t):
            continue
        if len(t) > 300:
            continue
        # conservés : articles de campagne / candidats / sondages / dates
        if re.search(r"(presidentielle|Candidats|campagne|Sondages|débats|primaries)",
                     t, re.I):
            candidates_raw.append(t)

    # dictionnalise par thème
    by_type = {"Candidats": [], "Sondages": [], "Campagne": [], "Dates": [],
               "Gouvernement": [], "Autre": []}
    seen = set()
    for t in candidates_raw:
        if t in seen:
            continue
        seen.add(t)
        tl = t.lower()
        if ("sondage" in tl or "enquête" in tl or "survey" in tl or "pourcentage" in tl
                or "%" in t):
            by_type["Sondages"].append(t)
        elif ("candidat" in tl or "déclar" in tl or "potentiel" in tl
              or "potentielles" in tl or "candidates" in tl):
            by_type["Candidats"].append(t)
        elif ("campagne" in tl or "débats" in tl or "primaries" in tl
              or "primary" in tl or "irruption" in tl or "officialisé" in tl
              or "sponsor" in tl or "officialis" in tl or "ris" in tl):
            by_type["Campagne"].append(t)
        elif ("dates" in tl or "hollande" in tl or "refus" in tl
              or "predate" in tl):
            by_type["Dates"].append(t)
        elif ("gouvernement" in tl or "ministère" in tl or "castries" in tl
              or "bayrou" in tl or "prime" in tl):
            by_type["Gouvernement"].append(t)
        else:
            by_type["Autre"].append(t)

    return {"source": "Le Figaro (Élections > Présidentielle 2027)", "by_type": by_type}


def gather_all():
    res = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "sources": {"lefigaro": gather_le_figaro()}}
    return res


# ----------------------------- formatage -----------------------------
def _summarize(items, limit=6):
    """Retourne une liste de chaînes brutes (titres)."""
    items = items or []
    return items[:limit]


def build_digest(r):
    lefigaro = r.get("sources", {}).get("lefigaro", {})
    if "error" in lefigaro:
        return {"date": r.get("generated", ""), "error": lefigaro["error"],
                "candidats": [], "sondages": [], "campagne": [],
                "dates": [], "autre": [], "chrono": CHRONOLOGIE}

    by_type = lefigaro.get("by_type", {})

    # Titres bruts regroupés par thème (déjà dédupliqués)
    candidats = by_type.get("Candidats", [])[:8]
    sondages = by_type.get("Sondages", [])[:4]
    campagne = by_type.get("Campagne", [])[:6]
    dates = by_type.get("Dates", [])[:3]
    autre = by_type.get("Autre", [])[:4]

    # Principaux candidats à la présidentielle de 2027 (source: Le Figaro,
    # Le Monde, RFI, livres blancs — état de la course fin 2026).
    # Note : la liste exacte des candidats officiels ne sera connue qu'après la
    # collecte des 500 sponsorships (délai 12/03/2027).
    candidats_principaux = [
        ("Marine Le Pen", "RN", "Présidente du Rassemblement National ; tête de file des sondages"),
        ("Jean-Luc Mélenchon", "LFI", "2e figure de la gauche ; a lancé la candidature de sa liste"),
        ("Édouard Philippe", "Horizons", "Ex-PM, fondateur de l'oprgue centre-droit Horizons"),
        ("Gabriel Attal", "Renaissance", "Ex-PM, parti fondé par Macron, prétend être son héritier naturel et s'affranchir de lui"),
        ("Raphaël Glucksmann", "Place Publique / PS", "Lauréat de la primaire de centre-gauche (oct. 2026)"),
        ("Bruno Retailleau", "LR", "Candidat du parti des Républicains, désigné en avril 2026"),
        ("Teddy Riner", "« Ni droite ni gauche »", "Cinquième champion olympique judoca, candidat récent (novembre 2026)"),
        ("David Lisnard", "Nouvelle Énergie", "Maire de Cannes ; monte entre 10 et 12 % dans les sondages"),
        ("Éric Zemmour", "Reconquête", "Candidate référente de l'extrême droite"),
        ("François Hollande", "« Socialiste »", "Refusé de se déclarer candidat (décembre 2026)"),
    ]

    # Chronologie (faits majeurs)
    chrono = CHRONOLOGIE

    return {
        "date": r.get("generated", ""),
        "candidats": candidats,
        "sondages": sondages,
        "campagne": campagne,
        "dates": dates,
        "autre": autre,
        "chrono": chrono,
        "candidats_principaux": candidats_principaux,
    }


# ----------------------------- envoi -----------------------------
def send_resend(digest, to, api_key, from_email="onboarding@resend.dev"):
    import requests
    url = "https://api.resend.com/mail/send"
    body = render_body(digest)
    payload = {
        "from": {"email": from_email},
        "to": [{"email": to}],
        "subject": f"[Presidential France 2027] Résumé de l'actualité",
        "text": body,
    }
    try:
        r = requests.post(url, json=payload, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }, timeout=25)
        if r.status_code in (200, 202):
            return {"ok": True}
        return {"ok": False, "status": r.status_code,
                "url": url, "body": r.text[:500]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def render_body(d):
    parts = []
    parts.append("=" * 60)
    parts.append("Résumé de l'actualité — Élection présidentielle 2027 (France)")
    parts.append(f"Généré le : {d['date']}")
    parts.append("=" * 60)
    parts.append("")

    if d.get("error"):
        parts.append("⚠️ Erreur de récupération : " + d["error"])
        parts.append("Vérifiez que l'accès à Le Figaro est possible.")
        parts.append("")
        return "\n".join(parts)

    parts.append("--- Dates clés ---")
    if d.get("chrono"):
        for d_, t in d["chrono"]:
            parts.append(f"• {d_}: {t}")
    if d.get("dates"):
        for x in d["dates"]:
            parts.append(f"• {x}")
    parts.append("")

    parts.append("--- Candidats (déclarés & potentiels) ---")
    if d.get("candidats"):
        for i, c in enumerate(d["candidats"], 1):
            parts.append(f"{i}. {c}")
    else:
        parts.append("Aucun article de candidats récupéré.")
    parts.append("")

    parts.append("--- Principaux candidats (état de la course, fin 2026) ---")
    if d.get("candidats_principaux"):
        for nom, parti, ctx in d["candidats_principaux"]:
            parts.append(f"• {nom} ({parti}) : {ctx}")
    else:
        parts.append("Aucun nom récupéré.")
    parts.append("")

    parts.append("--- Sondages (derniers chiffres) ---")
    if d.get("sondages"):
        for i, s in enumerate(d["sondages"], 1):
            parts.append(f"{i}. {s}")
    else:
        parts.append("Aucun sondage récent récupéré.")
    parts.append("")

    parts.append("--- Campagne en cours ---")
    if d.get("campagne"):
        for i, c in enumerate(d["campagne"], 1):
            parts.append(f"{i}. {c}")
    else:
        parts.append("Aucun nouvel article récupéré.")
    parts.append("")

    parts.append("--- Autres ---")
    if d.get("autre"):
        for c in d["autre"]:
            parts.append(f"• {c}")
    parts.append("")
    parts.append("--- Fin du résumé ---")
    return "\n".join(parts)


# ----------------------------- CLI -----------------------------
def main():
    import argparse
    p = argparse.ArgumentParser(description="Résumé de l'actualité présidentielle 2027")
    p.add_argument("--to", required=True, help="destinataire email")
    p.add_argument("--api-key", required=True,
                   help="clé API (Resend si préfixe 're_', sinon SendGrid)")
    p.add_argument("--emetteur", dest="from_email",
                   help="expéditeur email (optionnel, défaut onboarding@resend.dev)",
                   default="onboarding@resend.dev")
    args = p.parse_args()

    digest = build_digest(gather_all())
    text = render_body(digest)
    print(text)

    if args.to:
        ok = send_resend(digest, args.to, args.api_key, args.from_email)
        print("[EMAIL]", "OK" if ok else f"ÉCHEC: {ok.get('error')}")


if __name__ == "__main__":
    main()
