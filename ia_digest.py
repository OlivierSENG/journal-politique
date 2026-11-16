#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IA Digest — Résumé quotidien de l'actualité IA.

Reconstitue chaque jour un résumé : derniers modèles, annonces, modèles gratuits
et payants, agents IA. Envoi par email via la librairie resend.

Prérequis :
    pip install resend requests

Usage:
    python ia_digest.py --to mon@mail.fr --api-key re_...
    python ia_digest.py --to mon@mail.fr --api-key re_... --out ia_resume.txt
"""
import os
import sys
import json
import argparse
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime

# -----------------------------------------------------------------------
# Prendre l'actualité (requêtes HTTP directs)
# -----------------------------------------------------------------------
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------
# Configuration des en-têtes et timeouts
# ---------------------------------------------------------------
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr,en;q=0.9,en-US;q=0.8",
}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr,en-US;q=0.7,en;q=0.6",
}
TIMEOUT = 20
REQUEST_DELAY = 1.5  # respect de la politique de scraping

# ---------------------------------------------------------------
# Sources de données (IA uniquement)
# ---------------------------------------------------------------
# URLs directes à scraper (uniquement actualité IA)
DIRECT_SOURCES = [
    "https://blog.google/innovation-and-ai/technology/ai/",
    "https://www.anthropic.com/news",
    "https://ai.google/index/",
    "https://news.google.com/rss/search?q=AI+2026&hl=fr&gl=FR",
]


def fetch_ai_news(queries, limit=4):
    """Récupère l'actualité IA via des appels HTTP directs.

    Sources utilisées :
      - API Hacker News (hn.algolia.com) : histoires AI
      - RSS Reddit r/MachineLearning : actualités ML
      - Requêtes directes aux sources clés

    Retour :
        list[dict] = [
            {"date": str, "source": str, "title": str, "url": str, "snippet": str},
            ...
        ]
    """
    items = []
    seen = set()

    def add_item(source, title, url, snippet=""):
        if not title or not url:
            return
        # Normaliser le titre et retirer les retours à la ligne
        title = re.sub(r"\s+", " ", title).strip()
        snippet = re.sub(r"\s+", " ", snippet).strip()
        if len(title) < 10:
            return
        key = (title, url)
        if key in seen:
            return
        seen.add(key)
        items.append({
            "date": "",
            "source": source,
            "title": title[:200],
            "url": url,
            "snippet": snippet[:300],
        })

    # 1) Hacker News — histoires récentes AI/mach Learn
    # Requête multi-termes pour couvrir l'actualité AI
    try:
        # Première passe : top stories récents
        url = "https://hn.algolia.com/api/v1/items/newest?tags=story&hitsPerPage=20"
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        items_to_add = []
        if r.status_code == 200:
            data = r.json()
            ai_terms = ["ai", "llm", "large language", "machine learning", "deep learning",
                        "chatbot", "gpt", "claude", "gemini", "anthropic", "openai",
                        "mistral", "artificial intelligence", "neural network", "foundation model"]
            for hit in data.get("hits", [])[:30]:
                title = (hit.get("title") or "").lower()
                url = hit.get("url") or ""
                if any(k in title for k in ai_terms):
                    items_to_add.append((hit["title"], url, hit.get("story_text", "")))

        # Deuxième passe : recherche ciblée
        for q in ["AI 2026", "LLM 2026", "Claude 2026", "Gemini 2026"]:
            try:
                url = f"https://hn.algolia.com/api/v1/search?tags=story&query={requests.utils.quote(q)}&hitsPerPage=5"
                r2 = requests.get(url, headers=UA, timeout=TIMEOUT)
                if r2.status_code == 200:
                    data2 = r2.json()
                    for hit in data2.get("hits", [])[:limit]:
                        add_item("HackerNews (search)", hit["title"], hit["url"],
                                 hit.get("story_text", ""))
            except Exception as e:
                print(f"[WARN] HN search ({q}): {e}", file=sys.stderr)

        # Traitement de la première passe
        for hit in data.get("hits", [])[:30]:
            title = (hit.get("title") or "").lower()
            url = hit.get("url") or ""
            if any(k in title for k in ai_terms):
                add_item("HackerNews", hit["title"], url, hit.get("story_text", ""))
    except Exception as e:
        print(f"[WARN] HN newest: {e}", file=sys.stderr)
    time.sleep(REQUEST_DELAY)

    # 2) Reddit r/MachineLearning RSS — parser avec ElementTree (stdlib)
    try:
        url = "https://www.reddit.com/r/MachineLearning/.rss"
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            ns = {"r": "http://www.reddit.com/"}
            for item in root.findall("r:item", ns):
                title = item.find("r:title", ns)
                link = item.find("r:link", ns)
                if title and link:
                    add_item("Reddit ML", title.text.strip(), link.text.strip())
    except Exception as e:
        print(f"[WARN] Reddit RSS: {e}", file=sys.stderr)

    # 3) Requêtes directes sur les sites d'actualité IA
    for url in DIRECT_SOURCES:
        try:
            r = requests.get(url, headers=UA, timeout=TIMEOUT)
            if r.status_code == 200:
                soup = BeautifulSoup(r.content, "html.parser")
                # Extraire les titres (h2/h3)
                for tag in soup.find_all(["h2", "h3"])[:5]:
                    t = tag.get_text(strip=True)
                    if len(t) > 20:
                        a = tag.find_parent("a")
                        href = a.get("href", url) if a else url
                        add_item("Site actualité", t, href)
        except Exception as e:
            print(f"[WARN] Direct source ({url}): {e}", file=sys.stderr)

    # Dédup
    uniq = []
    seen2 = set()
    for it in items:
        key = (it.get("title", ""), it.get("url", ""))
        if key not in seen2:
            seen2.add(key)
            uniq.append(it)
    return uniq


def fetch_pages(urls):
    """Extrait le contenu vivant de quelques URL clés via requests + BeautifulSoup.

    Retour :
        list[dict] = [{"title": str, "url": str, "body": str}]
    """
    out = []
    seen = set()
    for u in urls:
        try:
            r = requests.get(u, headers=UA, timeout=TIMEOUT)
            if r.status_code != 200:
                continue
            soup = BeautifulSoup(r.content, "html.parser")

            # Titre
            title = ""
            for sel in ["h1", "title"]:
                el = soup.select_one(sel)
                if el and el.get_text(strip=True):
                    title = re.sub(r"\s+", " ", el.get_text(strip=True))[:150]
                    break
            if not title:
                title = u

            # Corps : extraire le contenu principal
            body = []
            for tag in soup.find_all(["p", "h2", "h3", "li", "div.article-content",
                                       "article", "main"]):
                txt = tag.get_text(strip=True)
                if len(txt) > 40:
                    body.append(txt)

            # Dedupliquer les paragraphes proches
            cleaned = []
            for b in body:
                b = re.sub(r"\s+", " ", b).strip()
                if len(b) < 80:
                    continue
                if cleaned and cleaned[-1] == b:
                    continue
                cleaned.append(b)

            body_text = " ".join(cleaned)[:6000]

            key = (title, u)
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "title": re.sub(r"\s+", " ", title)[:120],
                "url": u,
                "body": body_text,
            })
        except Exception as e:
            out.append({"title": u, "url": u, "body": f"[échec: {type(e).__name__}: {e}]"})

        # Petit délai entre les requêtes
        time.sleep(REQUEST_DELAY)

    return out


def build_digest(news, pages, queries=None):
    """Structure les données en catégories."""
    date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if queries is None:
        queries = []
    # Réduire les résultats à ce qui relève de l'actualité IA
    news = [n for n in news if n.get("snippet") or n.get("title")]

    # Normalisation de la liste d'articles (news + pages)
    items = []
    seen = set()
    for n in news:
        key = (n.get("title", ""), n.get("url", ""))
        if key not in seen:
            seen.add(key)
            items.append(n)
    for p in pages:
        key = (p.get("title", ""), p.get("url", ""))
        if key not in seen:
            seen.add(key)
            items.append(p)

    # ---- Catégorisation ----
    # 1) Announcements / lancements (modèles, révolutions, tech)
    model_kws = ["model", "modèle", "release", "launch", "lancement", "nouveau",
                 "nouvelle", "novel", "introduira", "présente", "introduit",
                 "open weights", "open-source", "api", "gpt", "claude", "gemini", "deepseek", "sora", "grok",
                 "sonnet", "opus", "haiku", "argon", "carbon", "hydrogen", "luna", "terra", "sol", "fable", "mythos", "kimi"]
    # 2) Modèles gratuits / open weights
    free_kws = ["free", "gratuit", "payant", "open weights", "open-source", "libre", "credit"]
    # 3) Agents
    agent_kws = ["agent", "agentic", "autonome", "automat", "automation", "workflow", "automation"]

    announcements = []
    free_models = []
    paid_models = []
    agents = []

    for it in items:
        t = (it.get("title") or "").lower()
        s = (it.get("snippet") or "").lower()
        text = f"{t} {s}"

        if any(k in text for k in agent_kws):
            agents.append(it)
        elif any(k in text for k in free_kws):
            free_models.append(it)
        elif any(k in text for k in model_kws):
            announcements.append(it)
        else:
            announcements.append(it)

    # 4) Pages d'information supplémentaires
    info_pages = []
    for p in pages[:4]:
        body = (p.get("body") or "").lower()
        t = (p.get("title") or "").lower()
        if (any(k in body for k in ["model", "modèle", "agent", "gratuit", "paie", "api", "pricing"])
                or "ai" in t or "intelligence" in t):
            info_pages.append(p)

    # Dédup des annonces
    ann_seen, ann_unique = set(), []
    for a in announcements:
        key = (a.get("title", ""), a.get("url", ""))
        if key not in ann_seen:
            ann_seen.add(key)
            ann_unique.append(a)
    announcements = ann_unique

    return {
        "date": date,
        "queries": queries,
        "total_items": len(news),
        "announcements": announcements[:16],
        "free_models": free_models[:8],
        "agents": agents[:8],
        "info_pages": info_pages[:5],
    }


def render_body(d):
    """Construit le corps texte de l'email."""
    parts = []
    parts.append("=" * 72)
    parts.append("  ACTUALITÉ IA — RÉSUMÉ QUOTIDIEN")
    parts.append(f"  Généré le : {d['date']}")
    parts.append(f"  Sources consultées : {d['total_items']}")
    parts.append("=" * 72)
    parts.append("")

    # 1. Dernières annonces / lancements
    parts.append("  1) DERNIERES ANNONCES / LANCEMENTS")
    parts.append("  " + "-" * 60)
    for a in d.get("announcements", []):
        title = a.get("title", "").strip()
        url = a.get("url", "")
        snippet = a.get("snippet", "").strip()
        if not title:
            title = a.get("source", "")
        parts.append(f"  • {title}")
        if snippet and len(snippet) < 300:
            parts.append(f"    ↳ {snippet[:180]}")
        if url:
            parts.append(f"    ↳ {url}")
    parts.append("")

    # 2. Modèles gratuits / open-weights
    parts.append("  2) MODÈLES GRATUITS / OPEN-WEIGHTS (à tester gratuitement)")
    parts.append("  " + "-" * 60)
    for fm in d.get("free_models", []):
        t = (fm.get("title") or "").strip()
        s = (fm.get("snippet") or "").strip()
        if t and not t.startswith("["):
            parts.append(f"  • {t} : {s[:170]}")
    parts.append("")

    # 3. Agents IA
    parts.append("  3) AGENTS IA")
    parts.append("  " + "-" * 60)
    for ag in d.get("agents", []):
        title = ag.get("title", "").strip()
        s = (ag.get("snippet") or "").strip()
        if title and not title.startswith("["):
            parts.append(f"  • {title} : {s[:150]}")
    parts.append("")

    # 4. Pages d'information
    parts.append("  4) ARTERES D'INFORMATIONS")
    parts.append("  " + "-" * 60)
    for p in d.get("info_pages", []):
        title = (p.get("title") or "").strip()
        body = (p.get("body") or "").strip()
        if title and len(body) > 80:
            parts.append(f"  • {title[:110]}")
            parts.append(f"    ↳ {body[:220]}")
    parts.append("")

    parts.append("=" * 72)
    parts.append("  Sources consultées : " + str(d.get("queries", [])))
    parts.append("=" * 72)

    return "\n".join(parts)


def send_email(digest, to, api_key, from_email="onboarding@resend.dev"):
    """Envoie l'email via la librairie resend."""
    try:
        import resend
    except ImportError:
        return {"ok": False, "error": "librairie 'resend' absente (pip install resend)"}

    resend.api_key = api_key
    body = render_body(digest)

    try:
        r = resend.Emails.send({
            "from": from_email,
            "to": to,
            "subject": f"[IA] Résumé de l'actualité IA du {digest['date']}",
            "text": body,
        })
        if r.get("id"):
            return {"ok": True, "id": r["id"]}
        return {"ok": False, "error": f"réponse sans id : {r}"}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def main():
    p = argparse.ArgumentParser(description="Résumé quotidien de l'actualité IA")
    p.add_argument("--to", required=True, help="destinataire email")
    p.add_argument("--api-key", required=True, help="clé API resend")
    p.add_argument("--emetteur", default="onboarding@resend.dev",
                   help="expéditeur email")
    p.add_argument("--out", help="écrire le résumé dans un fichier (au lieu d'envoyer)")
    args = p.parse_args()

    # Requêtes de recherche — couverture large de l'actualité IA
    queries = [
        # Announcements / lancements
        "AI model releases November 2026 announcements",
        "latest AI news OpenAI Anthropic Google November 2026",
        # Modèles gratuits / open weights
        "best free AI models open weights 2026 LLM",
        # Modèles payants / APIs
        "AI models paid API pricing 2026 GPT Claude Gemini pricing",
        # Agents IA
        "AI agents November 2026 free paid auto",
    ]

    news = fetch_ai_news(queries, limit=5)
    pages = fetch_pages([
        "https://www.anthropic.com/news",
        "https://blog.google/innovation-and-ai/technology/ai/",
    ])[:4]

    digest = build_digest(news, pages, queries)
    text = render_body(digest)
    print(text)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"\n[OK] écrit dans {args.out}")

    if args.to:
        ok = send_email(digest, args.to, args.api_key, args.emetteur)
        print("[EMAIL]", "OK" if ok.get("ok") else f"ÉCHEC: {ok.get('error')}")


if __name__ == "__main__":
    main()
