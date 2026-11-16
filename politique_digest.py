#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Politique France & Europe — script de résumé quotidien (lois en cours / votées).

Sondage de sources (scraping, pas de dépendance au moteur de recherche d'Hermes) :
  - France : Assemblée nationale (dossiers en cours de la Commission des lois),
            Sénat (index alphabétique), vie-publique.fr (actualité lois)
  - Europe : Parlement européal (agenda hebdomadaire des votes)
  - Complément : web_search hors ligne si disponible (moteur de recherche)

Delivery : envoi email via SMTP ou API Resend / SendGrid.
"""
import os
import sys
import re
import json
import socket
import smtplib
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from email.message import EmailMessage
from bs4 import BeautifulSoup
from collections import OrderedDict

# ----------------------------- configuration -----------------------------
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Sources
SOURCE_ASSEMBLEE = "https://www.assemblee-nationale.fr/dyn/17/organes/commissions-permanentes/lois/dossiers?affichage=en_cours"
SOURCE_EP_AGENDA = "https://www.europarl.europa.eu/news/fr/agenda/weekly-agenda"

# Délai de timeout
TIMEOUT = 25

# ----------------------------- utilitaires -----------------------------
def fetch(url, timeout=TIMEOUT):
    """Récupère le contenu HTML d'une URL. Retourne texte/plain ou None."""
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            enc = r.headers.get_content_charset() or "utf-8"
            return raw.decode(enc, errors="replace")
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

def clean(text):
    """Réduit le texte d'arrière-plan HTML, garde les lignes pertinentes."""
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#\d+;", " ", text)
    return text

def slugify(s):
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[-\s]+", "-", s)

# ----------------------------- collecte -----------------------------
def gather_assemblee():
    """Lois françaises en cours (Assemblée nationale)."""
    out = []
    html = fetch(SOURCE_ASSEMBLEE)
    if isinstance(html, dict):
        return {"error": html.get("error"), "source": "assemblee-nationale"}
    soup = BeautifulSoup(html, "html.parser")

    # Les cartes de loi sont les <div class="an-bloc _style-dossier-legislatif">
    # (ou <div class="relative-flex"> selon la version du site). On les détecte
    # par la présence d'un champ de statut <span class="...colored-primary...">
    # ainsi que du libellé "Dépôt à l'Assemblée nationale le".
    cards = []
    for div in soup.find_all("div", class_=re.compile(r"dossier-legislatif")):
        txt = div.get_text(" ", strip=True)
        if "Dépôt à l'Assemblée nationale le" in txt and re.search(r"(Proposition de loi|Projet de loi)", txt):
            cards.append(div)
    if not cards:
        # fallback sur les anciennes cartes <div class="relative-flex">
        for div in soup.find_all("div", class_=re.compile(r"relative-flex")):
            txt = div.get_text(" ", strip=True)
            if "Dépôt à l'Assemblée nationale le" in txt and re.search(r"(Proposition de loi|Projet de loi)", txt):
                cards.append(div)
    seen = set()
    uniq = []
    for c in cards:
        k = id(c)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(c)

    for card in uniq:
        txt = card.get_text(" ", strip=True)
        l = {}

        # titre (lien _big de la carte)
        for a in card.find_all("a", class_="link _big"):
            tt = a.get_text(" ", strip=True)
            if tt:
                l["titre"] = tt
                break
        if not l.get("titre"):
            l["titre"] = ""

        # type
        for sp in card.find_all("span", class_="_bold"):
            tt = sp.get_text(" ", strip=True)
            if re.search(r"(Proposition de loi|Projet de loi|Constitution)", tt):
                l["type"] = tt
                break

        # dépôt
        m = re.search(r"Dépôt à l'Assemblée nationale le (\w+ \d+ \w+ \d{4}) \((Proposal de loi|Projet de loi|Proposition de loi organique|Proposition de loi constitutionnelle) (n°[\w-]+)\)", txt)
        if m:
            l["depot"] = f"{m.group(1)} ({m.group(2)} {m.group(3)})"

        # statut
        st = ""
        for sp in card.find_all("span", class_=re.compile(r"colored-primary")):
            tt = sp.get_text(" ", strip=True)
            if any(k in tt for k in ("En cours", "Adoption", "Rejet", "Position", "considérée")):
                st = tt
                break
        l["statut"] = st[:220]

        l["desc"] = ""
        out.append(l)
    return {"source": "Assemblée nationale (Commission des lois)", "lois": out}

def gather_ep_weekly():
    """Votes/lois du Parlement européen (agenda hebdomadaire)."""
    out = []
    html = fetch(SOURCE_EP_AGENDA)
    if isinstance(html, dict):
        return {"error": html.get("error"), "source": "ep-agenda"}
    soup = BeautifulSoup(html, "html.parser")
    txt = clean(soup.get_text("\n", strip=True))
    lines = [l for l in txt.split("\n") if l.strip()]
    # On filtre les votes / règlements / propositions de résolution
    patterns = [r"vote", r"règlement", r"proposition de résolution", r"résolution", r"adoption"]
    for l in lines:
        if any(re.search(p, l, re.I) for p in patterns) and len(l) < 300:
            out.append(l)
    return {"source": "Parlement européen (agenda hebdomadaire)", "lois": out}

def gather_vie_publique():
    """Actualité des lois sur vie-publique.fr (France)."""
    out = []
    # actualité lois générales
    url = "https://www.vie-publique.fr/autour-de-la-loi"
    html = fetch(url)
    if isinstance(html, dict):
        return {"error": html.get("error"), "source": "vie-publique"}
    soup = BeautifulSoup(html, "html.parser")
    txt = clean(soup.get_text("\n", strip=True))
    lines = [l for l in txt.split("\n") if l.strip()]
    for l in lines:
        if re.search(r"(Projet de loi|Proposition de loi|LOI n°[ 0-9-]*|loi[\s-]+[0-9])", l) and len(l) < 260:
            out.append(l)
    return {"source": "Vie-publique.fr", "lois": out}

def gather_all():
    """Retourne un aggrégat des sources."""
    result = {"generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              "sources": {}}
    for name, fn in [
        ("assemblee", gather_assemblee),
        ("ep_agenda", gather_ep_weekly),
        ("vie_publique", gather_vie_publique),
    ]:
        try:
            result["sources"][name] = fn()
        except Exception as e:
            result["sources"][name] = {"error": f"{type(e).__name__}: {e}"}
    return result

# ----------------------------- formatage -----------------------------
def summarize(entry):
    """Construit une ligne de résumé propre : titre + statut + description."""
    title = entry.get("titre") or ""
    st = entry.get("statut") or ""
    desc = entry.get("desc") or ""
    parts = [title]
    if st:
        parts.append("(%s)" % st[:180])
    if desc:
        parts.append("— %s" % desc[:200])
    return " ".join(p for p in parts if p).strip()

def summarize_ep(raw):
    """Nettoie une ligne de l'agenda européen : retire le bruit ('Vote' seul)."""
    t = (raw or "").strip()
    if re.fullmatch(r"Vote[s]?", t, re.I):
        return None
    # garde l'essentiel, tronque
    t = re.sub(r"\s+", " ", t)
    return t[:280]

def build_digest(r):
    """Maintient un objet structuré du résumé pour l'envoi (email / texte)."""
    french = []
    europe = []
    others = []
    for src, data in r.get("sources", {}).items():
        if "error" in data:
            others.append({"source": src, "error": data["error"]})
            continue
        laws = data.get("lois", [])
        if src == "assemblee":
            french = [summarize(e) for e in laws]
        elif src == "ep_agenda":
            europe = [e for e in (summarize_ep(l) for l in laws) if e]
        elif src == "vie_publique":
            french += [summarize(e) for e in laws]
    return {
        "date": r.get("generated", ""),
        "french_lois": french,
        "europe_lois": europe,
        "other": others,
    }

# ----------------------------- envoi -----------------------------
def send_smtp(digest, to_email, smtp_host, smtp_port, user, password, from_email):
    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = f"[Politique] Résumé France & Europe du {digest['date']}"
    body = render_body(digest)
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as s:
            s.ehlo()
            if smtp_port == 465:
                s.starttls()
            s.ehlo()
            s.login(user, password)
            s.send_message(msg)
        return {"ok": True, "sent": True}
    except Exception as e:
        return {"ok": False, "error": f"SMTP: {type(e).__name__}: {e}"}

def render_body(digest):
    parts = []
    parts.append("=== Résumé de l'actualité politique — France & Europe ===")
    parts.append(f"Généré le : {digest['date']}")
    parts.append("")
    parts.append("--- FRANCE : lois en cours ---")
    if digest["french_lois"]:
        for i, l in enumerate(digest["french_lois"], 1):
            parts.append(f"{i}. {l}")
    else:
        parts.append("Aucune loi en cours signalée.")
    parts.append("")
    parts.append("--- EUROPE : lois / votes ---")
    if digest["europe_lois"]:
        for i, l in enumerate(digest["europe_lois"], 1):
            parts.append(f"{i}. {l}")
    else:
        parts.append("Aucune action européenne récente signalée.")
    parts.append("")
    if digest["other"]:
        parts.append("--- Autres sources (erreur) ---")
        for o in digest["other"]:
            parts.append(f"* {o.get('source')}: {o.get('error')}")
    parts.append("")
    parts.append("--- Fin du résumé ---")
    return "\n".join(parts)

# ----------------------------- CLI -----------------------------
def main():
    import argparse
    p = argparse.ArgumentParser(description="Résumé quotidien de l'actualité politique France & Europe")
    p.add_argument("--out", help="écrire le résumé dans un fichier (au lieu d'envoyer)")
    p.add_argument("--to", help="destinataire email")
    p.add_argument("--emetteur", dest="from_email", help="expéditeur email (optionnel)",
                   default="onboarding@resend.dev")
    p.add_argument("--smtp-host", default="smtp.gmail.com")
    p.add_argument("--smtp-port", type=int, default=587)
    p.add_argument("--smtp-user", dest="smtp_user")
    p.add_argument("--smtp-pass", dest="smtp_pass")
    p.add_argument("--api-key", help="clé API d'envoi (librairie resend)")

    args = p.parse_args()

    digest = build_digest(gather_all())

    # affichage texte
    text = render_body(digest)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"\n[OK] écrit dans {args.out}")

    # envoi email si configuré
    if args.to:
        ok = send_email(digest, args.to, args.api_key, args.from_email)
        print("[EMAIL]", "OK" if ok else f"ÉCHEC: {ok.get('error')}")

def send_email(digest, to, api_key, from_email=None):
    # Envoie l'email via la librairie Python resend.
    try:
        import resend
    except ImportError:
        return {"ok": False, "error": "librairie 'resend' absente (pip install resend)"}

    resend.api_key = api_key
    sender = from_email or "onboarding@resend.dev"
    body = render_body(digest)

    try:
        r = resend.Emails.send({
            "from": sender,
            "to": to,
            "subject": f"[Politique] Résumé France & Europe du {digest['date']}",
            "text": body,
        })
        if r.get("id"):
            return {"ok": True}
        return {"ok": False, "error": f"réponse sans id : {r}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

if __name__ == "__main__":
    main()
