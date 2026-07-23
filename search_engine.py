import difflib
import math
import re
import sqlite3
import time
import random
import threading
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib import parse, request, robotparser


STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "he",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "was",
    "were",
    "will",
    "with",
}

GREETING_TERMS = {
    "hi",
    "hello",
    "hey",
    "there",
    "thanks",
    "thank",
    "please",
    "yo",
    "sup",
}

REFERENCE_HOSTS = {
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
    "www.python.org",
    "docs.python.org",
}

NEWS_HOSTS = {
    "www.bbc.com",
    "arstechnica.com",
    "www.theverge.com",
    "newsroom.olympics.com",
}

HOWTO_HOSTS = {
    "www.wikihow.com",
    "stackoverflow.com",
    "wikipedia.org/wiki/Category:How-to_guides",
}

SOCIAL_HOSTS = {
    "old.reddit.com",
    "www.reddit.com",
    "www.youtube.com",
    "x.com",
    "twitter.com",
    "medium.com",
    "dev.to",
    "github.com",
    "www.tumblr.com",
    "www.fandom.com",
    "aesthetics.fandom.com",
    "frutigeraero.fandom.com",
}

NEWS_QUERY_TERMS = {
    "news",
    "latest",
    "today",
    "breaking",
    "update",
    "updates",
    "headline",
    "headlines",
    "war",
    "election",
    "weather",
    "score",
    "scores",
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

# ── High-trust domains ───────────────────────────────────────────────
HIGH_TRUST_DOMAINS = {
    "en.wikipedia.org": 0.95,
    "www.britannica.com": 0.92,
    "plato.stanford.edu": 0.93,
    "www.loc.gov": 0.94,
    "www.gutenberg.org": 0.76,
    "www.smithsonianmag.com": 0.88,
    "medlineplus.gov": 0.91,
    "developer.mozilla.org": 0.89,
    "docs.python.org": 0.88,
    "www.python.org": 0.86,
    "www.nasa.gov": 0.93,
    "stackoverflow.com": 0.84,
    "en.wiktionary.org": 0.85,
    "en.wikivoyage.org": 0.83,
    "www.bbc.com": 0.87,
    "arstechnica.com": 0.82,
    "www.theverge.com": 0.80,
    "github.com": 0.83,
    "news.ycombinator.com": 0.79,
    "www.nationalgeographic.com": 0.85,
    "www.nationalgeographic.com": 0.85,
}

# ── Low-trust / spam domains ────────────────────────────────────────
LOW_TRUST_PATTERNS = [
    r"^(www\.)?(free|cheap|best|top)\d*-",
    r"\.(tk|ml|ga|cf|gq)$",
    r"(clickbait|spam|ads|casino|poker|viagra|pharma)",
]

# ── Academic / Primer 1989 domains ───────────────────────────────────
PRIMER_1989_DOMAINS = {
    "en.wikipedia.org",
    "www.britannica.com",
    "plato.stanford.edu",
    "www.loc.gov",
    "www.gutenberg.org",
    "www.smithsonianmag.com",
    "medlineplus.gov",
    "www.nasa.gov",
    "en.wiktionary.org",
    "en.wikivoyage.org",
    "docs.python.org",
    "developer.mozilla.org",
}

# ── User-Agent rotation pool ────────────────────────────────────────
USER_AGENT_POOL = [
    "NESATBot/2000 (+http://127.0.0.1)",
    "Mozilla/5.0 (compatible; NESATBot/2.0; +http://127.0.0.1)",
    "NESATCrawler/2.0 (Search Engine; +http://127.0.0.1)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) NESATBot/2.0",
    "NESATSpider/2.0 (+http://127.0.0.1)",
    "Mozilla/5.0 (compatible; NESATIndexer/2.0)",
]


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    score: int
    matched_terms: int
    engagement_score: int
    term_frequency: int
    inbound_links: int
    referring_hosts: int
    authority_score: float
    star_rating: float = 0.0
    domain_trust: float = 0.5
    crawl_timestamp: float = 0.0
    meta_description: str = ""


@dataclass
class CrawlReport:
    seed_url: str
    indexed_pages: int
    added_pages: int
    updated_pages: int
    skipped_pages: int
    errors: list[str]


class DocumentParser(HTMLParser):
    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "header",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "section",
        "table",
        "tr",
        "ul",
    }

    def __init__(self, base_url: str):
        super().__init__()
        self.base_url = base_url
        self.links = []
        self.title_parts = []
        self.text_parts = []
        self.skip_depth = 0
        self.in_title = False
        self.canonical_url = None
        self.meta_description = ""

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
            return

        if self.skip_depth > 0:
            return

        if tag == "title":
            self.in_title = True
            return

        attr_dict = dict(attrs)

        if tag == "link" and attr_dict.get("rel", "").lower() == "canonical":
            href = attr_dict.get("href", "").strip()
            if href:
                self.canonical_url = parse.urljoin(self.base_url, href)

        if tag == "meta":
            name = attr_dict.get("name", "").lower()
            if name == "description":
                self.meta_description = attr_dict.get("content", "").strip()

        if tag == "a":
            href = attr_dict.get("href", "").strip()
            if href:
                self.links.append(parse.urljoin(self.base_url, href))

        if tag in self.BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.skip_depth = max(0, self.skip_depth - 1)
            return

        if self.skip_depth > 0:
            return

        if tag == "title":
            self.in_title = False
            return

        if tag in self.BLOCK_TAGS:
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth > 0:
            return

        cleaned = " ".join(data.split())
        if not cleaned:
            return

        if self.in_title:
            self.title_parts.append(cleaned)
        else:
            self.text_parts.append(cleaned)

    def get_title(self) -> str:
        title = " ".join(self.title_parts).strip()
        return title or "Untitled page"

    def get_text(self) -> str:
        joined = " ".join(self.text_parts)
        joined = re.sub(r"\s*\n\s*", "\n", joined)
        joined = re.sub(r"\n{2,}", "\n\n", joined)
        return joined.strip()


class SearchEngine:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_agent = "NESATBot/2000 (+http://127.0.0.1)"
        self._domain_delay_lock = threading.Lock()
        self._domain_last_access = {}
        self._crawl_delay = 1.0
        self._ensure_schema()

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _ensure_schema(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    snippet TEXT NOT NULL,
                    engagement_score INTEGER NOT NULL DEFAULT 0,
                    authority_score REAL NOT NULL DEFAULT 0,
                    crawled_at TEXT NOT NULL,
                    meta_description TEXT NOT NULL DEFAULT '',
                    page_load_speed REAL NOT NULL DEFAULT 0,
                    domain_trust_score REAL NOT NULL DEFAULT 0.5,
                    star_rating REAL NOT NULL DEFAULT 0,
                    crawl_timestamp REAL NOT NULL DEFAULT 0
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(pages)").fetchall()
            }
            if "engagement_score" not in columns:
                connection.execute(
                    "ALTER TABLE pages ADD COLUMN engagement_score INTEGER NOT NULL DEFAULT 0"
                )
            if "authority_score" not in columns:
                connection.execute(
                    "ALTER TABLE pages ADD COLUMN authority_score REAL NOT NULL DEFAULT 0"
                )
            if "meta_description" not in columns:
                connection.execute(
                    "ALTER TABLE pages ADD COLUMN meta_description TEXT NOT NULL DEFAULT ''"
                )
            if "page_load_speed" not in columns:
                connection.execute(
                    "ALTER TABLE pages ADD COLUMN page_load_speed REAL NOT NULL DEFAULT 0"
                )
            if "domain_trust_score" not in columns:
                connection.execute(
                    "ALTER TABLE pages ADD COLUMN domain_trust_score REAL NOT NULL DEFAULT 0.5"
                )
            if "star_rating" not in columns:
                connection.execute(
                    "ALTER TABLE pages ADD COLUMN star_rating REAL NOT NULL DEFAULT 0"
                )
            if "crawl_timestamp" not in columns:
                connection.execute(
                    "ALTER TABLE pages ADD COLUMN crawl_timestamp REAL NOT NULL DEFAULT 0"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS page_terms (
                    page_id INTEGER NOT NULL,
                    term TEXT NOT NULL,
                    frequency INTEGER NOT NULL,
                    PRIMARY KEY (page_id, term),
                    FOREIGN KEY (page_id) REFERENCES pages(id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_page_terms_term ON page_terms(term)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS page_links (
                    source_page_id INTEGER NOT NULL,
                    source_host TEXT NOT NULL,
                    target_url TEXT NOT NULL,
                    target_host TEXT NOT NULL,
                    PRIMARY KEY (source_page_id, target_url),
                    FOREIGN KEY (source_page_id) REFERENCES pages(id)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_page_links_target_url ON page_links(target_url)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_pages_crawled_at ON pages(crawled_at DESC)"
            )

    # ── Stats & Utilities ────────────────────────────────────────────

    def get_stats(self) -> dict:
        with self._connect() as connection:
            page_count = connection.execute(
                "SELECT COUNT(*) AS count FROM pages"
            ).fetchone()["count"]
            term_count = connection.execute(
                "SELECT COUNT(*) AS count FROM page_terms"
            ).fetchone()["count"]
            latest_row = connection.execute(
                "SELECT crawled_at FROM pages ORDER BY crawled_at DESC LIMIT 1"
            ).fetchone()
        return {
            "page_count": page_count,
            "term_count": term_count,
            "latest_crawl": latest_row["crawled_at"] if latest_row else "Never",
        }

    def recent_pages(self, limit: int = 8) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT title, url, crawled_at
                FROM pages
                ORDER BY crawled_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def top_hosts(self, limit: int = 8) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    substr(
                        replace(replace(url, 'https://', ''), 'http://', ''),
                        1,
                        CASE
                            WHEN instr(replace(replace(url, 'https://', ''), 'http://', ''), '/') = 0
                                THEN length(replace(replace(url, 'https://', ''), 'http://', ''))
                            ELSE instr(replace(replace(url, 'https://', ''), 'http://', ''), '/') - 1
                        END
                    ) AS host,
                    COUNT(*) AS page_count
                FROM pages
                GROUP BY host
                ORDER BY page_count DESC, host ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_index(self):
        with self._connect() as connection:
            connection.execute("DELETE FROM page_links")
            connection.execute("DELETE FROM page_terms")
            connection.execute("DELETE FROM pages")

    # ── Domain trust scoring ─────────────────────────────────────────

    def _compute_domain_trust(self, host: str) -> float:
        host_lower = host.lower()
        if host_lower in HIGH_TRUST_DOMAINS:
            return HIGH_TRUST_DOMAINS[host_lower]
        for pattern in LOW_TRUST_PATTERNS:
            if re.search(pattern, host_lower):
                return 0.1
        if host_lower.endswith(".edu"):
            return 0.88
        if host_lower.endswith(".gov"):
            return 0.90
        if host_lower.endswith(".org"):
            return 0.65
        return 0.5

    # ── Star rating computation ──────────────────────────────────────

    def _compute_star_rating(
        self,
        engagement_score: int,
        authority_score: float,
        domain_trust: float,
        inbound_links: int,
        content_length: int,
    ) -> float:
        score = 0.0
        score += min(domain_trust * 2.0, 2.0)
        if engagement_score > 0:
            score += min(math.log10(engagement_score + 1) * 0.5, 1.0)
        score += min(authority_score * 10, 1.0)
        if inbound_links > 0:
            score += min(math.log10(inbound_links + 1) * 0.3, 0.5)
        if content_length > 500:
            score += 0.5
        return round(min(score, 5.0), 1)

    # ── Indexing ─────────────────────────────────────────────────────

    def index_document(
        self,
        url: str,
        title: str,
        content: str,
        engagement_score: int = 0,
        outgoing_links: list[str] | None = None,
        meta_description: str = "",
        page_load_speed: float = 0.0,
    ) -> bool:
        normalized_url = self.normalize_url(url)
        if not normalized_url:
            raise ValueError("Please enter a valid http or https URL.")

        clean_title = self._clean_title(title, normalized_url)
        clean_content = " ".join((content or "").split()).strip()
        if not clean_content:
            raise ValueError("Content is required for indexing.")

        host = parse.urlparse(normalized_url).netloc.lower()
        domain_trust = self._compute_domain_trust(host)
        snippet = self._build_snippet(clean_content, [])
        return self._store_page(
            normalized_url,
            clean_title,
            clean_content,
            snippet,
            int(engagement_score or 0),
            outgoing_links or [],
            meta_description=meta_description,
            page_load_speed=page_load_speed,
            domain_trust_score=domain_trust,
        )

    # ── Search (original, kept for compatibility) ────────────────────

    def search(self, query: str, limit: int = 15) -> list[SearchResult]:
        results, _ = self.search_paginated(query, page=1, per_page=limit, sort_mode="relevant")
        return results

    # ── Paginated Search with Sort Modes ─────────────────────────────

    def search_paginated(
        self,
        query: str,
        page: int = 1,
        per_page: int = 10,
        sort_mode: str = "relevant",
    ) -> tuple[list[SearchResult], int]:
        raw_query = (query or "").strip()
        raw_terms = self._tokenize(raw_query)
        if raw_terms and all(term in GREETING_TERMS for term in raw_terms):
            return [], 0
        terms = [
            term
            for term in self._tokenize(query)
            if term not in STOP_WORDS and len(term) >= 3
        ]
        if not terms:
            return [], 0

        placeholders = ",".join("?" for _ in terms)
        sql = f"""
            SELECT
                p.title,
                p.url,
                p.content,
                p.snippet,
                p.engagement_score,
                p.authority_score,
                p.meta_description,
                p.domain_trust_score,
                p.star_rating,
                p.crawl_timestamp,
                COALESCE(ls.inbound_links, 0) AS inbound_links,
                COALESCE(ls.referring_hosts, 0) AS referring_hosts,
                SUM(pt.frequency) AS term_score,
                MAX(pt.frequency) AS max_term_frequency,
                COUNT(DISTINCT pt.term) AS matched_terms
            FROM page_terms AS pt
            JOIN pages AS p ON p.id = pt.page_id
            LEFT JOIN (
                SELECT
                    target_url,
                    COUNT(*) AS inbound_links,
                    COUNT(DISTINCT source_host) AS referring_hosts
                FROM page_links
                GROUP BY target_url
            ) AS ls ON ls.target_url = p.url
            WHERE pt.term IN ({placeholders})
            GROUP BY p.id
            LIMIT 5000
        """

        query_lower = query.lower()
        query_phrase = " ".join(terms)
        query_mode = self._classify_query_mode(raw_query, terms)
        short_single_term = len(terms) == 1 and len(terms[0]) <= 4

        # Get total document count for IDF
        with self._connect() as connection:
            total_docs = connection.execute("SELECT COUNT(*) AS c FROM pages").fetchone()["c"]
            # Get document frequencies for IDF
            idf_sql = f"SELECT term, COUNT(DISTINCT page_id) AS df FROM page_terms WHERE term IN ({placeholders}) GROUP BY term"
            idf_rows = connection.execute(idf_sql, terms).fetchall()
            doc_freqs = {row["term"]: row["df"] for row in idf_rows}
            rows = connection.execute(sql, terms).fetchall()

        all_results = []
        for row in rows:
            title = row["title"] or "Untitled page"
            content = row["content"] or ""
            content_lower = content.lower()
            term_frequency = int(row["term_score"] or 0)
            max_term_frequency = int(row["max_term_frequency"] or 0)
            matched_terms = int(row["matched_terms"] or 0)
            inbound_links = int(row["inbound_links"] or 0)
            referring_hosts = int(row["referring_hosts"] or 0)
            authority_score = float(row["authority_score"] or 0.0)
            domain_trust = float(row["domain_trust_score"] or 0.5)
            star_rating = float(row["star_rating"] or 0.0)
            crawl_ts = float(row["crawl_timestamp"] or 0.0)
            meta_desc = row["meta_description"] or ""
            engagement_score = int(row["engagement_score"] or 0)
            content_token_count = max(1, len(self._tokenize(content)))
            term_density = int((term_frequency * 1000) / content_token_count)
            title_lower = title.lower()
            url_lower = row["url"].lower()
            host = parse.urlparse(row["url"]).netloc.lower()
            title_term_hits = sum(
                1 for term in terms if self._contains_whole_term(title_lower, term)
            )
            url_term_hits = sum(
                1
                for term in terms
                if (
                    f"/{term}" in url_lower
                    or f"={term}" in url_lower
                    or f"_{term}" in url_lower
                    or f"-{term}" in url_lower
                )
            )
            phrase_in_title = bool(
                query_phrase and self._contains_whole_phrase(title_lower, query_phrase)
            )
            phrase_in_url = bool(
                query_phrase and query_phrase in url_lower.replace("_", " ").replace("-", " ")
            )
            all_terms_in_title = all(
                self._contains_whole_term(title_lower, term) for term in terms
            )

            # ── TF-IDF Score ─────────────────────────────────────────
            tfidf_score = 0.0
            for term in terms:
                tf = content_lower.count(term) / max(content_token_count, 1)
                df = doc_freqs.get(term, 1)
                idf = math.log((total_docs + 1) / (df + 1)) + 1
                tfidf_score += tf * idf

            # ── Relevance Score (classic heuristic + TF-IDF) ─────────
            score = (
                int(tfidf_score * 5000)
                + term_frequency * 180
                + matched_terms * 220
                + title_term_hits * 900
                + url_term_hits * 700
                + term_density * 45
                + min(inbound_links, 40) * 90
                + min(referring_hosts, 10) * 320
                + int(authority_score * 450000)
            )
            popularity_boost = min(engagement_score, 5000)
            exact_title_or_url_match = False
            official_match_score = 0

            if query_lower and query_lower in title_lower:
                score += 1200
            if query_lower and query_lower in content_lower:
                score += 220
            if all_terms_in_title:
                score += 1200
            if phrase_in_title:
                exact_title_or_url_match = True
                score += 7000
            if phrase_in_url:
                exact_title_or_url_match = True
                score += 5200
            if query_phrase and self._contains_whole_phrase(content_lower, query_phrase):
                score += 700
            if len(terms) == 1 and self._contains_whole_term(title_lower, terms[0]):
                exact_title_or_url_match = True
                score += 900
            if len(terms) == 1 and (
                f"/{terms[0]}" in url_lower
                or f"={terms[0]}" in url_lower
                or f"_{terms[0]}" in url_lower
                or f"-{terms[0]}" in url_lower
            ):
                exact_title_or_url_match = True
                score += 1200
            if len(terms) == 1 and (
                title_lower == terms[0]
                or title_lower.startswith(terms[0] + " ")
                or title_lower.startswith(terms[0] + " -")
                or title_lower.startswith(terms[0] + ":")
            ):
                score += 1600
            if len(terms) == 1:
                official_match_score = self._score_official_host_match(
                    host=host,
                    url=row["url"],
                    term=terms[0],
                    domain_trust=domain_trust,
                    authority_score=authority_score,
                    engagement_score=engagement_score,
                )
                if official_match_score:
                    exact_title_or_url_match = True
                    score += official_match_score

            generic_signals = [
                "/category:",
                "/category/",
                "category:",
                "quizzes",
                "quiz",
                "trending",
                "popular",
                "main page",
                "main_page",
                "search",
            ]
            if any(signal in title_lower or signal in url_lower for signal in generic_signals):
                score -= 500
            score += popularity_boost * 6
            if popularity_boost >= 250:
                score += 1500
            if popularity_boost >= 1000:
                score += 2500

            if query_mode == "reference":
                if host in REFERENCE_HOSTS:
                    score += 2200
                if host == "en.wikipedia.org":
                    score += 2500
                    if phrase_in_title or all_terms_in_title:
                        score += 3500
                if host in SOCIAL_HOSTS:
                    score += 2100
                if host in NEWS_HOSTS:
                    score -= 2400
                if host in HOWTO_HOSTS:
                    score -= 1800
            elif query_mode == "news":
                if host in NEWS_HOSTS:
                    score += 2200
                elif host in REFERENCE_HOSTS:
                    score += 400
            elif query_mode == "howto":
                if host in HOWTO_HOSTS:
                    score += 2200
                elif host in REFERENCE_HOSTS:
                    score += 300

            if len(terms) == 1 and not exact_title_or_url_match and term_frequency < 8:
                continue

            if len(terms) == 1 and max_term_frequency <= 1 and query_lower not in title_lower:
                continue

            if short_single_term and not exact_title_or_url_match and title_term_hits == 0 and url_term_hits == 0:
                if term_frequency < 20:
                    continue
                score -= 4500

            if len(terms) <= 3 and matched_terms < len(terms):
                continue

            if len(terms) > 3 and matched_terms < len(terms) - 1:
                continue

            if len(terms) > 1 and title_term_hits == 0 and url_term_hits == 0 and term_density < 2:
                continue

            if len(terms) > 1 and not phrase_in_title and not phrase_in_url and not all_terms_in_title:
                score -= 1800

            title = self._build_result_title(
                title=title,
                content=content,
                terms=terms,
                query_phrase=query_phrase,
                raw_query=raw_query,
                url=row["url"],
            )
            snippet = self._build_snippet(content, terms) or row["snippet"]

            # Recompute star_rating if it's 0
            if star_rating == 0.0:
                star_rating = self._compute_star_rating(
                    engagement_score, authority_score, domain_trust,
                    inbound_links, len(content),
                )

            all_results.append(
                SearchResult(
                    title=title,
                    url=row["url"],
                    snippet=snippet,
                    score=score,
                    matched_terms=matched_terms,
                    engagement_score=engagement_score,
                    term_frequency=term_frequency,
                    inbound_links=inbound_links,
                    referring_hosts=referring_hosts,
                    authority_score=authority_score,
                    star_rating=star_rating,
                    domain_trust=domain_trust,
                    crawl_timestamp=crawl_ts,
                    meta_description=meta_desc,
                )
            )

        # ── Apply sort mode ──────────────────────────────────────────
        all_results = self._apply_sort_mode(all_results, sort_mode, terms, query_phrase, query_mode)

        # ── Diversify results ────────────────────────────────────────
        diversified = self._diversify_results(all_results, terms, query_mode)

        total_count = len(diversified)
        page = max(1, min(page, 999))
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_results = diversified[start_idx:end_idx]

        return page_results, total_count

    def _apply_sort_mode(
        self,
        results: list[SearchResult],
        sort_mode: str,
        terms: list[str],
        query_phrase: str,
        query_mode: str,
    ) -> list[SearchResult]:
        if sort_mode == "popular":
            results.sort(
                key=lambda item: (
                    item.authority_score * 100000
                    + item.inbound_links * 500
                    + item.referring_hosts * 2000
                    + item.engagement_score * 10,
                    item.score,
                ),
                reverse=True,
            )
        elif sort_mode == "rated":
            now = time.time()
            def rated_key(item):
                freshness = 5000 if (now - item.crawl_timestamp) < 2592000 else 0
                return (
                    item.star_rating * 10000
                    + item.domain_trust * 50000
                    + item.engagement_score * 20
                    + freshness,
                    item.score,
                )
            results.sort(key=rated_key, reverse=True)
        elif sort_mode == "primer":
            def primer_key(item):
                host = parse.urlparse(item.url).netloc.lower()
                academic_boost = 3.0 if host in PRIMER_1989_DOMAINS else 1.0
                if host.endswith(".edu") or host.endswith(".gov"):
                    academic_boost = max(academic_boost, 2.5)
                social_penalty = 0.3 if host in SOCIAL_HOSTS else 1.0
                # Older pages favored (less timestamp = older = better for primer)
                age_boost = 1.0
                if item.crawl_timestamp > 0:
                    age_boost = 1.0 + (1.0 / max(1.0, item.crawl_timestamp / 1e9))
                link_diversity = min(item.referring_hosts, 20) * 500
                return (
                    item.score * academic_boost * social_penalty * age_boost
                    + link_diversity
                    + item.inbound_links * 200,
                    item.authority_score,
                )
            results.sort(key=primer_key, reverse=True)
        else:
            # Default: "relevant" — use the combined score
            results.sort(
                key=lambda item: (
                    item.score,
                    item.engagement_score,
                    item.authority_score,
                    item.inbound_links,
                    item.term_frequency,
                    item.matched_terms,
                    item.title.lower(),
                ),
                reverse=True,
            )

            # Strong phrase re-ranking for multi-term queries
            if len(terms) > 1:
                strong_phrase_results = []
                fallback_results = []
                normalized_phrase = query_phrase.lower()
                for item in results:
                    title_lower = item.title.lower()
                    url_lower = item.url.lower().replace("_", " ").replace("-", " ")
                    if (
                        self._contains_whole_phrase(title_lower, normalized_phrase)
                        or normalized_phrase in url_lower
                        or all(self._contains_whole_term(title_lower, term) for term in terms)
                    ):
                        strong_phrase_results.append(item)
                    else:
                        fallback_results.append(item)
                if strong_phrase_results:
                    strong_phrase_results.sort(
                        key=lambda item: (
                            item.engagement_score,
                            item.authority_score,
                            item.score,
                            item.inbound_links,
                            item.term_frequency,
                        ),
                        reverse=True,
                    )
                    fallback_results.sort(
                        key=lambda item: (
                            item.score,
                            item.engagement_score,
                            item.authority_score,
                        ),
                        reverse=True,
                    )
                    results = strong_phrase_results + fallback_results

            # Short single term title re-ranking
            short_single_term = len(terms) == 1 and len(terms[0]) <= 4
            if short_single_term:
                strong_title_results = []
                fallback_results = []
                for item in results:
                    title_lower = item.title.lower()
                    url_lower = item.url.lower().replace("_", " ").replace("-", " ")
                    if (
                        self._contains_whole_term(title_lower, terms[0])
                        or terms[0] in url_lower
                        or title_lower.startswith(terms[0] + " -")
                        or title_lower.startswith(terms[0] + ":")
                    ):
                        strong_title_results.append(item)
                    else:
                        fallback_results.append(item)
                if strong_title_results:
                    results = strong_title_results + fallback_results

            # Reference mode re-ranking
            if query_mode == "reference":
                reference_results = []
                social_results = []
                fallback_results = []
                penalized_results = []
                for item in results:
                    host = parse.urlparse(item.url).netloc.lower()
                    if host in REFERENCE_HOSTS:
                        reference_results.append(item)
                    elif host in SOCIAL_HOSTS:
                        social_results.append(item)
                    elif host in NEWS_HOSTS or host in HOWTO_HOSTS:
                        penalized_results.append(item)
                    else:
                        fallback_results.append(item)
                if reference_results:
                    results = reference_results + social_results + fallback_results + penalized_results

            if len(terms) == 1:
                official_results = []
                fallback_results = []
                for item in results:
                    host = parse.urlparse(item.url).netloc.lower()
                    official_score = self._score_official_host_match(
                        host=host,
                        url=item.url,
                        term=terms[0],
                        domain_trust=item.domain_trust,
                        authority_score=item.authority_score,
                        engagement_score=item.engagement_score,
                    )
                    if official_score >= 9000:
                        official_results.append((official_score, item))
                    else:
                        fallback_results.append(item)
                if official_results:
                    official_results.sort(
                        key=lambda pair: (
                            pair[0],
                            pair[1].engagement_score,
                            pair[1].authority_score,
                            pair[1].score,
                        ),
                        reverse=True,
                    )
                    results = [item for _, item in official_results] + fallback_results

        return results

    def _diversify_results(
        self,
        results: list[SearchResult],
        terms: list[str],
        query_mode: str,
    ) -> list[SearchResult]:
        diversified = []
        host_counts = {}
        single_term_query = len(terms) == 1
        default_host_cap = 2 if single_term_query else 3

        for item in results:
            host = parse.urlparse(item.url).netloc.lower()
            current_host_count = host_counts.get(host, 0)
            host_cap = default_host_cap
            if query_mode == "reference" and (host in NEWS_HOSTS or host in HOWTO_HOSTS):
                host_cap = 1
            if current_host_count >= host_cap:
                continue
            diversified.append(item)
            host_counts[host] = current_host_count + 1

        # Fill from overflow
        for item in results:
            if item in diversified:
                continue
            diversified.append(item)

        return diversified

    # ── Crawler ──────────────────────────────────────────────────────

    def _score_official_host_match(
        self,
        host: str,
        url: str,
        term: str,
        domain_trust: float,
        authority_score: float,
        engagement_score: int,
    ) -> int:
        clean_term = (term or "").strip().lower()
        clean_host = (host or "").split(":", 1)[0].strip().lower()
        if not clean_term or not clean_host:
            return 0

        labels = [label for label in clean_host.split(".") if label and label != "www"]
        if not labels or clean_term not in labels:
            return 0

        leftmost_label = labels[0]
        root_label = labels[-2] if len(labels) >= 2 else labels[0]
        parsed = parse.urlparse(url or "")
        path = parsed.path or "/"
        query = parsed.query or ""
        score = 3500

        if leftmost_label == clean_term:
            score += 6200
        if root_label == clean_term:
            score += 4800
        if len(labels) == 2 and root_label == clean_term:
            score += 1800

        if path in {"", "/"} and not query:
            score += 1800
        elif path.count("/") <= 1 and len(path.strip("/")) <= 18 and not query:
            score += 600
        else:
            score -= 1200

        if clean_host.endswith(".edu"):
            score += 3400
        elif clean_host.endswith(".gov"):
            score += 3600
        elif clean_host.endswith(".org"):
            score += 2200
        elif clean_host.endswith(".com"):
            score += 1600
        elif clean_host.endswith(".net"):
            score += 1200
        elif clean_host.endswith(".io"):
            score += 1100
        elif clean_host.endswith(".app") or clean_host.endswith(".dev"):
            score += 900
        elif clean_host.endswith(".onrender.com"):
            score += 700

        if leftmost_label == clean_term and clean_host.endswith(".edu"):
            score += 2600
        elif leftmost_label == clean_term and clean_host.endswith(".gov"):
            score += 2800

        score += int(max(0.0, min(domain_trust, 1.0)) * 7000)
        score += int(max(0.0, min(authority_score, 1.0)) * 4500)
        if engagement_score > 0:
            score += min(int(math.log10(engagement_score + 1) * 1200), 2500)

        return score

    def crawl(
        self,
        seed_url: str,
        max_pages: int = 20,
        max_depth: int = 1,
        same_domain_only: bool = True,
        allowed_hosts: set[str] | None = None,
        num_threads: int = 4,
    ) -> CrawlReport:
        normalized_seed = self.normalize_url(seed_url)
        if not normalized_seed:
            raise ValueError("Please enter a valid http or https URL.")

        max_pages = max(1, min(int(max_pages), 2000))
        max_depth = max(0, min(int(max_depth), 3))
        seed_host = parse.urlparse(normalized_seed).netloc

        queue = deque([(normalized_seed, 0)])
        queued = {normalized_seed}
        visited = set()
        robots_cache = {}
        robots_lock = threading.Lock()
        results_lock = threading.Lock()

        indexed_pages = 0
        added_pages = 0
        updated_pages = 0
        skipped_pages = 0
        errors = []
        child_urls = []  # (url, depth) pairs to add to queue

        def _process_url(current_url, depth):
            nonlocal indexed_pages, added_pages, updated_pages, skipped_pages

            with robots_lock:
                allowed = self._allowed_by_robots(current_url, robots_cache)
            if not allowed:
                with results_lock:
                    skipped_pages += 1
                return []

            # Per-domain crawl delay
            host = parse.urlparse(current_url).netloc.lower()
            self._wait_for_domain(host)

            try:
                start_time = time.time()
                final_url, html = self._fetch_html(current_url)
                load_speed = time.time() - start_time
                normalized_final = self.normalize_url(final_url) or current_url

                parser = DocumentParser(normalized_final)
                parser.feed(html)
                parser.close()

                # Canonical URL deduplication
                if parser.canonical_url:
                    canonical = self.normalize_url(parser.canonical_url)
                    if canonical and canonical != normalized_final:
                        normalized_final = canonical

                content = parser.get_text()
                if not content:
                    with results_lock:
                        skipped_pages += 1
                    return []

                title = self._clean_title(parser.get_title(), normalized_final)
                snippet = self._build_snippet(content, [])
                engagement_score = self._extract_engagement_score(title, content)
                outgoing_links = self._extract_indexable_links(parser.links)
                meta_desc = parser.meta_description
                final_host = parse.urlparse(normalized_final).netloc.lower()
                domain_trust = self._compute_domain_trust(final_host)

                created = self._store_page(
                    normalized_final,
                    title,
                    content,
                    snippet,
                    engagement_score,
                    outgoing_links,
                    meta_description=meta_desc,
                    page_load_speed=load_speed,
                    domain_trust_score=domain_trust,
                )

                with results_lock:
                    indexed_pages += 1
                    if created:
                        added_pages += 1
                    else:
                        updated_pages += 1

                if depth >= max_depth:
                    return []

                new_urls = []
                for link in parser.links:
                    normalized_link = self.normalize_url(link)
                    if not normalized_link:
                        continue
                    link_host = parse.urlparse(normalized_link).netloc.lower()
                    if same_domain_only and link_host != seed_host:
                        continue
                    if not same_domain_only and allowed_hosts and link_host not in allowed_hosts:
                        continue
                    new_urls.append((normalized_link, depth + 1))
                return new_urls

            except Exception as exc:
                with results_lock:
                    errors.append(f"{current_url} - {str(exc)}")
                return []

        # Process queue - use thread pool for fetching
        effective_threads = min(num_threads, max_pages)
        with ThreadPoolExecutor(max_workers=max(1, effective_threads)) as executor:
            while queue and indexed_pages < max_pages:
                # Submit a batch
                batch = []
                while queue and len(batch) < effective_threads and indexed_pages + len(batch) < max_pages:
                    current_url, depth = queue.popleft()
                    if current_url in visited:
                        continue
                    visited.add(current_url)
                    batch.append((current_url, depth))

                if not batch:
                    break

                futures = {
                    executor.submit(_process_url, url, depth): (url, depth)
                    for url, depth in batch
                }
                for future in as_completed(futures):
                    try:
                        new_urls = future.result()
                        for new_url, new_depth in new_urls:
                            if new_url not in visited and new_url not in queued:
                                if len(visited) + len(queue) < max_pages * 12:
                                    queue.append((new_url, new_depth))
                                    queued.add(new_url)
                    except Exception as exc:
                        url, _ = futures[future]
                        errors.append(f"{url} - {str(exc)}")

        if indexed_pages > 0:
            self.recompute_authority_scores()

        return CrawlReport(
            seed_url=normalized_seed,
            indexed_pages=indexed_pages,
            added_pages=added_pages,
            updated_pages=updated_pages,
            skipped_pages=skipped_pages,
            errors=errors[:10],
        )

    def _wait_for_domain(self, host: str):
        with self._domain_delay_lock:
            last_access = self._domain_last_access.get(host, 0)
            now = time.time()
            elapsed = now - last_access
            if elapsed < self._crawl_delay:
                time.sleep(self._crawl_delay - elapsed)
            self._domain_last_access[host] = time.time()

    def normalize_url(self, raw_url: str) -> str | None:
        cleaned = (raw_url or "").strip()
        if not cleaned:
            return None

        if "://" not in cleaned:
            cleaned = "https://" + cleaned

        parsed = parse.urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None

        netloc = parsed.netloc.lower()
        if netloc.endswith(":80") and parsed.scheme == "http":
            netloc = netloc[:-3]
        if netloc.endswith(":443") and parsed.scheme == "https":
            netloc = netloc[:-4]

        path = parsed.path or "/"
        return parse.urlunparse(
            (
                parsed.scheme.lower(),
                netloc,
                path,
                "",
                parsed.query,
                "",
            )
        )

    def _allowed_by_robots(self, url: str, cache: dict) -> bool:
        parsed = parse.urlparse(url)
        robots_url = parse.urlunparse((parsed.scheme, parsed.netloc, "/robots.txt", "", "", ""))
        if robots_url not in cache:
            parser = robotparser.RobotFileParser()
            parser.set_url(robots_url)
            try:
                parser.read()
                cache[robots_url] = parser
            except Exception:
                cache[robots_url] = None

        parser = cache[robots_url]
        if parser is None:
            return True
        return parser.can_fetch(self.user_agent, url)

    def _fetch_html(self, url: str) -> tuple[str, str]:
        ua = random.choice(USER_AGENT_POOL)
        req = request.Request(
            url,
            headers={
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with request.urlopen(req, timeout=4) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                raise ValueError("Skipped non-HTML content.")

            charset = response.headers.get_content_charset() or "utf-8"
            payload = response.read(900_000)
            html = payload.decode(charset, errors="replace")
            return response.geturl(), html

    def _store_page(
        self,
        url: str,
        title: str,
        content: str,
        snippet: str,
        engagement_score: int,
        outgoing_links: list[str],
        meta_description: str = "",
        page_load_speed: float = 0.0,
        domain_trust_score: float = 0.5,
    ) -> bool:
        tokens = [term for term in self._tokenize(f"{title} {content}") if term not in STOP_WORDS]
        frequencies = Counter(tokens)
        timestamp = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        crawl_ts = time.time()
        source_host = parse.urlparse(url).netloc.lower()

        # Compute star rating
        star_rating = self._compute_star_rating(
            engagement_score, 0.0, domain_trust_score, 0, len(content)
        )

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id FROM pages WHERE url = ?",
                (url,),
            ).fetchone()

            if existing:
                page_id = existing["id"]
                connection.execute(
                    """
                    UPDATE pages
                    SET title = ?, content = ?, snippet = ?, engagement_score = ?,
                        authority_score = authority_score, crawled_at = ?,
                        meta_description = ?, page_load_speed = ?,
                        domain_trust_score = ?, star_rating = ?,
                        crawl_timestamp = ?
                    WHERE id = ?
                    """,
                    (title, content, snippet, engagement_score, timestamp,
                     meta_description, page_load_speed, domain_trust_score,
                     star_rating, crawl_ts, page_id),
                )
                connection.execute("DELETE FROM page_terms WHERE page_id = ?", (page_id,))
                connection.execute("DELETE FROM page_links WHERE source_page_id = ?", (page_id,))
                created = False
            else:
                cursor = connection.execute(
                    """
                    INSERT INTO pages (url, title, content, snippet, engagement_score,
                        authority_score, crawled_at, meta_description, page_load_speed,
                        domain_trust_score, star_rating, crawl_timestamp)
                    VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)
                    """,
                    (url, title, content, snippet, engagement_score, timestamp,
                     meta_description, page_load_speed, domain_trust_score,
                     star_rating, crawl_ts),
                )
                page_id = cursor.lastrowid
                created = True

            connection.executemany(
                """
                INSERT INTO page_terms (page_id, term, frequency)
                VALUES (?, ?, ?)
                """,
                [(page_id, term, count) for term, count in frequencies.items()],
            )
            connection.executemany(
                """
                INSERT INTO page_links (source_page_id, source_host, target_url, target_host)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (
                        page_id,
                        source_host,
                        target_url,
                        parse.urlparse(target_url).netloc.lower(),
                    )
                    for target_url in outgoing_links
                ],
            )

        return created

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[a-z0-9][a-z0-9_-]{1,31}", text.lower())

    def _build_snippet(self, content: str, terms: list[str], max_length: int = 220) -> str:
        clean = " ".join(content.split())
        if not clean:
            return ""

        hit_index = 0
        lower = clean.lower()
        for term in terms:
            found = lower.find(term)
            if found >= 0:
                hit_index = found
                break

        start = max(0, hit_index - 60)
        end = min(len(clean), start + max_length)
        snippet = clean[start:end].strip()
        if start > 0:
            snippet = "... " + snippet
        if end < len(clean):
            snippet += " ..."
        return snippet

    def _extract_engagement_score(self, title: str, content: str) -> int:
        text = f"{title}\n{content}".lower()
        total = 0
        patterns = [
            r"(\d+(?:\.\d+)?)\s*([km]?)\s+(?:upvotes|upvote|points|likes|views|comments|subscribers|followers)",
            r"(?:score|rating)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*([km]?)",
        ]
        for pattern in patterns:
            for amount, suffix in re.findall(pattern, text):
                total += self._normalize_metric(amount, suffix)
        return min(total, 5000)

    def _normalize_metric(self, amount: str, suffix: str) -> int:
        value = float(amount)
        suffix = suffix.lower()
        if suffix == "k":
            value *= 1000
        elif suffix == "m":
            value *= 1000000
        return int(value // 10)

    def _clean_title(self, title: str, url: str) -> str:
        cleaned = (title or "").strip()
        if cleaned and cleaned.lower() != "untitled page":
            return cleaned

        parsed = parse.urlparse(url)
        path = parsed.path.strip("/")
        if path:
            last_segment = path.split("/")[-1].replace("-", " ").replace("_", " ").strip()
            if last_segment:
                return f"{parsed.netloc} / {last_segment}"
        return parsed.netloc or "Untitled page"

    def _contains_whole_term(self, text: str, term: str) -> bool:
        return re.search(rf"\b{re.escape(term)}\b", text) is not None

    def _contains_whole_phrase(self, text: str, phrase: str) -> bool:
        return re.search(rf"\b{re.escape(phrase)}\b", text) is not None

    def _classify_query_mode(self, raw_query: str, terms: list[str]) -> str:
        cleaned = (raw_query or "").strip().lower()
        if cleaned.startswith("how ") or cleaned.startswith("how to "):
            return "howto"
        term_set = set(terms)
        if term_set & NEWS_QUERY_TERMS:
            return "news"
        if term_set & HOWTO_QUERY_TERMS:
            return "howto"
        return "reference"

    def _build_result_title(
        self,
        title: str,
        content: str,
        terms: list[str],
        query_phrase: str,
        raw_query: str,
        url: str,
    ) -> str:
        query_label = self._humanize_query_label(raw_query or query_phrase or " ".join(terms))
        title_lower = title.lower()
        if raw_query and raw_query.lower() in title_lower:
            return title
        if query_phrase and self._contains_whole_phrase(title_lower, query_phrase):
            return title
        if all(self._contains_whole_term(title_lower, term) for term in terms):
            if query_label.lower() not in title_lower:
                return self._truncate_text(f"{query_label} - {title}", 88)
            return title

        sentence = self._extract_matching_sentence(content, terms, query_phrase)
        if sentence:
            if query_label:
                return self._truncate_text(f"{query_label} - {sentence}", 88)
            return self._truncate_text(sentence, 88)

        cleaned_title = self._clean_title(title, url)
        if query_label.lower() not in cleaned_title.lower():
            return self._truncate_text(f"{query_label} - {cleaned_title}", 88)
        return cleaned_title

    def _extract_matching_sentence(self, content: str, terms: list[str], query_phrase: str) -> str:
        sentences = re.split(r"(?<=[.!?])\s+|\n+", content or "")
        for sentence in sentences:
            cleaned = " ".join(sentence.split()).strip(" -:|")
            if not cleaned:
                continue
            lower = cleaned.lower()
            if query_phrase and self._contains_whole_phrase(lower, query_phrase):
                return cleaned
        for sentence in sentences:
            cleaned = " ".join(sentence.split()).strip(" -:|")
            if not cleaned:
                continue
            lower = cleaned.lower()
            if all(self._contains_whole_term(lower, term) for term in terms):
                return cleaned
        return ""

    def _humanize_query_label(self, query: str) -> str:
        words = [word for word in (query or "").split() if word]
        if not words:
            return ""
        return " ".join(word[:1].upper() + word[1:] for word in words)

    def _truncate_text(self, text: str, max_length: int) -> str:
        cleaned = " ".join((text or "").split())
        if len(cleaned) <= max_length:
            return cleaned
        return cleaned[: max_length - 3].rstrip(" ,;:-") + "..."

    def _extract_indexable_links(self, links: list[str]) -> list[str]:
        normalized_links = []
        seen = set()
        for link in links:
            normalized = self.normalize_url(link)
            if not normalized:
                continue
            parsed = parse.urlparse(normalized)
            if parsed.scheme not in {"http", "https"}:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            normalized_links.append(normalized)
            if len(normalized_links) >= 400:
                break
        return normalized_links

    def suggest_query(self, query: str) -> str | None:
        query = (query or "").strip().lower()
        if not query:
            return None

        raw_terms = self._tokenize(query)
        if not raw_terms:
            return None

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT term, SUM(frequency) AS total_frequency
                FROM page_terms
                WHERE length(term) >= 3
                GROUP BY term
                ORDER BY total_frequency DESC, term ASC
                LIMIT 5000
                """
            ).fetchall()

        vocabulary = [row["term"] for row in rows]
        vocabulary_set = set(vocabulary)
        changed = False
        suggested_terms = []
        for term in raw_terms:
            if term in vocabulary_set or len(term) < 3:
                suggested_terms.append(term)
                continue

            match = difflib.get_close_matches(term, vocabulary, n=1, cutoff=0.84)
            if match:
                suggested_terms.append(match[0])
                changed = True
            else:
                suggested_terms.append(term)

        suggestion = " ".join(suggested_terms).strip()
        if changed and suggestion != query:
            return suggestion
        return None

    def recompute_authority_scores(self, iterations: int = 12, damping: float = 0.85):
        with self._connect() as connection:
            page_rows = connection.execute("SELECT id, url FROM pages").fetchall()
            if not page_rows:
                return

            page_ids = [int(row["id"]) for row in page_rows]
            page_id_set = set(page_ids)
            link_rows = connection.execute(
                """
                SELECT pl.source_page_id, target.id AS target_page_id
                FROM page_links AS pl
                JOIN pages AS target ON target.url = pl.target_url
                """
            ).fetchall()

            outbound = {page_id: set() for page_id in page_ids}
            for row in link_rows:
                source_id = int(row["source_page_id"])
                target_id = int(row["target_page_id"])
                if source_id in page_id_set and target_id in page_id_set and source_id != target_id:
                    outbound[source_id].add(target_id)

            page_count = len(page_ids)
            base_score = 1.0 / page_count
            scores = {page_id: base_score for page_id in page_ids}

            for _ in range(max(1, iterations)):
                sink_total = sum(
                    scores[page_id]
                    for page_id in page_ids
                    if not outbound.get(page_id)
                )
                next_scores = {
                    page_id: ((1.0 - damping) / page_count) + (damping * sink_total / page_count)
                    for page_id in page_ids
                }

                for source_id, targets in outbound.items():
                    if not targets:
                        continue
                    share = scores[source_id] / len(targets)
                    for target_id in targets:
                        next_scores[target_id] += damping * share

                scores = next_scores

            connection.executemany(
                "UPDATE pages SET authority_score = ? WHERE id = ?",
                [(float(scores.get(page_id, 0.0)), page_id) for page_id in page_ids],
            )
