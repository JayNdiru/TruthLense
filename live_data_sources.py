"""
TruthLens — Live Data Source Connectors
=========================================
Real API integrations for live fact-checking, link scrutiny, and news ingestion.

Sources that work WITHOUT an API key (free, immediate):
  - PolitiFact RSS feed
  - FactCheck.org RSS feed
  - Snopes RSS feed
  - Wayback Machine (Internet Archive)
  - URL content extraction (requests + BeautifulSoup)

Sources that require a FREE API key:
  - Google Fact Check Tools API  (GOOGLE_FACTCHECK_API_KEY)
  - Google Safe Browsing API     (GOOGLE_SAFEBROWSING_API_KEY)
  - NewsAPI.org                  (NEWSAPI_KEY)
  - VirusTotal                   (VIRUSTOTAL_API_KEY)
"""

import os
import re
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse

import requests

# Optional imports — degrade gracefully
try:
    import feedparser
    _HAS_FEEDPARSER = True
except ImportError:
    _HAS_FEEDPARSER = False

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

logger = logging.getLogger(__name__)

# ─── Shared HTTP session with retries ─────────────────────────────────────────
_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(max_retries=2, pool_connections=10, pool_maxsize=10)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)
_session.headers.update({"User-Agent": "TruthLens/1.0 (misinformation-detection-platform)"})
_TIMEOUT = 15  # seconds


# ══════════════════════════════════════════════════════════════════════════════
#  1. RSS FACT-CHECK FEEDS  (FREE — no key needed)
# ══════════════════════════════════════════════════════════════════════════════

class RSSFactCheckFetcher:
    """Fetch real fact-checks from PolitiFact, FactCheck.org, and Snopes RSS feeds."""

    FEEDS = {
        "PolitiFact": "https://www.politifact.com/rss/factchecks/",
        "FactCheck.org": "https://www.factcheck.org/feed/",
        "Snopes": "https://www.snopes.com/feed/",
    }

    def __init__(self):
        self.last_fetch: Dict[str, datetime] = {}
        self._cache: Dict[str, List[Dict]] = {}
        self._available = _HAS_FEEDPARSER

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "name": "Fact-Check RSS Feeds",
            "provider": "PolitiFact, FactCheck.org, Snopes",
            "requires_key": False,
            "available": self._available,
            "missing_dependency": None if self._available else "feedparser (pip install feedparser)",
            "feeds": list(self.FEEDS.keys()),
            "last_fetch": {k: v.isoformat() for k, v in self.last_fetch.items()},
        }

    def fetch_all(self, max_per_feed: int = 30) -> List[Dict[str, Any]]:
        """Fetch fact-checks from all RSS feeds. Returns list of dicts."""
        if not self._available:
            logger.warning("feedparser not installed — RSS fact-check feeds unavailable")
            return []

        all_items: List[Dict[str, Any]] = []
        for source_name, feed_url in self.FEEDS.items():
            try:
                feed = feedparser.parse(feed_url)
                if feed.bozo and not feed.entries:
                    logger.warning("RSS parse error for %s: %s", source_name, feed.bozo_exception)
                    continue

                for entry in feed.entries[:max_per_feed]:
                    # Extract verdict from title patterns like "Fact check: <claim> — <verdict>"
                    title = entry.get("title", "")
                    summary = entry.get("summary", entry.get("description", ""))
                    # Strip HTML tags from summary
                    if _HAS_BS4:
                        summary = BeautifulSoup(summary, "html.parser").get_text(separator=" ")
                    else:
                        summary = re.sub(r"<[^>]+>", "", summary)

                    verdict = self._extract_verdict(title, summary)

                    all_items.append({
                        "claim": title[:500],
                        "verdict": verdict,
                        "source": source_name,
                        "url": entry.get("link", ""),
                        "date_checked": entry.get("published", datetime.now().isoformat()),
                        "summary": summary[:1000],
                    })

                self.last_fetch[source_name] = datetime.now()
                logger.info("Fetched %d fact-checks from %s", min(len(feed.entries), max_per_feed), source_name)

            except Exception as e:
                logger.error("Failed to fetch RSS feed %s: %s", source_name, e)

        return all_items

    @staticmethod
    def _extract_verdict(title: str, summary: str) -> str:
        """Try to extract a verdict from the fact-check title or summary."""
        text = (title + " " + summary).upper()
        for verdict in ["PANTS ON FIRE", "FALSE", "MOSTLY FALSE", "HALF TRUE",
                        "MOSTLY TRUE", "TRUE", "UNPROVEN", "MIXTURE",
                        "MISCAPTIONED", "OUTDATED", "CORRECT ATTRIBUTION"]:
            if verdict in text:
                return verdict
        return "CHECKED"


# ══════════════════════════════════════════════════════════════════════════════
#  2. GOOGLE FACT CHECK TOOLS API  (FREE — needs key)
# ══════════════════════════════════════════════════════════════════════════════

class GoogleFactCheckAPI:
    """Search Google's aggregated fact-check database (ClaimReview markup)."""

    BASE_URL = "https://factchecktools.googleapis.com/v1alpha1/claims:search"

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_FACTCHECK_API_KEY", "")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "name": "Google Fact Check Tools API",
            "provider": "Google (ClaimReview aggregation)",
            "requires_key": True,
            "env_var": "GOOGLE_FACTCHECK_API_KEY",
            "available": self.available,
            "tier": "Free (10K queries/day)",
        }

    def search_claim(self, query: str, language: str = "en", max_results: int = 5) -> List[Dict[str, Any]]:
        """Search for fact-checks matching a claim or keyword."""
        if not self.available:
            return []

        try:
            resp = _session.get(self.BASE_URL, params={
                "query": query[:200],
                "languageCode": language,
                "pageSize": max_results,
                "key": self.api_key,
            }, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for claim in data.get("claims", []):
                for review in claim.get("claimReview", []):
                    results.append({
                        "claim": claim.get("text", ""),
                        "claimant": claim.get("claimant", ""),
                        "verdict": review.get("textualRating", ""),
                        "source": review.get("publisher", {}).get("name", ""),
                        "url": review.get("url", ""),
                        "review_date": review.get("reviewDate", ""),
                    })
            return results[:max_results]

        except Exception as e:
            logger.error("Google Fact Check API error: %s", e)
            return []


# ══════════════════════════════════════════════════════════════════════════════
#  3. GOOGLE SAFE BROWSING API  (FREE — needs key)
# ══════════════════════════════════════════════════════════════════════════════

class GoogleSafeBrowsingAPI:
    """Check URLs against Google's Safe Browsing threat lists."""

    BASE_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"

    THREAT_TYPES = [
        "MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE",
        "POTENTIALLY_HARMFUL_APPLICATION",
    ]

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_SAFEBROWSING_API_KEY", "")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "name": "Google Safe Browsing API",
            "provider": "Google",
            "requires_key": True,
            "env_var": "GOOGLE_SAFEBROWSING_API_KEY",
            "available": self.available,
            "tier": "Free (10K lookups/day)",
        }

    def check_url(self, url: str) -> Dict[str, Any]:
        """Check a single URL against Safe Browsing. Returns threat info or safe status."""
        if not self.available:
            return {"checked": False, "reason": "API key not configured"}

        try:
            payload = {
                "client": {"clientId": "truthlens", "clientVersion": "1.0"},
                "threatInfo": {
                    "threatTypes": self.THREAT_TYPES,
                    "platformTypes": ["ANY_PLATFORM"],
                    "threatEntryTypes": ["URL"],
                    "threatEntries": [{"url": url}],
                },
            }
            resp = _session.post(
                f"{self.BASE_URL}?key={self.api_key}",
                json=payload,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            matches = data.get("matches", [])
            if matches:
                return {
                    "checked": True,
                    "safe": False,
                    "threats": [
                        {
                            "type": m.get("threatType"),
                            "platform": m.get("platformType"),
                        }
                        for m in matches
                    ],
                }
            return {"checked": True, "safe": True, "threats": []}

        except Exception as e:
            logger.error("Safe Browsing API error: %s", e)
            return {"checked": False, "reason": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
#  4. WAYBACK MACHINE  (FREE — no key needed)
# ══════════════════════════════════════════════════════════════════════════════

class WaybackMachineAPI:
    """Check URL history via the Internet Archive Wayback Machine."""

    AVAILABILITY_URL = "https://archive.org/wayback/available"

    def __init__(self):
        pass  # No key needed

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "name": "Wayback Machine (Internet Archive)",
            "provider": "Internet Archive",
            "requires_key": False,
            "available": True,
            "tier": "Free (unlimited)",
        }

    def check_url(self, url: str, timestamp: str = None) -> Dict[str, Any]:
        """Check if a URL has been archived. Returns archive info."""
        try:
            params = {"url": url}
            if timestamp:
                params["timestamp"] = timestamp

            resp = _session.get(self.AVAILABILITY_URL, params=params, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            snapshot = data.get("archived_snapshots", {}).get("closest")
            if snapshot:
                return {
                    "archived": True,
                    "archive_url": snapshot.get("url", ""),
                    "archive_timestamp": snapshot.get("timestamp", ""),
                    "status": snapshot.get("status", ""),
                    "available": snapshot.get("available", False),
                }
            return {"archived": False}

        except Exception as e:
            logger.error("Wayback Machine API error: %s", e)
            return {"archived": False, "error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
#  5. NEWSAPI.ORG  (FREE tier — needs key)
# ══════════════════════════════════════════════════════════════════════════════

class NewsAPIClient:
    """Fetch live news articles from NewsAPI.org for cross-referencing."""

    BASE_URL = "https://newsapi.org/v2"

    def __init__(self):
        self.api_key = os.getenv("NEWSAPI_KEY", "")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "name": "NewsAPI.org",
            "provider": "NewsAPI",
            "requires_key": True,
            "env_var": "NEWSAPI_KEY",
            "available": self.available,
            "tier": "Free (100 req/day) or Business ($449/mo)",
        }

    def search_articles(self, query: str, days_back: int = 7, page_size: int = 10) -> List[Dict[str, Any]]:
        """Search for news articles matching a query."""
        if not self.available:
            return []

        try:
            from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            resp = _session.get(f"{self.BASE_URL}/everything", params={
                "q": query[:100],
                "from": from_date,
                "sortBy": "relevancy",
                "pageSize": page_size,
                "apiKey": self.api_key,
            }, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            articles = []
            for art in data.get("articles", []):
                articles.append({
                    "title": art.get("title", ""),
                    "description": art.get("description", ""),
                    "source": art.get("source", {}).get("name", ""),
                    "url": art.get("url", ""),
                    "published_at": art.get("publishedAt", ""),
                    "author": art.get("author", ""),
                })
            return articles

        except Exception as e:
            logger.error("NewsAPI error: %s", e)
            return []

    def top_headlines(self, country: str = "us", page_size: int = 20) -> List[Dict[str, Any]]:
        """Fetch top headlines for ingestion."""
        if not self.available:
            return []

        try:
            resp = _session.get(f"{self.BASE_URL}/top-headlines", params={
                "country": country,
                "pageSize": page_size,
                "apiKey": self.api_key,
            }, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()

            return [
                {
                    "title": a.get("title", ""),
                    "description": a.get("description", ""),
                    "content": a.get("content", ""),
                    "source": a.get("source", {}).get("name", ""),
                    "url": a.get("url", ""),
                    "published_at": a.get("publishedAt", ""),
                }
                for a in data.get("articles", [])
            ]

        except Exception as e:
            logger.error("NewsAPI top_headlines error: %s", e)
            return []


# ══════════════════════════════════════════════════════════════════════════════
#  6. VIRUSTOTAL  (FREE tier — needs key)
# ══════════════════════════════════════════════════════════════════════════════

class VirusTotalAPI:
    """Scan URLs for malicious content via VirusTotal."""

    BASE_URL = "https://www.virustotal.com/api/v3"

    def __init__(self):
        self.api_key = os.getenv("VIRUSTOTAL_API_KEY", "")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "name": "VirusTotal URL Scanner",
            "provider": "VirusTotal",
            "requires_key": True,
            "env_var": "VIRUSTOTAL_API_KEY",
            "available": self.available,
            "tier": "Free (4 lookups/min) or Premium",
        }

    def scan_url(self, url: str) -> Dict[str, Any]:
        """Get analysis report for a URL. Uses the URL-ID lookup (no submission queue)."""
        if not self.available:
            return {"scanned": False, "reason": "API key not configured"}

        try:
            # VirusTotal URL ID = base64url of the URL without padding
            import base64
            url_id = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")

            resp = _session.get(
                f"{self.BASE_URL}/urls/{url_id}",
                headers={"x-apikey": self.api_key},
                timeout=_TIMEOUT,
            )

            if resp.status_code == 404:
                return {"scanned": True, "found": False, "message": "URL not in VirusTotal database"}

            resp.raise_for_status()
            data = resp.json().get("data", {}).get("attributes", {})
            stats = data.get("last_analysis_stats", {})

            return {
                "scanned": True,
                "found": True,
                "malicious": stats.get("malicious", 0),
                "suspicious": stats.get("suspicious", 0),
                "harmless": stats.get("harmless", 0),
                "undetected": stats.get("undetected", 0),
                "reputation": data.get("reputation", 0),
                "total_votes": data.get("total_votes", {}),
                "last_analysis_date": data.get("last_analysis_date", ""),
            }

        except Exception as e:
            logger.error("VirusTotal API error: %s", e)
            return {"scanned": False, "reason": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
#  7. URL CONTENT EXTRACTOR  (FREE — no key needed)
# ══════════════════════════════════════════════════════════════════════════════

class URLContentExtractor:
    """Fetch and parse web page content from a URL (article text, metadata)."""

    def __init__(self):
        self._available = _HAS_BS4

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "name": "URL Content Extractor",
            "provider": "Built-in (requests + BeautifulSoup)",
            "requires_key": False,
            "available": self._available,
            "missing_dependency": None if self._available else "beautifulsoup4 (pip install beautifulsoup4)",
        }

    def extract(self, url: str) -> Dict[str, Any]:
        """Fetch a URL and extract article content, metadata, and outbound links."""
        result = {
            "url": url,
            "fetched": False,
            "domain": urlparse(url).netloc,
            "headline": "",
            "content": "",
            "description": "",
            "author": "",
            "publish_date": "",
            "outbound_links": [],
            "word_count": 0,
        }

        try:
            resp = _session.get(url, timeout=_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()

            if not self._available:
                # Minimal extraction without BS4
                result["fetched"] = True
                result["content"] = resp.text[:5000]
                return result

            soup = BeautifulSoup(resp.text, "html.parser")

            # Title / headline
            og_title = soup.find("meta", property="og:title")
            result["headline"] = (
                og_title["content"] if og_title and og_title.get("content")
                else (soup.title.string if soup.title else "")
            )

            # Description
            og_desc = soup.find("meta", property="og:description")
            meta_desc = soup.find("meta", attrs={"name": "description"})
            result["description"] = (
                (og_desc or meta_desc or {}).get("content", "")
            )

            # Author
            author_meta = soup.find("meta", attrs={"name": "author"})
            result["author"] = author_meta["content"] if author_meta and author_meta.get("content") else ""

            # Publish date
            for attr in ["article:published_time", "datePublished", "og:article:published_time"]:
                date_tag = soup.find("meta", property=attr) or soup.find("meta", attrs={"name": attr})
                if date_tag and date_tag.get("content"):
                    result["publish_date"] = date_tag["content"]
                    break

            # Article body — try <article> first, then main content areas
            article_tag = soup.find("article")
            if article_tag:
                paragraphs = article_tag.find_all("p")
            else:
                # Fallback: gather all <p> tags from body
                paragraphs = soup.find_all("p")

            body_text = " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
            result["content"] = body_text[:10000]
            result["word_count"] = len(body_text.split())

            # Outbound links
            for a_tag in soup.find_all("a", href=True)[:50]:
                href = a_tag["href"]
                if href.startswith("http") and urlparse(href).netloc != urlparse(url).netloc:
                    result["outbound_links"].append(href)

            result["fetched"] = True

        except Exception as e:
            logger.error("URL extraction error for %s: %s", url, e)
            result["error"] = str(e)

        return result


# ══════════════════════════════════════════════════════════════════════════════
#  8. RSS NEWS ARTICLE FEEDS  (FREE — real articles with real URLs)
# ══════════════════════════════════════════════════════════════════════════════

class RSSArticleFetcher:
    """Fetch real news articles from major RSS feeds.
    
    These are genuine articles from real publishers with real, working URLs
    that users can click through to read the original source.
    """

    FEEDS = {
        # Major wire services & credible outlets
        "Reuters": {
            "url": "https://feeds.reuters.com/reuters/topNews",
            "domain": "reuters.com",
        },
        "BBC World": {
            "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
            "domain": "bbc.com",
        },
        "NPR": {
            "url": "https://feeds.npr.org/1001/rss.xml",
            "domain": "npr.org",
        },
        "The Guardian World": {
            "url": "https://www.theguardian.com/world/rss",
            "domain": "theguardian.com",
        },
        "Al Jazeera": {
            "url": "https://www.aljazeera.com/xml/rss/all.xml",
            "domain": "aljazeera.com",
        },
        # Science / Tech
        "Ars Technica": {
            "url": "https://feeds.arstechnica.com/arstechnica/index",
            "domain": "arstechnica.com",
        },
    }

    def __init__(self):
        self._available = _HAS_FEEDPARSER

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "name": "News Article RSS Feeds",
            "provider": ", ".join(self.FEEDS.keys()),
            "requires_key": False,
            "available": self._available,
            "feeds": list(self.FEEDS.keys()),
        }

    def fetch_all(self, max_per_feed: int = 15) -> List[Dict[str, Any]]:
        """Fetch real news articles from all configured RSS feeds.
        
        Returns list of dicts with real headlines, real URLs, and real source domains.
        """
        if not self._available:
            logger.warning("feedparser not installed — RSS article feeds unavailable")
            return []

        all_articles: List[Dict[str, Any]] = []
        seen_urls = set()

        for source_name, feed_info in self.FEEDS.items():
            try:
                feed = feedparser.parse(feed_info["url"])
                if feed.bozo and not feed.entries:
                    logger.warning("RSS parse error for %s: %s", source_name, feed.bozo_exception)
                    continue

                for entry in feed.entries[:max_per_feed]:
                    link = entry.get("link", "")
                    if not link or link in seen_urls:
                        continue
                    seen_urls.add(link)

                    title = entry.get("title", "").strip()
                    if not title:
                        continue

                    # Extract summary text
                    summary = entry.get("summary", entry.get("description", ""))
                    if _HAS_BS4:
                        summary = BeautifulSoup(summary, "html.parser").get_text(separator=" ")
                    else:
                        summary = re.sub(r"<[^>]+>", "", summary)

                    all_articles.append({
                        "headline": title[:300],
                        "source": feed_info["domain"],
                        "url": link,
                        "content": (title + ". " + summary)[:2000],
                        "published": entry.get("published", datetime.now().isoformat()),
                        "feed_name": source_name,
                    })

                logger.info("Fetched %d articles from %s", min(len(feed.entries), max_per_feed), source_name)

            except Exception as e:
                logger.error("Failed to fetch RSS feed %s: %s", source_name, e)

        return all_articles


# ══════════════════════════════════════════════════════════════════════════════
#  9. REDDIT SEARCH  (FREE — public JSON, no auth needed for basic search)
# ══════════════════════════════════════════════════════════════════════════════

class RedditSearchAPI:
    """Search Reddit for real discussions about articles/topics.

    Uses the public `.json` endpoint (no OAuth required).
    Rate limit: ~60 requests/minute without auth.
    For higher limits, register at https://www.reddit.com/prefs/apps
    and set REDDIT_CLIENT_ID + REDDIT_CLIENT_SECRET in .env.
    """

    def __init__(self):
        # OAuth2 client credentials (optional — higher rate limits)
        self.client_id = os.getenv("REDDIT_CLIENT_ID", "")
        self.client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
        self._token = None
        self._token_expiry = datetime.min

    @property
    def available(self) -> bool:
        return True  # Public JSON always available

    @property
    def status(self) -> Dict[str, Any]:
        auth_mode = "OAuth2" if self.client_id else "Public JSON (no auth)"
        return {
            "name": "Reddit Search",
            "provider": "Reddit (reddit.com)",
            "requires_key": False,
            "available": True,
            "auth_mode": auth_mode,
            "tier": "Free public API (60 req/min) or OAuth2 for higher limits",
        }

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers, using OAuth2 if credentials are set."""
        headers = {"User-Agent": "TruthLens/1.0 (misinformation-detection-platform)"}
        if self.client_id and self.client_secret:
            if datetime.now() >= self._token_expiry:
                self._refresh_token()
            if self._token:
                headers["Authorization"] = f"bearer {self._token}"
        return headers

    def _refresh_token(self):
        """Get OAuth2 application-only token."""
        try:
            resp = requests.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": "TruthLens/1.0"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data.get("access_token")
            self._token_expiry = datetime.now() + timedelta(seconds=data.get("expires_in", 3600) - 60)
        except Exception as e:
            logger.error("Reddit OAuth2 token refresh failed: %s", e)

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search Reddit for posts matching a query. Returns real post data."""
        try:
            base = "https://oauth.reddit.com" if self._token else "https://www.reddit.com"
            resp = _session.get(
                f"{base}/search.json",
                params={"q": query[:200], "sort": "relevance", "limit": limit, "t": "month"},
                headers=self._get_headers(),
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                results.append({
                    "platform": "reddit",
                    "title": post.get("title", ""),
                    "subreddit": post.get("subreddit_name_prefixed", ""),
                    "url": f"https://www.reddit.com{post.get('permalink', '')}",
                    "external_url": post.get("url", ""),
                    "score": post.get("score", 0),
                    "upvote_ratio": post.get("upvote_ratio", 0),
                    "num_comments": post.get("num_comments", 0),
                    "created_utc": post.get("created_utc", 0),
                    "author": post.get("author", ""),
                })
            return results

        except Exception as e:
            logger.error("Reddit search error: %s", e)
            return []

    def search_url(self, url: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search for Reddit posts that link to a specific URL."""
        return self.search(f"url:{url}", limit=limit)


# ══════════════════════════════════════════════════════════════════════════════
#  9. YOUTUBE DATA API v3  (FREE tier — needs key, 10K units/day)
# ══════════════════════════════════════════════════════════════════════════════

class YouTubeDataAPI:
    """Search YouTube for videos discussing articles/topics.

    Uses YouTube Data API v3 (search.list).
    Free tier: 10,000 quota units/day (each search costs 100 units = 100 searches/day).
    Signup: https://console.cloud.google.com/ → Enable "YouTube Data API v3"
    """

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self):
        self.api_key = os.getenv("YOUTUBE_API_KEY", "")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "name": "YouTube Data API",
            "provider": "Google (YouTube)",
            "requires_key": True,
            "env_var": "YOUTUBE_API_KEY",
            "available": self.available,
            "tier": "Free (10K units/day ≈ 100 searches)",
        }

    def search_videos(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Search YouTube for videos matching a topic/headline."""
        if not self.available:
            return []

        try:
            resp = _session.get(
                f"{self.BASE_URL}/search",
                params={
                    "q": query[:100],
                    "part": "snippet",
                    "type": "video",
                    "maxResults": max_results,
                    "order": "relevance",
                    "key": self.api_key,
                },
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("items", []):
                vid_id = item.get("id", {}).get("videoId", "")
                snippet = item.get("snippet", {})
                results.append({
                    "platform": "youtube",
                    "title": snippet.get("title", ""),
                    "channel": snippet.get("channelTitle", ""),
                    "description": snippet.get("description", "")[:200],
                    "url": f"https://www.youtube.com/watch?v={vid_id}" if vid_id else "",
                    "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
                    "published_at": snippet.get("publishedAt", ""),
                    "video_id": vid_id,
                })
            return results

        except Exception as e:
            logger.error("YouTube Data API error: %s", e)
            return []


# ══════════════════════════════════════════════════════════════════════════════
#  UNIFIED DATA SOURCE REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

class LiveDataSourceRegistry:
    """Central registry of all live data source connectors with health status."""

    def __init__(self):
        self.rss_factcheck = RSSFactCheckFetcher()
        self.rss_articles = RSSArticleFetcher()
        self.google_factcheck = GoogleFactCheckAPI()
        self.safe_browsing = GoogleSafeBrowsingAPI()
        self.wayback = WaybackMachineAPI()
        self.newsapi = NewsAPIClient()
        self.virustotal = VirusTotalAPI()
        self.url_extractor = URLContentExtractor()
        self.reddit = RedditSearchAPI()
        self.youtube = YouTubeDataAPI()

    def get_all_status(self) -> List[Dict[str, Any]]:
        """Return connection status of every data source (real, not simulated)."""
        return [
            self.rss_factcheck.status,
            self.rss_articles.status,
            self.google_factcheck.status,
            self.safe_browsing.status,
            self.wayback.status,
            self.newsapi.status,
            self.virustotal.status,
            self.url_extractor.status,
            self.reddit.status,
            self.youtube.status,
        ]

    def get_summary(self) -> Dict[str, Any]:
        statuses = self.get_all_status()
        total = len(statuses)
        active = sum(1 for s in statuses if s.get("available"))
        keys_needed = [
            s["env_var"] for s in statuses
            if s.get("requires_key") and not s.get("available")
        ]
        return {
            "total_sources": total,
            "active_sources": active,
            "inactive_sources": total - active,
            "missing_api_keys": keys_needed,
            "sources": statuses,
        }
