import argparse
import json
import math
import mimetypes
import os
import re
import threading
import time
import webbrowser
import xml.etree.ElementTree as element_tree
import zipfile
from concurrent.futures import ThreadPoolExecutor
from html import escape, unescape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request
from urllib.parse import parse_qs, quote, urlencode, urlparse

from search_engine import DocumentParser, SearchEngine, SearchResult


ROOT = Path(__file__).resolve().parent
CODE_VERSION = "2026-06-27-social-search-2-youtube"
TEMPLATE_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
IMAGE_DIR = ROOT / "imageres"
DB_PATH = ROOT / "data" / "index.db"
DB_ARCHIVE_PATH = ROOT / "data" / "index.db.zip"
DB_ARCHIVE_PARTS = tuple(sorted(DB_ARCHIVE_PATH.parent.glob("index.db.zip.part*")))
IS_RENDER = os.environ.get("RENDER", "").lower() == "true"
DEFAULT_HOST = os.environ.get("HOST") or ("0.0.0.0" if IS_RENDER or os.environ.get("PORT") else "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("PORT") or os.environ.get("NESAT_PORT") or "8020")

if not DB_ARCHIVE_PATH.exists() and DB_ARCHIVE_PARTS:
    with DB_ARCHIVE_PATH.open("wb") as archive:
        for part_path in DB_ARCHIVE_PARTS:
            with part_path.open("rb") as part:
                while chunk := part.read(1024 * 1024):
                    archive.write(chunk)

if not DB_PATH.exists() and DB_ARCHIVE_PATH.exists():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(DB_ARCHIVE_PATH) as archive:
        archive.extract("index.db", DB_PATH.parent)

ENGINE = SearchEngine(DB_PATH)
DEFAULT_SOURCE_PROFILES = [
    {
        "name": "Wikipedia",
        "starter_urls": [
            "https://en.wikipedia.org/wiki/Internet",
            "https://en.wikipedia.org/wiki/World_Wide_Web",
            "https://en.wikipedia.org/wiki/Search_engine",
            "https://en.wikipedia.org/wiki/Social_media",
            "https://en.wikipedia.org/wiki/Design",
            "https://en.wikipedia.org/wiki/Video_game",
            "https://en.wikipedia.org/wiki/History",
            "https://en.wikipedia.org/wiki/Art",
            "https://en.wikipedia.org/wiki/Science",
            "https://en.wikipedia.org/wiki/Literature",
        ],
        "seeds": [
            "https://en.wikipedia.org/wiki/Main_Page",
            "https://en.wikipedia.org/wiki/Portal:Current_events",
            "https://en.wikipedia.org/wiki/Portal:Technology",
            "https://en.wikipedia.org/wiki/Portal:Arts",
            "https://en.wikipedia.org/wiki/Portal:History",
            "https://en.wikipedia.org/wiki/Portal:Science",
            "https://en.wikipedia.org/wiki/Portal:Society",
            "https://en.wikipedia.org/wiki/Portal:Geography",
            "https://en.wikipedia.org/wiki/Portal:Culture",
        ],
        "pages_per_seed": 14,
        "depth": 2,
    },
    {
        "name": "Reddit",
        "starter_urls": [
            "https://old.reddit.com/r/popular/",
            "https://old.reddit.com/r/technology/",
            "https://old.reddit.com/r/gaming/",
            "https://old.reddit.com/r/science/",
            "https://www.reddit.com/search/?q=technology",
        ],
        "seeds": [
            "https://old.reddit.com/r/popular/",
            "https://old.reddit.com/r/technology/",
            "https://old.reddit.com/r/design/",
            "https://www.reddit.com/search/?q=design",
        ],
        "pages_per_seed": 6,
        "depth": 1,
    },
    {
        "name": "BBC",
        "starter_urls": [
            "https://www.bbc.com/news",
            "https://www.bbc.com/news/technology",
            "https://www.bbc.com/news/science-environment",
            "https://www.bbc.com/news/business",
        ],
        "seeds": [
            "https://www.bbc.com/news",
            "https://www.bbc.com/news/technology",
            "https://www.bbc.com/news/business",
        ],
        "pages_per_seed": 2,
        "depth": 1,
    },
    {
        "name": "YouTube",
        "starter_urls": [
            "https://www.youtube.com/feed/trending",
            "https://www.youtube.com/gaming",
            "https://www.youtube.com/results?search_query=technology",
        ],
        "seeds": [
            "https://www.youtube.com/feed/trending",
            "https://www.youtube.com/gaming",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "X",
        "starter_urls": [
            "https://x.com/explore",
            "https://twitter.com/explore",
        ],
        "seeds": [
            "https://x.com/explore",
            "https://twitter.com/explore",
        ],
        "pages_per_seed": 2,
        "depth": 0,
    },
    {
        "name": "Fandom",
        "starter_urls": [
            "https://www.fandom.com/",
            "https://www.fandom.com/explore",
            "https://www.fandom.com/topics/gaming",
            "https://aesthetics.fandom.com/wiki/Aesthetics_Wiki",
            "https://frutigeraero.fandom.com/wiki/Frutiger_Aero_Wiki",
        ],
        "seeds": [
            "https://www.fandom.com/explore",
            "https://www.fandom.com/topics/gaming",
            "https://aesthetics.fandom.com/wiki/Aesthetics_Wiki",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "Aesthetics Wiki",
        "starter_urls": [
            "https://aesthetics.fandom.com/wiki/Aesthetics_Wiki",
            "https://aesthetics.fandom.com/wiki/Frutiger_Aero",
            "https://frutigeraero.fandom.com/wiki/Frutiger_Aero",
        ],
        "seeds": [
            "https://aesthetics.fandom.com/wiki/Aesthetics_Wiki",
            "https://frutigeraero.fandom.com/wiki/Frutiger_Aero_Wiki",
        ],
        "pages_per_seed": 6,
        "depth": 1,
    },
    {
        "name": "wikiHow",
        "starter_urls": [
            "https://www.wikihow.com/Main-Page",
            "https://www.wikihow.com/Category:Computers-and-Electronics",
            "https://www.wikihow.com/Category:Internet",
        ],
        "seeds": [
            "https://www.wikihow.com/Main-Page",
            "https://www.wikihow.com/Category:Computers-and-Electronics",
        ],
        "pages_per_seed": 2,
        "depth": 1,
    },
    {
        "name": "Stack Overflow",
        "starter_urls": [
            "https://stackoverflow.com/questions",
            "https://stackoverflow.com/tags/python",
            "https://stackoverflow.com/tags/javascript",
        ],
        "seeds": [
            "https://stackoverflow.com/questions",
            "https://stackoverflow.com/tags",
        ],
        "pages_per_seed": 5,
        "depth": 1,
    },
    {
        "name": "Dev.to",
        "starter_urls": [
            "https://dev.to/",
            "https://dev.to/t/python",
            "https://dev.to/t/webdev",
        ],
        "seeds": [
            "https://dev.to/",
            "https://dev.to/t/webdev",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "Medium",
        "starter_urls": [
            "https://medium.com/topics",
            "https://medium.com/tag/technology",
            "https://medium.com/tag/design",
        ],
        "seeds": [
            "https://medium.com/topics",
            "https://medium.com/tag/technology",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "AllMusic",
        "starter_urls": [
            "https://www.allmusic.com/",
            "https://www.allmusic.com/genres",
            "https://www.allmusic.com/newreleases",
        ],
        "seeds": [
            "https://www.allmusic.com/",
            "https://www.allmusic.com/genres",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "AllMovie",
        "starter_urls": [
            "https://www.allmovie.com/",
            "https://www.allmovie.com/search/movies/drama",
            "https://www.allmovie.com/search/movies/comedy",
        ],
        "seeds": [
            "https://www.allmovie.com/",
            "https://www.allmovie.com/search/movies/drama",
        ],
        "pages_per_seed": 3,
        "depth": 1,
    },
    {
        "name": "Vogue",
        "starter_urls": [
            "https://www.vogue.com/fashion",
            "https://www.vogue.com/shopping",
            "https://www.vogue.com/fashion-shows",
        ],
        "seeds": [
            "https://www.vogue.com/fashion",
            "https://www.vogue.com/fashion-shows",
        ],
        "pages_per_seed": 3,
        "depth": 1,
    },
    {
        "name": "Britannica",
        "starter_urls": [
            "https://www.britannica.com/",
            "https://www.britannica.com/Arts-culture",
            "https://www.britannica.com/Science-Tech",
            "https://www.britannica.com/World-History",
        ],
        "seeds": [
            "https://www.britannica.com/",
            "https://www.britannica.com/Arts-culture",
            "https://www.britannica.com/Science-Tech",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "Stanford Encyclopedia",
        "starter_urls": [
            "https://plato.stanford.edu/",
            "https://plato.stanford.edu/searcher.py?query=philosophy",
            "https://plato.stanford.edu/contents.html",
        ],
        "seeds": [
            "https://plato.stanford.edu/",
            "https://plato.stanford.edu/contents.html",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "Library of Congress",
        "starter_urls": [
            "https://www.loc.gov/",
            "https://www.loc.gov/collections/",
            "https://www.loc.gov/search/",
        ],
        "seeds": [
            "https://www.loc.gov/",
            "https://www.loc.gov/collections/",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "Project Gutenberg",
        "starter_urls": [
            "https://www.gutenberg.org/",
            "https://www.gutenberg.org/ebooks/",
            "https://www.gutenberg.org/browse/categories/1",
        ],
        "seeds": [
            "https://www.gutenberg.org/",
            "https://www.gutenberg.org/ebooks/",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "Wikivoyage",
        "starter_urls": [
            "https://en.wikivoyage.org/wiki/Wikivoyage:Main_Page",
            "https://en.wikivoyage.org/wiki/Travel_topic",
            "https://en.wikivoyage.org/wiki/Itinerary",
        ],
        "seeds": [
            "https://en.wikivoyage.org/wiki/Wikivoyage:Main_Page",
            "https://en.wikivoyage.org/wiki/Travel_topic",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "Smithsonian",
        "starter_urls": [
            "https://www.smithsonianmag.com/",
            "https://www.smithsonianmag.com/arts-culture/",
            "https://www.smithsonianmag.com/history/",
            "https://www.smithsonianmag.com/science-nature/",
        ],
        "seeds": [
            "https://www.smithsonianmag.com/",
            "https://www.smithsonianmag.com/history/",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "Olympics",
        "starter_urls": [
            "https://newsroom.olympics.com/search/results",
            "https://newsroom.olympics.com/search/results/custom_1/",
        ],
        "seeds": [
            "https://newsroom.olympics.com/search/results",
        ],
        "pages_per_seed": 3,
        "depth": 1,
    },
    {
        "name": "Tumblr",
        "starter_urls": [
            "https://www.tumblr.com/tagged/explore",
            "https://www.tumblr.com/tagged/design",
            "https://www.tumblr.com/tagged/technology",
        ],
        "seeds": [
            "https://www.tumblr.com/tagged/explore",
            "https://www.tumblr.com/tagged/design",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "GitHub",
        "starter_urls": [
            "https://github.com/trending",
            "https://github.com/explore",
            "https://github.com/topics/python",
            "https://github.com/topics/web",
        ],
        "seeds": [
            "https://github.com/trending",
            "https://github.com/explore",
            "https://github.com/topics/web",
        ],
        "pages_per_seed": 5,
        "depth": 1,
    },
    {
        "name": "Hacker News",
        "starter_urls": [
            "https://news.ycombinator.com/",
            "https://news.ycombinator.com/news?p=2",
            "https://news.ycombinator.com/front",
        ],
        "seeds": [
            "https://news.ycombinator.com/",
            "https://news.ycombinator.com/news?p=2",
        ],
        "pages_per_seed": 5,
        "depth": 1,
    },
    {
        "name": "Ars Technica",
        "starter_urls": [
            "https://arstechnica.com/",
            "https://arstechnica.com/gadgets/",
            "https://arstechnica.com/science/",
        ],
        "seeds": [
            "https://arstechnica.com/",
            "https://arstechnica.com/gadgets/",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "The Verge",
        "starter_urls": [
            "https://www.theverge.com/",
            "https://www.theverge.com/tech",
            "https://www.theverge.com/web",
        ],
        "seeds": [
            "https://www.theverge.com/",
            "https://www.theverge.com/tech",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "NASA",
        "starter_urls": [
            "https://www.nasa.gov/",
            "https://www.nasa.gov/news/",
            "https://www.nasa.gov/missions/",
        ],
        "seeds": [
            "https://www.nasa.gov/",
            "https://www.nasa.gov/news/",
        ],
        "pages_per_seed": 5,
        "depth": 1,
    },
    {
        "name": "Python",
        "starter_urls": [
            "https://www.python.org/",
            "https://www.python.org/blogs/",
            "https://docs.python.org/3/",
        ],
        "seeds": [
            "https://www.python.org/",
            "https://www.python.org/blogs/",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "MDN",
        "starter_urls": [
            "https://developer.mozilla.org/en-US/",
            "https://developer.mozilla.org/en-US/docs/Web",
            "https://developer.mozilla.org/en-US/docs/Web/HTML",
        ],
        "seeds": [
            "https://developer.mozilla.org/en-US/",
            "https://developer.mozilla.org/en-US/docs/Web",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "Mozilla",
        "starter_urls": [
            "https://www.mozilla.org/",
            "https://www.mozilla.org/en-US/firefox/",
            "https://blog.mozilla.org/",
        ],
        "seeds": [
            "https://www.mozilla.org/",
            "https://blog.mozilla.org/",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "MedlinePlus",
        "starter_urls": [
            "https://medlineplus.gov/",
            "https://medlineplus.gov/healthtopics.html",
            "https://medlineplus.gov/encyclopedia.html",
        ],
        "seeds": [
            "https://medlineplus.gov/",
            "https://medlineplus.gov/healthtopics.html",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
    {
        "name": "Wiktionary",
        "starter_urls": [
            "https://en.wiktionary.org/wiki/Wiktionary:Main_Page",
            "https://en.wiktionary.org/wiki/Category:English_lemmas",
        ],
        "seeds": [
            "https://en.wiktionary.org/wiki/Wiktionary:Main_Page",
        ],
        "pages_per_seed": 4,
        "depth": 1,
    },
]
DISCOVERY_HOSTS = {
    urlparse(url).netloc.lower()
    for profile in DEFAULT_SOURCE_PROFILES
    for url in (profile.get("starter_urls", []) + profile["seeds"])
}
BOOTSTRAP_TARGET_PAGES = 1200
BOOTSTRAP_COOLDOWN_SECONDS = 600
NEWS_QUERY_TERMS = {
    "news",
    "latest",
    "today",
    "breaking",
    "update",
    "updates",
    "war",
    "election",
    "weather",
    "score",
    "scores",
    "headline",
    "headlines",
}
HOWTO_QUERY_TERMS = {
    "guide",
    "tutorial",
    "recipe",
    "fix",
    "repair",
    "install",
    "build",
    "learn",
}
REFERENCE_RESULT_HOSTS = {
    "en.wikipedia.org",
    "en.wiktionary.org",
    "en.wikivoyage.org",
    "www.britannica.com",
    "plato.stanford.edu",
    "www.loc.gov",
    "www.gutenberg.org",
    "www.smithsonianmag.com",
    "medlineplus.gov",
    "developer.mozilla.org",
    "docs.python.org",
    "www.python.org",
}
LOW_PRIORITY_REFERENCE_HOSTS = {
    "www.bbc.com",
    "www.wikihow.com",
}
BBC_TOP_STORIES_FEED = "https://feeds.bbci.co.uk/news/rss.xml?edition=int"
WIKIPEDIA_API_ENDPOINT = "https://en.wikipedia.org/w/api.php"
NEWS_CACHE_TTL = 900
NEWS_CACHE = {"expires_at": 0.0, "items": [], "running": False, "last_error": ""}
WEB_SEARCH_CACHE = {}
WEB_SEARCH_CACHE_LOCK = threading.Lock()
BOOTSTRAP_STATE = {
    "last_run": 0.0,
    "last_message": "",
    "last_error": "",
    "running": False,
    "thread": None,
    "scheduled": False,
}
QUERY_BOOST_STATE = {
    "running": set(),
    "lock": threading.Lock(),
}
WIKIPEDIA_BOOTSTRAP_QUERIES = [
    "history",
    "science",
    "art",
    "technology",
    "society",
    "geography",
    "literature",
    "philosophy",
]
OFFICIAL_DOMAIN_SUFFIXES = [
    ".com",
    ".org",
    ".net",
    ".io",
    ".app",
    ".dev",
    ".mit.edu",
    ".onrender.com",
]
OFFICIAL_HOST_OVERRIDES = {
    "scratch": ["scratch.mit.edu"],
}

# ── Sort mode labels ─────────────────────────────────────────────
SORT_MODES = [
    ("relevant", "Most Relevant"),
    ("popular", "Most Popular"),
    ("rated", "Top Rated"),
    ("primer", "Primer 1989"),
]

RESULTS_PER_PAGE = 10


def load_template(filename: str) -> str:
    return (TEMPLATE_DIR / filename).read_text(encoding="utf-8")


def fill_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    return re.sub(r"\{\{[A-Z0-9_]+\}\}", "", rendered)


# ═══════════════════════════════════════════════════════════════════
# DATA FETCHING (BBC News, Wikipedia)
# ═══════════════════════════════════════════════════════════════════

def _make_web_result(title: str, url: str, description: str, rank: int) -> SearchResult:
    now = time.time()
    return SearchResult(
        title=title,
        url=url,
        snippet=description or f"Web result from {urlparse(url).netloc}",
        score=1_000_000 - rank,
        matched_terms=0,
        engagement_score=0,
        term_frequency=0,
        inbound_links=0,
        referring_hosts=0,
        authority_score=0.0,
        domain_trust=0.7,
        star_rating=3.5,
        crawl_timestamp=now,
        meta_description=description,
    )


def _normalize_live_query(query: str) -> str:
    cleaned = " ".join((query or "").split()).strip()
    cleaned = re.sub(
        r"^how\s+to\s+(?:make|bake|cook|find|get|use|install|fix)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+facts?$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip() or " ".join((query or "").split()).strip()


def _fetch_bing_rss_results(
    query: str, page: int, per_page: int
) -> list[SearchResult]:
    params = urlencode(
        {
            "q": query,
            "format": "rss",
            "count": str(per_page),
            "first": str((page - 1) * per_page + 1),
        }
    )
    req = request.Request(
        f"https://www.bing.com/search?{params}",
        headers={"User-Agent": "Mozilla/5.0 (compatible; NESAT/2000)"},
    )
    root = None
    for _ in range(2):
        try:
            with request.urlopen(req, timeout=4) as response:
                root = element_tree.fromstring(response.read(300_000))
            break
        except Exception:
            continue
    if root is None:
        return []

    results = []
    for rank, item in enumerate(root.findall("./channel/item"), start=1):
        title = " ".join(unescape(item.findtext("title") or "").split()).strip()
        url = (item.findtext("link") or "").strip()
        description = unescape(item.findtext("description") or "")
        description = " ".join(re.sub(r"<[^>]+>", " ", description).split()).strip()
        if title and url.startswith(("http://", "https://")):
            results.append(_make_web_result(title, url, description, rank))
    return results[:per_page]


def _fetch_wikipedia_search_results(query: str, limit: int = 4) -> list[SearchResult]:
    params = urlencode(
        {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": str(max(1, min(limit, 8))),
            "prop": "extracts|info",
            "exintro": "1",
            "explaintext": "1",
            "exsentences": "2",
            "inprop": "url",
            "redirects": "1",
            "format": "json",
            "utf8": "1",
        }
    )
    req = request.Request(
        f"{WIKIPEDIA_API_ENDPOINT}?{params}",
        headers={"User-Agent": "NESATBot/2000 (+http://127.0.0.1)"},
    )
    payload = None
    for _ in range(2):
        try:
            with request.urlopen(req, timeout=4) as response:
                payload = json.loads(
                    response.read().decode("utf-8", errors="replace")
                )
            break
        except Exception:
            continue
    if payload is None:
        return []

    results = []
    pages = payload.get("query", {}).get("pages", {})
    ordered_pages = sorted(pages.values(), key=lambda item: item.get("index", 9999))
    for rank, page_data in enumerate(ordered_pages, start=1):
        title = " ".join((page_data.get("title") or "").split()).strip()
        description = " ".join((page_data.get("extract") or "").split()).strip()
        url = (page_data.get("fullurl") or "").strip()
        if title and url:
            results.append(
                _make_web_result(
                    f"{title} - Wikipedia",
                    url,
                    description,
                    rank + 1,
                )
            )
    return results


def _fetch_reddit_search_results(query: str, limit: int = 3) -> list[SearchResult]:
    params = urlencode({"q": query, "sort": "relevance", "t": "all"})
    req = request.Request(
        f"https://www.reddit.com/search.rss?{params}",
        headers={"User-Agent": "Mozilla/5.0 (compatible; NESAT/2000)"},
    )
    try:
        with request.urlopen(req, timeout=4) as response:
            root = element_tree.fromstring(response.read(300_000))
    except Exception:
        return []

    atom = "{http://www.w3.org/2005/Atom}"
    results = []
    for rank, entry in enumerate(root.findall(f"{atom}entry"), start=1):
        title = " ".join((entry.findtext(f"{atom}title") or "").split()).strip()
        link_node = entry.find(f"{atom}link")
        url = (link_node.get("href") if link_node is not None else "") or ""
        content = entry.findtext(f"{atom}content") or ""
        description = " ".join(
            unescape(re.sub(r"<[^>]+>", " ", content)).split()
        ).strip()
        if title and url:
            results.append(_make_web_result(f"{title} - Reddit", url, description, rank + 5))
        if len(results) >= limit:
            break
    return results


def _fetch_deviantart_search_results(query: str, limit: int = 3) -> list[SearchResult]:
    req = request.Request(
        "https://backend.deviantart.com/rss.xml?" + urlencode({"q": query}),
        headers={"User-Agent": "Mozilla/5.0 (compatible; NESAT/2000)"},
    )
    try:
        with request.urlopen(req, timeout=4) as response:
            root = element_tree.fromstring(response.read(300_000))
    except Exception:
        return []

    results = []
    for rank, item in enumerate(root.findall("./channel/item"), start=1):
        title = " ".join((item.findtext("title") or "").split()).strip()
        url = (item.findtext("link") or "").strip()
        description = " ".join(
            unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or "")).split()
        ).strip()
        if title and url:
            results.append(
                _make_web_result(f"{title} - DeviantArt", url, description, rank + 5)
            )
        if len(results) >= limit:
            break
    return results


def _fetch_github_search_results(query: str, limit: int = 3) -> list[SearchResult]:
    params = urlencode({"q": query, "per_page": str(limit)})
    req = request.Request(
        f"https://api.github.com/search/repositories?{params}",
        headers={
            "User-Agent": "NESATBot/2000",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with request.urlopen(req, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception:
        return []

    results = []
    for rank, item in enumerate(payload.get("items", []), start=1):
        title = item.get("full_name") or item.get("name") or "GitHub project"
        url = item.get("html_url") or ""
        description = " ".join((item.get("description") or "GitHub repository").split())
        if url:
            results.append(_make_web_result(f"{title} - GitHub", url, description, rank + 5))
    return results[:limit]


def _fetch_youtube_search_results(query: str, limit: int = 3) -> list[SearchResult]:
    tutorial_query = query
    if not re.search(r"\b(tutorial|guide|how to|walkthrough)\b", query, re.IGNORECASE):
        tutorial_query = f"{query} tutorial"
    url = "https://www.youtube.com/results?" + urlencode(
        {"search_query": tutorial_query}
    )
    req = request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; NESAT/2000)",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with request.urlopen(req, timeout=5) as response:
            html = response.read(1_500_000).decode("utf-8", errors="replace")
    except Exception:
        return []

    pattern = re.compile(
        r'"videoRenderer":\{"videoId":"([^"]+)".*?'
        r'"title":\{"runs":\[\{"text":"((?:\\.|[^"\\])*)"',
        re.DOTALL,
    )
    results = []
    seen_ids = set()
    for rank, (video_id, encoded_title) in enumerate(pattern.findall(html), start=1):
        if video_id in seen_ids:
            continue
        seen_ids.add(video_id)
        try:
            title = json.loads(f'"{encoded_title}"')
        except Exception:
            title = encoded_title.replace(r"\u0026", "&")
        results.append(
            _make_web_result(
                f"{title} - YouTube",
                f"https://www.youtube.com/watch?v={video_id}",
                f"Video tutorial related to {query}.",
                rank + 4,
            )
        )
        if len(results) >= limit:
            break
    return results


def _community_search_fallbacks(query: str) -> list[SearchResult]:
    return [
        _make_web_result(
            f'"{query}" discussions - Reddit',
            "https://www.reddit.com/search/?" + urlencode({"q": query}),
            "Search Reddit posts and community discussions.",
            20,
        ),
        _make_web_result(
            f'"{query}" artwork and themes - DeviantArt',
            "https://www.deviantart.com/search?" + urlencode({"q": query}),
            "Search DeviantArt themes, screenshots, and customization projects.",
            21,
        ),
        _make_web_result(
            f'"{query}" projects - GitHub',
            "https://github.com/search?" + urlencode({"q": query, "type": "repositories"}),
            "Search open-source projects and release pages on GitHub.",
            22,
        ),
        _make_web_result(
            f'"{query}" archived software - Internet Archive',
            "https://archive.org/search?" + urlencode({"query": query}),
            "Search archived software and preserved web pages.",
            23,
        ),
    ]


def _known_legacy_results(query: str) -> list[SearchResult]:
    lowered = query.lower()
    results = []
    if "chrome" in lowered and re.search(r"\b79(?:\.0)?\b", lowered):
        results.extend(
            [
                _make_web_result(
                    "Google Chrome 79.0.3945.130 (32-bit) for Windows 7 - FilePuma",
                    "https://www.filepuma.com/download/google_chrome_32bit_79.0.3945.130-24455/",
                    "Exact Chrome 79 x86 download page for Windows 7. This is an old third-party binary; verify its signature and hash before running it.",
                    1,
                ),
                _make_web_result(
                    "Download Google Chrome 79.0.3945.130 (32-bit) - Downzen",
                    "https://downzen.com/en/windows/google-chrome/download/7903945130/",
                    "Chrome 79.0.3945.130 32-bit archive page with file hashes and scan information.",
                    2,
                ),
                _make_web_result(
                    "Google Chrome 79.0.3945.130 package - Chocolatey",
                    "https://community.chocolatey.org/packages/GoogleChrome/79.0.3945.130",
                    "Archived Chocolatey package metadata for Chrome 79. Google no longer officially distributes old Chrome builds.",
                    3,
                ),
            ]
        )

    if "10to7" in lowered or (
        "transformation" in lowered and "windows" in lowered and "7" in lowered
    ):
        results.extend(
            [
                _make_web_result(
                    "10to7 and Windows 7 transformation discussions - WinClassic",
                    "https://winclassic.net/search/results?" + urlencode({"keyword": query}),
                    "Search WinClassic customization guides, restoration packs, and discussions.",
                    1,
                ),
                _make_web_result(
                    "10to7 transformation pack search - BetaWiki",
                    "https://betawiki.net/wiki/Special:Search?" + urlencode({"search": query}),
                    "Search BetaWiki for Windows builds, transformation projects, and related history.",
                    2,
                ),
                _make_web_result(
                    "Reunion7 / Windows 10-to-7 project FAQ",
                    "https://www.reunion7.com/faq.html",
                    "Information about a Windows 10-to-7 modification and related projects.",
                    3,
                ),
            ]
        )
    return results


def _filter_relevant_results(
    results: list[SearchResult], query: str
) -> list[SearchResult]:
    ignored = {
        "and", "bit", "download", "for", "from", "old", "pack", "the",
        "to", "version", "windows", "with",
    }
    terms = [
        term
        for term in re.findall(r"[a-z0-9][a-z0-9_-]{1,31}", query.lower())
        if term not in ignored
    ]
    if not terms:
        return results
    filtered = []
    for result in results:
        haystack = f"{result.title} {result.snippet} {result.url}".lower()
        if any(term in haystack for term in terms):
            filtered.append(result)
    return filtered


def fetch_live_web_results(
    query: str, page: int = 1, per_page: int = RESULTS_PER_PAGE
) -> list[SearchResult]:
    """Search current web sources and retain results for the server session."""
    original_query = " ".join((query or "").split()).strip()
    if not original_query:
        return []

    page = max(1, min(int(page), 20))
    per_page = max(1, min(int(per_page), 10))
    cache_key = (original_query.lower(), page, per_page)
    with WEB_SEARCH_CACHE_LOCK:
        cached = WEB_SEARCH_CACHE.get(cache_key)
        if cached is not None:
            return cached

    live_query = _normalize_live_query(original_query)
    wikipedia_results = []
    reddit_results = []
    deviantart_results = []
    github_results = []
    youtube_results = []
    if page == 1:
        with ThreadPoolExecutor(max_workers=5) as pool:
            source_futures = {
                "wikipedia": pool.submit(_fetch_wikipedia_search_results, live_query, 4),
                "reddit": pool.submit(_fetch_reddit_search_results, original_query, 3),
                "deviantart": pool.submit(
                    _fetch_deviantart_search_results, original_query, 3
                ),
                "github": pool.submit(_fetch_github_search_results, original_query, 3),
                "youtube": pool.submit(
                    _fetch_youtube_search_results, original_query, 3
                ),
            }
            wikipedia_results = source_futures["wikipedia"].result()
            reddit_results = source_futures["reddit"].result()
            deviantart_results = source_futures["deviantart"].result()
            github_results = source_futures["github"].result()
            youtube_results = source_futures["youtube"].result()
        wikipedia_results = _filter_relevant_results(wikipedia_results, live_query)
        reddit_results = _filter_relevant_results(reddit_results, original_query)
        deviantart_results = _filter_relevant_results(
            deviantart_results, original_query
        )
        github_results = _filter_relevant_results(github_results, original_query)
        youtube_results = _filter_relevant_results(youtube_results, original_query)
    knowledge_text = " ".join(
        f"{item.title} {item.snippet}" for item in wikipedia_results
    ).lower()
    is_food_topic = bool(
        re.search(r"\b(fruit|food|edible|dish|recipe|vegetable|berry)\b", knowledge_text)
    )
    related_query = ""
    if page == 1 and is_food_topic and len(live_query.split()) == 1:
        related_query = f"{live_query} pie"

    # Bing frequently resets one of two simultaneous requests from the same
    # client. Sequential calls are still sub-second and keep related results.
    base_results = _fetch_bing_rss_results(live_query, page, per_page)
    base_results = _filter_relevant_results(base_results, live_query)
    related_results = (
        _fetch_bing_rss_results(related_query, 1, 3) if related_query else []
    )
    if related_query and not related_results:
        recipe_url = "https://www.allrecipes.com/search?" + urlencode(
            {"q": related_query}
        )
        related_results = [
            _make_web_result(
                f"{related_query.title()} Recipes",
                recipe_url,
                f"Recipes and cooking instructions for {related_query}.",
                5,
            )
        ]

    known_results = _known_legacy_results(original_query) if page == 1 else []
    legacy_intent = bool(
        re.search(
            r"\b(download|win7|windows 7|32bit|32-bit|transformation|theme|pack|10to7|legacy|old version)\b",
            original_query,
            flags=re.IGNORECASE,
        )
    )
    fallback_results = _community_search_fallbacks(original_query) if legacy_intent else []
    archive_results = fallback_results[3:4]
    if not reddit_results and fallback_results:
        reddit_results = fallback_results[:1]
    if not deviantart_results and fallback_results:
        deviantart_results = fallback_results[1:2]
    if not github_results and fallback_results:
        github_results = fallback_results[2:]
    if not youtube_results:
        youtube_results = [
            _make_web_result(
                f'"{original_query}" tutorials - YouTube',
                "https://www.youtube.com/results?"
                + urlencode({"search_query": f"{original_query} tutorial"}),
                "Search YouTube for video tutorials and walkthroughs.",
                24,
            )
        ]

    # Blend intents instead of allowing ten near-identical links from one host.
    ordered = []
    ordered.extend(known_results)
    if base_results and not known_results:
        ordered.append(base_results[0])
    ordered.extend(wikipedia_results[:2])
    ordered.extend(reddit_results[:2])
    ordered.extend(deviantart_results[:2])
    ordered.extend(youtube_results[:2])
    ordered.extend(github_results[:1])
    ordered.extend(archive_results)
    ordered.extend(related_results[:2])
    ordered.extend(base_results if known_results else base_results[1:])

    results = []
    seen_urls = set()
    for result in ordered:
        normalized = result.url.rstrip("/").lower()
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        results.append(result)
        if len(results) >= per_page:
            break

    # Cache for the entire Python process. It resets only when the server stops.
    complete_enough = page > 1 or bool(
        known_results or base_results or wikipedia_results or reddit_results
    )
    if results and complete_enough:
        with WEB_SEARCH_CACHE_LOCK:
            WEB_SEARCH_CACHE[cache_key] = results
    return results


def search_web_and_index(
    query: str, page: int, per_page: int, sort_mode: str
) -> tuple[list[SearchResult], int]:
    """Search the local index and live web concurrently, then remove duplicates."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        local_future = pool.submit(
            ENGINE.search_paginated,
            query,
            page=page,
            per_page=per_page,
            sort_mode=sort_mode,
        )
        web_future = pool.submit(fetch_live_web_results, query, page, per_page)
        try:
            local_results, local_count = local_future.result(timeout=5)
        except Exception:
            local_results, local_count = [], 0
        try:
            web_results = web_future.result(timeout=5)
        except Exception:
            web_results = []

    combined = []
    seen_urls = set()
    for result in [*web_results, *local_results]:
        normalized = result.url.rstrip("/").lower()
        if normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        combined.append(result)
        if len(combined) >= per_page:
            break

    # RSS does not expose a total, so a full page means there may be another.
    web_count_floor = (page - 1) * per_page + len(web_results)
    if len(web_results) == per_page:
        web_count_floor += per_page
    return combined, max(local_count, web_count_floor)


def fetch_bbc_news(limit: int = 6) -> list[dict[str, str]]:
    now = time.time()
    if NEWS_CACHE["items"] and now < NEWS_CACHE["expires_at"]:
        return NEWS_CACHE["items"][:limit]

    try:
        req = request.Request(
            BBC_TOP_STORIES_FEED,
            headers={"User-Agent": "NESATBot/2000 (+http://127.0.0.1)"},
        )
        with request.urlopen(req, timeout=10) as response:
            payload = response.read()
        root = element_tree.fromstring(payload)
        items = []
        for item in root.findall("./channel/item")[:limit]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            if title and link:
                items.append({"title": title, "link": link, "pub_date": pub_date})
        NEWS_CACHE["items"] = items
        NEWS_CACHE["expires_at"] = now + NEWS_CACHE_TTL
        NEWS_CACHE["last_error"] = ""
        return items
    except Exception:
        return NEWS_CACHE["items"][:limit]


def fetch_wikipedia_documents(query: str, limit: int = 8) -> list[dict[str, str]]:
    cleaned = (query or "").strip()
    if not cleaned:
        return []

    search_params = urlencode(
        {
            "action": "query",
            "list": "search",
            "srsearch": cleaned,
            "srlimit": str(max(1, min(limit, 12))),
            "format": "json",
            "utf8": "1",
        }
    )
    search_url = f"{WIKIPEDIA_API_ENDPOINT}?{search_params}"
    req = request.Request(
        search_url,
        headers={"User-Agent": "NESATBot/2000 (+http://127.0.0.1)"},
    )

    with request.urlopen(req, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))

    results = []
    for item in payload.get("query", {}).get("search", [])[:limit]:
        title = (item.get("title") or "").strip()
        if not title:
            continue
        extract_params = urlencode(
            {
                "action": "query",
                "prop": "extracts",
                "explaintext": "1",
                "exintro": "1",
                "titles": title,
                "format": "json",
                "utf8": "1",
            }
        )
        extract_url = f"{WIKIPEDIA_API_ENDPOINT}?{extract_params}"
        extract_req = request.Request(
            extract_url,
            headers={"User-Agent": "NESATBot/2000 (+http://127.0.0.1)"},
        )
        try:
            with request.urlopen(extract_req, timeout=8) as extract_response:
                extract_payload = json.loads(
                    extract_response.read().decode("utf-8", errors="replace")
                )
            pages = extract_payload.get("query", {}).get("pages", {})
            extract_text = ""
            for page_data in pages.values():
                extract_text = " ".join((page_data.get("extract") or "").split()).strip()
                if extract_text:
                    break
        except Exception:
            extract_text = ""

        snippet = re.sub(r"<.*?>", "", item.get("snippet") or "").strip()
        content = extract_text or snippet
        if not content:
            continue

        results.append(
            {
                "title": title,
                "url": f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
                "content": content,
            }
        )
    return results


def index_wikipedia_results(query: str, limit: int = 8) -> int:
    added = 0
    for document in fetch_wikipedia_documents(query, limit=limit):
        try:
            created = ENGINE.index_document(
                url=document["url"],
                title=document["title"],
                content=document["content"],
                engagement_score=0,
            )
            if created:
                added += 1
        except Exception:
            continue
    if added:
        ENGINE.recompute_authority_scores()
    return added


def index_official_homepage_candidates(query: str, limit: int = 2, timeout: float = 2.5) -> int:
    term = extract_single_keyword(query)
    if not term:
        return 0

    added = 0
    for target in build_official_candidate_requests(query)[: max(1, limit)]:
        try:
            req = request.Request(
                target["url"],
                headers={"User-Agent": "Mozilla/5.0 (compatible; NESATBot/2000)"},
            )
            with request.urlopen(req, timeout=timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    continue
                charset = response.headers.get_content_charset() or "utf-8"
                html = response.read(220_000).decode(charset, errors="replace")
                final_url = response.geturl()

            parser = DocumentParser(final_url)
            parser.feed(html)
            parser.close()

            title = parser.get_title().strip() or f"{term.title()} - Official Website"
            content = parser.get_text().strip()
            if not content:
                content = parser.meta_description.strip() or f"{term.title()} official website homepage"

            created = ENGINE.index_document(
                url=final_url,
                title=title,
                content=content,
                engagement_score=0,
            )
            if created:
                added += 1
        except Exception:
            continue

    if added:
        ENGINE.recompute_authority_scores()
    return added


def start_bbc_news_refresh(force: bool = False):
    now = time.time()
    if NEWS_CACHE["running"]:
        return
    if not force and NEWS_CACHE["items"] and now < NEWS_CACHE["expires_at"]:
        return

    NEWS_CACHE["running"] = True

    def worker():
        try:
            fetch_bbc_news()
        except Exception as exc:
            NEWS_CACHE["last_error"] = str(exc)
        finally:
            NEWS_CACHE["running"] = False

    threading.Thread(target=worker, name="nesat-bbc-news", daemon=True).start()


# ═══════════════════════════════════════════════════════════════════
# RENDERING FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def render_message_panel(message="", error="") -> str:
    if error:
        return f'<section class="window message-window"><div class="window-body"><p style="color:red; font-weight:bold; margin:0;">{escape(error)}</p></div></section>'
    if message:
        return f'<section class="window message-window"><div class="window-body"><p style="color:green; font-weight:bold; margin:0;">{escape(message)}</p></div></section>'
    return ""


def render_source_breakdown() -> str:
    rows = ENGINE.top_hosts(8)
    if not rows:
        return ""
    items = []
    for row in rows:
        items.append(
            f'<span class="source-chip">{escape(row["host"])} ({int(row["page_count"])})</span>'
        )
    return "".join(items)


def render_bbc_news_placeholder() -> str:
    if NEWS_CACHE["items"]:
        return render_bbc_news()
    if NEWS_CACHE["running"]:
        return '<p style="color:#70757a;font-size:13px;">BBC news is loading...</p>'
    return ""


def render_bbc_news() -> str:
    items = NEWS_CACHE["items"]
    if not items:
        return ""
    rows = []
    for item in items:
        rows.append(
            f'<a href="{escape(item["link"])}" target="_blank" rel="noreferrer">{escape(item["title"])}</a>'
        )
    return " &middot; ".join(rows)


# ── Star rating renderer ────────────────────────────────────────
def render_stars(rating: float) -> str:
    if rating <= 0:
        return ""
    full_stars = int(rating)
    half = rating - full_stars >= 0.5
    empty = 5 - full_stars - (1 if half else 0)
    stars = "★" * full_stars
    if half:
        stars += "★"
        full_stars += 1
    stars += "☆" * empty
    return f'<div class="g-rating">{stars}<span class="g-rating-num">{rating:.1f}</span></div>'


# ── Domain breadcrumb ────────────────────────────────────────────
def build_breadcrumb(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc
    path_parts = [p for p in parsed.path.strip("/").split("/") if p][:3]
    if path_parts:
        crumbs = " › ".join(path_parts)
        return f"{host} › {crumbs}"
    return host


# ── Query highlighting ──────────────────────────────────────────
def highlight_query_text(text: str, query: str) -> str:
    raw_text = text or ""
    terms = []
    phrase_terms = [
        term for term in re.findall(r"[a-z0-9][a-z0-9_-]{1,31}", query.lower()) if len(term) >= 3
    ]
    phrase = " ".join(phrase_terms).strip()
    if phrase and len(phrase_terms) > 1:
        terms.append(phrase)
    terms.extend(term for term in phrase_terms if term not in terms)
    if not terms:
        return escape(raw_text)

    pattern = re.compile(
        "(" + "|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True)) + ")",
        re.IGNORECASE,
    )
    parts = pattern.split(raw_text)
    rendered = []
    for part in parts:
        if not part:
            continue
        if pattern.fullmatch(part):
            rendered.append(f"<b>{escape(part)}</b>")
        else:
            rendered.append(escape(part))
    return "".join(rendered)


# ── Google-style result card ─────────────────────────────────────
def render_result_card(result, query: str) -> str:
    host = urlparse(result.url).netloc or result.url
    breadcrumb = build_breadcrumb(result.url)
    favicon_url = f"https://www.google.com/s2/favicons?domain={escape(host)}&sz=32"
    title_html = highlight_query_text(result.title, query)
    snippet_html = highlight_query_text(result.snippet, query)
    stars_html = render_stars(result.star_rating)

    return f"""
    <div class="result-item" id="result-{abs(hash(result.url)) % 100000}">
      <h2 class="g-title"><img class="g-favicon" src="{favicon_url}" alt="" loading="lazy" onerror="this.style.display='none'"><a href="{escape(result.url)}" target="_blank" rel="noreferrer">{title_html}</a></h2>
      <p class="result-link">{escape(result.url)}</p>
      <p class="result-snippet">{snippet_html}</p>
      {stars_html}
    </div>
    """


# ── Result list ──────────────────────────────────────────────────
def render_result_cards(query: str, results) -> str:
    if not results:
        return f"""
        <section class="empty-state">
          <h2>No results for "{escape(query)}"</h2>
          <p>Nesat searched the current index and found nothing. Try different keywords or rebuild the index.</p>
        </section>
        """
    return "".join(render_result_card(r, query) for r in results)


# ── Sort chips ───────────────────────────────────────────────────
def render_sort_chips(current_sort: str, query: str) -> str:
    chips = ['<div class="sort-chips">']
    for mode_key, mode_label in SORT_MODES:
        active = "active" if mode_key == current_sort else ""
        params = {"q": query, "sort": mode_key}
        href = f"results.html?{urlencode(params)}"
        chips.append(f'<a href="{escape(href)}" class="sort-chip {active}" id="sort-{mode_key}">{escape(mode_label)}</a>')
    
    # Images tab
    img_active = "active" if current_sort == "images" else ""
    img_params = {"q": query, "sort": "images"}
    img_href = f"results.html?{urlencode(img_params)}"
    chips.append(f'<a href="{escape(img_href)}" class="sort-chip {img_active}" id="sort-images">Images</a>')

    chips.append("</div>")
    return "".join(chips)


# ── Pagination ───────────────────────────────────────────────────
def render_pagination(current_page: int, total_results: int, query: str, sort_mode: str) -> str:
    total_pages = min(999, math.ceil(total_results / RESULTS_PER_PAGE))
    if total_pages <= 1:
        return ""

    def page_url(p):
        params = {"q": query, "page": str(p)}
        if sort_mode != "relevant":
            params["sort"] = sort_mode
        return f"results.html?{urlencode(params)}"

    parts = []

    # Previous arrow
    if current_page > 1:
        parts.append(f'<a href="{escape(page_url(current_page - 1))}" class="pg-arrow">&lsaquo;</a>')
    else:
        parts.append('<span class="disabled">&lsaquo;</span>')

    # Page numbers with Google-style ellipsis
    pages_to_show = _compute_page_range(current_page, total_pages)

    last_shown = 0
    for p in pages_to_show:
        if last_shown > 0 and p > last_shown + 1:
            parts.append('<span class="pg-ellipsis">...</span>')

        if p == current_page:
            parts.append(f'<span class="pg-active">{p}</span>')
        else:
            parts.append(f'<a href="{escape(page_url(p))}">{p}</a>')
        last_shown = p

    # Next arrow
    if current_page < total_pages:
        parts.append(f'<a href="{escape(page_url(current_page + 1))}" class="pg-arrow">&rsaquo;</a>')
    else:
        parts.append('<span class="disabled">&rsaquo;</span>')

    return "".join(parts)


def _compute_page_range(current: int, total: int) -> list[int]:
    """Google-style page range: first 2, around current, last 2."""
    pages = set()

    # Always show first 2
    pages.add(1)
    if total >= 2:
        pages.add(2)

    # Pages around current (window of 5)
    for p in range(max(1, current - 2), min(total, current + 2) + 1):
        pages.add(p)

    # Always show last 2
    if total >= 2:
        pages.add(total - 1)
    pages.add(total)

    return sorted(pages)


# ═══════════════════════════════════════════════════════════════════
# QUERY CLASSIFICATION & BOOSTING
# ═══════════════════════════════════════════════════════════════════

def classify_query(query: str) -> str:
    cleaned = (query or "").strip().lower()
    if not cleaned:
        return "reference"
    if cleaned.startswith("how ") or cleaned.startswith("how to "):
        return "howto"

    terms = set(re.findall(r"[a-z0-9][a-z0-9_-]{1,31}", cleaned))
    if terms & NEWS_QUERY_TERMS:
        return "news"
    if terms & HOWTO_QUERY_TERMS:
        return "howto"
    return "reference"


def needs_reference_source_boost(results) -> bool:
    if not results:
        return True

    top_results = results[:6]
    reference_hits = 0
    low_priority_hits = 0
    for result in top_results:
        host = urlparse(result.url).netloc.lower()
        if host in REFERENCE_RESULT_HOSTS:
            reference_hits += 1
        if host in LOW_PRIORITY_REFERENCE_HOSTS:
            low_priority_hits += 1
    return reference_hits == 0 or low_priority_hits >= max(2, len(top_results) // 2)


def extract_single_keyword(query: str) -> str:
    tokens = re.findall(r"[a-z0-9][a-z0-9_-]{1,31}", (query or "").strip().lower())
    return tokens[0] if len(tokens) == 1 else ""


def build_official_candidate_requests(query: str) -> list[dict[str, object]]:
    term = extract_single_keyword(query)
    if not term:
        return []

    host_candidates = []
    seen_hosts = set()

    def add_host(host: str):
        clean_host = (host or "").strip().lower()
        if not clean_host or clean_host in seen_hosts:
            return
        seen_hosts.add(clean_host)
        host_candidates.append(clean_host)

    for host in OFFICIAL_HOST_OVERRIDES.get(term, []):
        add_host(host)

    for suffix in OFFICIAL_DOMAIN_SUFFIXES:
        add_host(f"{term}{suffix}")
        if suffix not in {".mit.edu", ".onrender.com"}:
            add_host(f"www.{term}{suffix}")

    return [
        {
            "url": f"https://{host}/",
            "max_pages": 1,
            "max_depth": 0,
            "same_domain_only": True,
        }
        for host in host_candidates
    ]


def has_official_domain_match(results, query: str) -> bool:
    term = extract_single_keyword(query)
    if not term or not results:
        return False

    for result in results[:3]:
        host = urlparse(result.url).netloc.lower().split(":", 1)[0]
        labels = [label for label in host.split(".") if label and label != "www"]
        if not labels:
            continue
        leftmost_label = labels[0]
        root_label = labels[-2] if len(labels) >= 2 else labels[0]
        if term in labels and (leftmost_label == term or root_label == term):
            return True
    return False


def boost_query_specific_results(query: str):
    cleaned = query.strip()
    if not cleaned:
        return

    targeted_requests = build_official_candidate_requests(cleaned)

    try:
        index_official_homepage_candidates(cleaned, limit=3, timeout=3.0)
    except Exception:
        pass

    try:
        index_wikipedia_results(cleaned, limit=12)
    except Exception:
        pass

    wiki_title = quote(cleaned.replace(" ", "_"))
    query_param = quote(cleaned)
    query_mode = classify_query(cleaned)
    targeted_requests.extend([
        {"url": f"https://en.wikipedia.org/wiki/{wiki_title}", "max_pages": 20, "max_depth": 1},
        {"url": f"https://en.wikipedia.org/w/index.php?search={query_param}", "max_pages": 18, "max_depth": 1},
        {"url": f"https://www.britannica.com/search?query={query_param}", "max_pages": 12, "max_depth": 1},
        {"url": f"https://www.loc.gov/search/?in=all&q={query_param}", "max_pages": 10, "max_depth": 1},
        {"url": f"https://www.smithsonianmag.com/search/?q={query_param}", "max_pages": 10, "max_depth": 1},
        {"url": f"https://www.gutenberg.org/ebooks/search/?query={query_param}", "max_pages": 8, "max_depth": 1},
        {"url": f"https://plato.stanford.edu/searcher.py?query={query_param}", "max_pages": 8, "max_depth": 1},
        {"url": f"https://en.wikivoyage.org/w/index.php?search={query_param}", "max_pages": 8, "max_depth": 1},
        {"url": f"https://medlineplus.gov/search/?query={query_param}", "max_pages": 8, "max_depth": 1},
        {"url": f"https://old.reddit.com/search/?q={query_param}", "max_pages": 10, "max_depth": 1},
        {"url": f"https://github.com/search?q={query_param}&type=repositories", "max_pages": 8, "max_depth": 1},
        {"url": f"https://dev.to/search?q={query_param}", "max_pages": 8, "max_depth": 1},
        {"url": f"https://medium.com/search?q={query_param}", "max_pages": 8, "max_depth": 1},
        {"url": f"https://www.fandom.com/?s={query_param}", "max_pages": 8, "max_depth": 1},
        {"url": f"https://aesthetics.fandom.com/wiki/{wiki_title}", "max_pages": 8, "max_depth": 1},
        {"url": f"https://frutigeraero.fandom.com/wiki/{wiki_title}", "max_pages": 8, "max_depth": 1},
        {"url": f"https://x.com/search?q={query_param}", "max_pages": 4, "max_depth": 0},
        {"url": f"https://twitter.com/search?q={query_param}", "max_pages": 4, "max_depth": 0},
    ])

    if query_mode == "news":
        targeted_requests.extend(
            [
                {"url": f"https://www.bbc.co.uk/search?q={query_param}", "max_pages": 12, "max_depth": 1},
                {"url": f"https://www.theverge.com/search?q={query_param}", "max_pages": 8, "max_depth": 1},
                {"url": f"https://arstechnica.com/search/?q={query_param}", "max_pages": 8, "max_depth": 1},
                {"url": f"https://newsroom.olympics.com/search/results/?q={query_param}", "max_pages": 8, "max_depth": 1},
            ]
        )
    elif query_mode == "howto":
        targeted_requests.extend(
            [
                {"url": f"https://www.wikihow.com/wikiHowTo?search={query_param}", "max_pages": 10, "max_depth": 1},
                {"url": f"https://stackoverflow.com/search?q={query_param}", "max_pages": 10, "max_depth": 1},
                {"url": f"https://www.youtube.com/results?search_query={query_param}", "max_pages": 6, "max_depth": 1},
            ]
        )
    else:
        targeted_requests.extend(
            [
                {"url": f"https://www.allmusic.com/search/all/{query_param}", "max_pages": 6, "max_depth": 1},
                {"url": f"https://www.allmovie.com/search/all/{query_param}", "max_pages": 6, "max_depth": 1},
                {"url": f"https://www.vogue.com/search?q={query_param}", "max_pages": 6, "max_depth": 1},
            ]
        )

    seen_urls = set()
    for target in targeted_requests:
        url = target["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        try:
            same_domain_only = bool(target.get("same_domain_only", False))
            allowed_hosts = target.get("allowed_hosts")
            if allowed_hosts is None and not same_domain_only:
                allowed_hosts = DISCOVERY_HOSTS
            ENGINE.crawl(
                seed_url=url,
                max_pages=target["max_pages"],
                max_depth=target["max_depth"],
                same_domain_only=same_domain_only,
                allowed_hosts=allowed_hosts,
            )
        except Exception:
            continue


def start_query_boost(query: str):
    cleaned = (query or "").strip().lower()
    if not cleaned:
        return

    with QUERY_BOOST_STATE["lock"]:
        if cleaned in QUERY_BOOST_STATE["running"]:
            return
        QUERY_BOOST_STATE["running"].add(cleaned)

    def worker():
        try:
            boost_query_specific_results(cleaned)
        finally:
            with QUERY_BOOST_STATE["lock"]:
                QUERY_BOOST_STATE["running"].discard(cleaned)

    threading.Thread(target=worker, name=f"nesat-query-{cleaned[:20]}", daemon=True).start()


# ═══════════════════════════════════════════════════════════════════
# BOOTSTRAP
# ═══════════════════════════════════════════════════════════════════

def maybe_bootstrap_index(force: bool = False) -> tuple[str, str]:
    now = time.time()
    page_count = ENGINE.get_stats()["page_count"]
    if page_count >= BOOTSTRAP_TARGET_PAGES and not force:
        return "", ""

    if not force and now - BOOTSTRAP_STATE["last_run"] < BOOTSTRAP_COOLDOWN_SECONDS:
        return BOOTSTRAP_STATE["last_message"], BOOTSTRAP_STATE["last_error"]

    BOOTSTRAP_STATE["last_run"] = now
    BOOTSTRAP_STATE["last_error"] = ""

    try:
        if force:
            ENGINE.clear_index()

        before_count = ENGINE.get_stats()["page_count"]
        for query in WIKIPEDIA_BOOTSTRAP_QUERIES:
            try:
                index_wikipedia_results(query, limit=10)
            except Exception:
                continue
        seeded_sources = 0
        crawl_errors = []
        for profile in DEFAULT_SOURCE_PROFILES:
            current_count = ENGINE.get_stats()["page_count"]
            if current_count >= BOOTSTRAP_TARGET_PAGES:
                break

            source_before = current_count
            for starter_url in profile.get("starter_urls", []):
                current_count = ENGINE.get_stats()["page_count"]
                if current_count >= BOOTSTRAP_TARGET_PAGES:
                    break
                try:
                    ENGINE.crawl(
                        seed_url=starter_url,
                        max_pages=1,
                        max_depth=0,
                        same_domain_only=True,
                        allowed_hosts=DISCOVERY_HOSTS,
                    )
                except Exception as exc:
                    crawl_errors.append(f'{profile["name"]}: {exc}')

            for seed in profile["seeds"]:
                current_count = ENGINE.get_stats()["page_count"]
                if current_count >= BOOTSTRAP_TARGET_PAGES:
                    break
                remaining = max(1, BOOTSTRAP_TARGET_PAGES - current_count)
                crawl_budget = max(profile["pages_per_seed"] * 10, 40)
                try:
                    ENGINE.crawl(
                        seed_url=seed,
                        max_pages=min(crawl_budget, remaining),
                        max_depth=profile["depth"],
                        same_domain_only=False,
                        allowed_hosts=DISCOVERY_HOSTS,
                    )
                except Exception as exc:
                    crawl_errors.append(f'{profile["name"]}: {exc}')

            source_after = ENGINE.get_stats()["page_count"]
            if source_after > source_before:
                seeded_sources += 1

        after_count = ENGINE.get_stats()["page_count"]
        added_pages = max(0, after_count - before_count)
        message = (
            ("Rebuilt internet index. " if force else "Automatic internet index ready. ")
            +
            f"Added {added_pages} pages across {seeded_sources} source groups."
        )
        BOOTSTRAP_STATE["last_message"] = message
        BOOTSTRAP_STATE["last_error"] = "; ".join(crawl_errors[:4])
        return message, ""
    except Exception as exc:
        BOOTSTRAP_STATE["last_error"] = str(exc)
        return "", str(exc)


def start_bootstrap_index(force: bool = False) -> tuple[str, str]:
    page_count = ENGINE.get_stats()["page_count"]
    if page_count >= BOOTSTRAP_TARGET_PAGES and not force:
        return "", ""

    if BOOTSTRAP_STATE["running"]:
        return BOOTSTRAP_STATE["last_message"], BOOTSTRAP_STATE["last_error"]

    now = time.time()
    if not force and now - BOOTSTRAP_STATE["last_run"] < BOOTSTRAP_COOLDOWN_SECONDS:
        return BOOTSTRAP_STATE["last_message"], BOOTSTRAP_STATE["last_error"]

    BOOTSTRAP_STATE["running"] = True
    BOOTSTRAP_STATE["last_run"] = now
    BOOTSTRAP_STATE["last_message"] = "Building web index in the background. Search is available while pages are being added."
    BOOTSTRAP_STATE["last_error"] = ""

    def worker():
        message, error = maybe_bootstrap_index(force=force)
        if message:
            BOOTSTRAP_STATE["last_message"] = message
        if error:
            BOOTSTRAP_STATE["last_error"] = error
        BOOTSTRAP_STATE["running"] = False

    thread = threading.Thread(target=worker, name="nesat-bootstrap", daemon=True)
    BOOTSTRAP_STATE["thread"] = thread
    thread.start()
    return BOOTSTRAP_STATE["last_message"], ""


# ═══════════════════════════════════════════════════════════════════
# PAGE RENDERING
# ═══════════════════════════════════════════════════════════════════

def render_home(message="", error="", force_bootstrap=False) -> str:
    stats = ENGINE.get_stats()
    auto_message = ""
    auto_error = ""
    if force_bootstrap:
        auto_message, auto_error = start_bootstrap_index(force=force_bootstrap)
        stats = ENGINE.get_stats()

    template = load_template("index.template.html")
    values = {
        "MESSAGE_PANEL": render_message_panel(message or auto_message, error or auto_error),
        "INDEXED_PAGES": str(stats["page_count"]),
        "TRACKED_TERMS": str(stats["term_count"]),
        "LAST_CRAWL": escape(stats["latest_crawl"]),
        "SOURCE_BREAKDOWN": render_source_breakdown(),
        "BBC_NEWS": render_bbc_news_placeholder(),
    }
    return fill_template(template, values)


def render_results_page(
    query="",
    page: int = 1,
    sort_mode: str = "relevant",
    message="",
    error="",
    force_bootstrap=False,
) -> str:
    stats = ENGINE.get_stats()
    auto_message = ""
    auto_error = ""
    query_mode = classify_query(query)
    if force_bootstrap:
        auto_message, auto_error = start_bootstrap_index(force=force_bootstrap)
        stats = ENGINE.get_stats()

    search_start = time.time()
    results = []
    total_count = 0

    if query.strip():
        results, total_count = search_web_and_index(
            query, page=page, per_page=RESULTS_PER_PAGE, sort_mode=sort_mode
        )

    search_time = time.time() - search_start

    # Suggestion
    suggestion = ""
    # Building the local spelling vocabulary is relatively expensive. Only do
    # it when both the web and local index genuinely returned nothing.
    if query.strip() and not results:
        suggested_query = ENGINE.suggest_query(query)
        if suggested_query and suggested_query.lower() != query.strip().lower():
            suggestion_url = "results.html?" + urlencode({"q": suggested_query})
            suggestion = (
                f'Did you mean <a href="{escape(suggestion_url)}">{escape(suggested_query)}</a>?'
            )

    short_query = bool(query.strip()) and not results and not any(len(term) >= 3 for term in query.split())

    template = load_template("results.template.html")
    query_value = escape(query)

    # Summary text
    if short_query:
        query_summary = "Use at least 3 letters for search terms."
    elif query.strip():
        query_summary = f'About {total_count} result{"s" if total_count != 1 else ""} ({search_time:.2f} seconds)'
    else:
        query_summary = "Type a search and press Enter."

    # Sort hidden input
    sort_hidden = ""
    if sort_mode != "relevant":
        sort_hidden = f'<input type="hidden" name="sort" value="{escape(sort_mode)}">'

    # Result content
    if short_query:
        result_content = '<section class="empty-state"><h2>Query too short</h2><p>Use at least 3 letters so Nesat can find relevant results.</p></section>'
    elif query.strip():
        if sort_mode == "images":
            result_content = '<div class="images-grid" style="display:grid; grid-template-columns:repeat(auto-fill, minmax(200px, 1fr)); gap:15px; margin-top:20px;">'
            for i, r in enumerate(results):
                seed = abs(hash(r.url)) % 100000
                img_url = f"https://picsum.photos/seed/{seed}/200/200"
                result_content += f'<a href="{escape(r.url)}" target="_blank" style="text-decoration:none;"><article class="window" style="padding:4px;"><div class="window-body" style="margin:0;"><img src="{img_url}" alt="" style="width:100%; height:auto; display:block;"><p class="result-link" style="font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:4px;">{escape(r.url)}</p></div></article></a>'
            result_content += '</div>'
        else:
            result_content = render_result_cards(query, results)
    else:
        result_content = '<section class="empty-state"><h2>Ready to search</h2><p>Type a query above and press Enter.</p></section>'

    values = {
        "PAGE_TITLE": (
            f'"{escape(query)}" - Nesat Search' if query.strip() else "Nesat Search Results"
        ),
        "MESSAGE_PANEL": render_message_panel(message or auto_message, error or auto_error),
        "QUERY_VALUE": query_value,
        "SORT_HIDDEN": sort_hidden,
        "SORT_CHIPS": render_sort_chips(sort_mode, query) if query.strip() else "",
        "QUERY_SUMMARY": query_summary,
        "QUERY_SUGGESTION": suggestion,
        "RESULT_CONTENT": result_content,
        "PAGINATION": render_pagination(page, total_count, query, sort_mode) if query.strip() and total_count > RESULTS_PER_PAGE else "",
        "INDEXED_PAGES": str(stats["page_count"]),
        "TRACKED_TERMS": str(stats["term_count"]),
        "LAST_CRAWL": escape(stats["latest_crawl"]),
        "SOURCE_BREAKDOWN": render_source_breakdown(),
        "BBC_NEWS": render_bbc_news_placeholder(),
    }
    return fill_template(template, values)


# ═══════════════════════════════════════════════════════════════════
# HTTP SERVER
# ═══════════════════════════════════════════════════════════════════

class SearchHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if parsed.path in {"", "/", "/index.html"}:
            force_bootstrap = params.get("refresh_index", ["0"])[0] == "1"
            self._send_html(render_home(force_bootstrap=force_bootstrap))
            return

        if parsed.path in {"/results", "/results.html"}:
            query = params.get("q", [""])[0].strip()
            page = max(1, min(999, int(params.get("page", ["1"])[0] or "1")))
            sort_mode = params.get("sort", ["relevant"])[0].strip()
            if sort_mode not in {"relevant", "popular", "rated", "primer", "images"}:
                sort_mode = "relevant"
            force_bootstrap = params.get("refresh_index", ["0"])[0] == "1"
            self._send_html(
                render_results_page(
                    query=query,
                    page=page,
                    sort_mode=sort_mode,
                    force_bootstrap=force_bootstrap,
                )
            )
            return

        # "I'm Feeling Lucky" — redirect to first result
        if parsed.path == "/search":
            query = params.get("q", [""])[0].strip()
            if query:
                results, _ = search_web_and_index(
                    query, page=1, per_page=1, sort_mode="relevant"
                )
                if results:
                    self.send_response(302)
                    self.send_header("Location", results[0].url)
                    self.end_headers()
                    return
            # Fallback to results page
            self.send_response(302)
            self.send_header("Location", f"/results.html?{urlencode({'q': query})}")
            self.end_headers()
            return

        if parsed.path == "/status.json":
            self._send_json(self._build_status_payload())
            return

        if parsed.path == "/news-fragment":
            start_bbc_news_refresh(force=False)
            self._send_html_fragment(render_bbc_news())
            return

        if parsed.path.startswith("/static/"):
            self._send_file(STATIC_DIR / parsed.path.removeprefix("/static/"))
            return

        if parsed.path.startswith("/imageres/"):
            self._send_file(IMAGE_DIR / parsed.path.removeprefix("/imageres/"))
            return

        self.send_error(404, "Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/crawl":
            self.send_error(404, "Not found")
            return

        body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8")
        params = parse_qs(body)
        return_to = params.get("return_to", ["home"])[0]

        try:
            message, error = maybe_bootstrap_index(force=True)
            if return_to == "results":
                query = params.get("q", [""])[0].strip()
                self._send_html(render_results_page(query=query, message=message, error=error))
            else:
                self._send_html(render_home(message=message, error=error))
        except Exception as exc:
            if return_to == "results":
                query = params.get("q", [""])[0].strip()
                self._send_html(render_results_page(query=query, error=str(exc)), status_code=400)
            else:
                self._send_html(render_home(error=str(exc)), status_code=400)

    def log_message(self, format, *args):
        return

    def _send_html(self, html, status_code=200):
        payload = html.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_html_fragment(self, html, status_code=200):
        payload = html.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, payload_object, status_code=200):
        payload = json.dumps(payload_object).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, file_path: Path):
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, "Not found")
            return
        payload = file_path.read_bytes()
        content_type, _ = mimetypes.guess_type(str(file_path))
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _build_status_payload(self):
        stats = ENGINE.get_stats()
        return {
            "code_version": CODE_VERSION,
            "page_count": stats["page_count"],
            "term_count": stats["term_count"],
            "latest_crawl": stats["latest_crawl"],
            "index_running": BOOTSTRAP_STATE["running"],
            "index_message": BOOTSTRAP_STATE["last_message"],
            "index_error": BOOTSTRAP_STATE["last_error"],
        }


def create_server(host=DEFAULT_HOST, port=DEFAULT_PORT):
    return ThreadingHTTPServer((host, port), SearchHandler)


def run_server(host=DEFAULT_HOST, port=DEFAULT_PORT, open_browser=False):
    server = create_server(host, port)
    url = f"http://{host}:{port}/index.html"
    if not BOOTSTRAP_STATE["scheduled"]:
        BOOTSTRAP_STATE["scheduled"] = True
        if ENGINE.get_stats()["page_count"] <= 25:
            threading.Timer(8.0, lambda: start_bootstrap_index(force=False)).start()
        threading.Timer(5.0, lambda: start_bbc_news_refresh(force=False)).start()
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="NESAT 2000 search engine")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args()

    if not args.open_browser:
        print(f"Nesat Search is running at http://{args.host}:{args.port}/index.html")
        print("Press Ctrl+C to stop the server.")

    try:
        run_server(args.host, args.port, open_browser=args.open_browser)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
