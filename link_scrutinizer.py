"""
TruthLens — Link Scrutiny Pipeline
====================================
Takes a URL, fetches its content, runs it through every available live data
source, then feeds the results into the analytics engine for a full
credibility report.

Usage:
    from link_scrutinizer import LinkScrutinizer
    scrutinizer = LinkScrutinizer(engine, registry)
    report = scrutinizer.scrutinize("https://example.com/article")
"""

import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class LinkScrutinizer:
    """End-to-end link scrutiny pipeline."""

    def __init__(self, engine, registry):
        """
        Args:
            engine:   TruthLensAnalyticsEngine instance
            registry: LiveDataSourceRegistry instance
        """
        self.engine = engine
        self.reg = registry

    def scrutinize(self, url: str) -> Dict[str, Any]:
        """
        Full scrutiny pipeline for a single URL.

        Steps:
          1. Extract page content (headline, body, metadata, outbound links)
          2. Check URL safety (Google Safe Browsing)
          3. Check URL reputation (VirusTotal)
          4. Search fact-check databases (Google Fact Check API + RSS cache)
          5. Check archive history (Wayback Machine)
          6. Cross-reference with credible news outlets (NewsAPI)
          7. Run NLP credibility analysis (TruthLens engine)
          8. Aggregate everything into a single report

        Returns:
            Comprehensive scrutiny report dict.
        """
        start_time = time.time()
        domain = urlparse(url).netloc

        report: Dict[str, Any] = {
            "url": url,
            "domain": domain,
            "scrutinized_at": datetime.now().isoformat(),
            "steps_completed": [],
            "steps_failed": [],
        }

        # ── Step 1: Extract page content ──────────────────────────────────
        page = self._step_extract(url, report)

        # ── Step 2: Google Safe Browsing ──────────────────────────────────
        self._step_safe_browsing(url, report)

        # ── Step 3: VirusTotal ────────────────────────────────────────────
        self._step_virustotal(url, report)

        # ── Step 4: Fact-check search ─────────────────────────────────────
        headline = page.get("headline", "") if page else ""
        content = page.get("content", "") if page else ""
        self._step_factcheck_search(headline, content, report)

        # ── Step 5: Wayback Machine ───────────────────────────────────────
        self._step_wayback(url, report)

        # ── Step 6: News cross-reference ──────────────────────────────────
        self._step_news_crossref(headline, report)

        # ── Step 7: NLP analysis via TruthLens engine ─────────────────────
        self._step_engine_analysis(page, url, domain, report)

        # ── Finalize ──────────────────────────────────────────────────────
        elapsed_ms = round((time.time() - start_time) * 1000)
        report["processing_time_ms"] = elapsed_ms
        report["sources_checked"] = len(report["steps_completed"])
        report["overall_risk"] = self._compute_overall_risk(report)

        return report

    # ──────────────────────────────────────────────────────────────────────────
    #  Individual pipeline steps
    # ──────────────────────────────────────────────────────────────────────────

    def _step_extract(self, url: str, report: Dict) -> Optional[Dict]:
        """Step 1: Fetch and parse page content."""
        try:
            page = self.reg.url_extractor.extract(url)
            report["page_content"] = {
                "headline": page.get("headline", ""),
                "description": page.get("description", ""),
                "author": page.get("author", ""),
                "publish_date": page.get("publish_date", ""),
                "word_count": page.get("word_count", 0),
                "outbound_links_count": len(page.get("outbound_links", [])),
                "fetched": page.get("fetched", False),
            }
            if page.get("fetched"):
                report["steps_completed"].append("content_extraction")
            else:
                report["steps_failed"].append("content_extraction")
            return page
        except Exception as e:
            logger.error("Step extract failed: %s", e)
            report["steps_failed"].append("content_extraction")
            return None

    def _step_safe_browsing(self, url: str, report: Dict):
        """Step 2: Google Safe Browsing check."""
        try:
            result = self.reg.safe_browsing.check_url(url)
            report["safe_browsing"] = result
            if result.get("checked"):
                report["steps_completed"].append("safe_browsing")
            else:
                report["steps_failed"].append("safe_browsing")
        except Exception as e:
            logger.error("Step safe_browsing failed: %s", e)
            report["safe_browsing"] = {"checked": False, "reason": str(e)}
            report["steps_failed"].append("safe_browsing")

    def _step_virustotal(self, url: str, report: Dict):
        """Step 3: VirusTotal URL scan."""
        try:
            result = self.reg.virustotal.scan_url(url)
            report["virustotal"] = result
            if result.get("scanned"):
                report["steps_completed"].append("virustotal")
            else:
                report["steps_failed"].append("virustotal")
        except Exception as e:
            logger.error("Step virustotal failed: %s", e)
            report["virustotal"] = {"scanned": False, "reason": str(e)}
            report["steps_failed"].append("virustotal")

    def _step_factcheck_search(self, headline: str, content: str, report: Dict):
        """Step 4: Search fact-check databases."""
        query = (headline or content[:200]).strip()
        if not query:
            report["fact_check_results"] = {"searched": False, "reason": "No content to search"}
            report["steps_failed"].append("factcheck_search")
            return

        results = []

        # Google Fact Check API
        try:
            google_results = self.reg.google_factcheck.search_claim(query)
            for r in google_results:
                r["matched_via"] = "Google Fact Check API"
            results.extend(google_results)
        except Exception as e:
            logger.error("Google Fact Check search failed: %s", e)

        # Search cached RSS fact-checks in the database
        try:
            import sqlite3, json
            conn = sqlite3.connect(self.engine.db_path, timeout=10)
            cursor = conn.cursor()
            # Simple keyword search against stored fact-checks
            words = [w for w in query.lower().split() if len(w) > 3][:5]
            if words:
                conditions = " OR ".join(["LOWER(claim) LIKE ?"] * len(words))
                params = [f"%{w}%" for w in words]
                cursor.execute(
                    f"SELECT claim, verdict, source, url FROM fact_checks WHERE {conditions} LIMIT 5",
                    params,
                )
                for row in cursor.fetchall():
                    results.append({
                        "claim": row[0],
                        "verdict": row[1],
                        "source": row[2],
                        "url": row[3],
                        "matched_via": "Local fact-check DB (RSS-synced)",
                    })
            conn.close()
        except Exception as e:
            logger.error("Local fact-check DB search failed: %s", e)

        report["fact_check_results"] = {
            "searched": True,
            "query": query[:200],
            "matches_found": len(results),
            "matches": results,
        }
        report["steps_completed"].append("factcheck_search")

    def _step_wayback(self, url: str, report: Dict):
        """Step 5: Wayback Machine archive check."""
        try:
            result = self.reg.wayback.check_url(url)
            report["wayback_archive"] = result
            report["steps_completed"].append("wayback_archive")
        except Exception as e:
            logger.error("Step wayback failed: %s", e)
            report["wayback_archive"] = {"archived": False, "error": str(e)}
            report["steps_failed"].append("wayback_archive")

    def _step_news_crossref(self, headline: str, report: Dict):
        """Step 6: Cross-reference with credible news outlets via NewsAPI."""
        if not headline:
            report["news_crossref"] = {"searched": False, "reason": "No headline to search"}
            report["steps_failed"].append("news_crossref")
            return

        try:
            # Extract key terms from headline (first 5 significant words)
            stop_words = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or", "but", "not", "with", "this", "that", "it", "by", "from", "as", "has", "had", "have"}
            key_terms = [w for w in headline.split() if w.lower() not in stop_words and len(w) > 2][:5]
            query = " ".join(key_terms)

            articles = self.reg.newsapi.search_articles(query, days_back=14, page_size=5)
            credible_sources = [a for a in articles if a.get("source")]

            report["news_crossref"] = {
                "searched": True,
                "query": query,
                "articles_found": len(articles),
                "credible_coverage": len(credible_sources),
                "articles": articles[:5],
            }
            if articles or self.reg.newsapi.available:
                report["steps_completed"].append("news_crossref")
            else:
                report["steps_failed"].append("news_crossref")

        except Exception as e:
            logger.error("Step news_crossref failed: %s", e)
            report["news_crossref"] = {"searched": False, "reason": str(e)}
            report["steps_failed"].append("news_crossref")

    def _step_engine_analysis(self, page: Optional[Dict], url: str, domain: str, report: Dict):
        """Step 7: Run content through the TruthLens NLP engine."""
        try:
            headline = page.get("headline", "") if page else ""
            content = page.get("content", "") if page else ""
            description = page.get("description", "") if page else ""

            if not content and not headline:
                report["engine_analysis"] = {"analyzed": False, "reason": "No content extracted"}
                report["steps_failed"].append("engine_analysis")
                return

            input_data = {
                "content": content or description,
                "headline": headline,
                "source": domain,
                "url": url,
                "metadata": {"shares": 0, "likes": 0, "comments": 0},
            }

            result = self.engine.analyze_content(input_data)
            report["engine_analysis"] = {
                "analyzed": True,
                "credibility_score": result.get("credibility_score"),
                "classification": result.get("classification"),
                "confidence": result.get("confidence"),
                "signals": result.get("signals"),
                "recommendation": result.get("recommendation"),
                "explanation": result.get("explanation"),
            }
            report["steps_completed"].append("engine_analysis")

        except Exception as e:
            logger.error("Step engine_analysis failed: %s", e)
            report["engine_analysis"] = {"analyzed": False, "reason": str(e)}
            report["steps_failed"].append("engine_analysis")

    # ──────────────────────────────────────────────────────────────────────────
    #  Risk aggregation
    # ──────────────────────────────────────────────────────────────────────────

    def _compute_overall_risk(self, report: Dict) -> Dict[str, Any]:
        """Aggregate all signals into an overall risk assessment."""
        risk_score = 50  # Neutral baseline
        risk_factors = []

        # Safe Browsing
        sb = report.get("safe_browsing", {})
        if sb.get("checked") and not sb.get("safe", True):
            risk_score += 30
            risk_factors.append("URL flagged by Google Safe Browsing")

        # VirusTotal
        vt = report.get("virustotal", {})
        if vt.get("scanned") and vt.get("found"):
            malicious = vt.get("malicious", 0)
            if malicious > 0:
                risk_score += min(malicious * 5, 25)
                risk_factors.append(f"VirusTotal: {malicious} engines flagged as malicious")

        # Fact-check matches
        fc = report.get("fact_check_results", {})
        if fc.get("matches_found", 0) > 0:
            for match in fc.get("matches", []):
                verdict = (match.get("verdict") or "").upper()
                if any(v in verdict for v in ["FALSE", "PANTS ON FIRE", "FAKE"]):
                    risk_score += 15
                    risk_factors.append(f"Fact-checked as {verdict} by {match.get('source', 'unknown')}")
                    break

        # Engine analysis
        ea = report.get("engine_analysis", {})
        if ea.get("analyzed"):
            cred = ea.get("credibility_score", 50)
            if cred < 30:
                risk_score += 15
                risk_factors.append(f"Low credibility score: {cred}/100")
            elif cred > 70:
                risk_score -= 20
                risk_factors.append(f"High credibility score: {cred}/100")

            classification = ea.get("classification", "")
            if classification == "fake":
                risk_score += 10
            elif classification == "real":
                risk_score -= 10

        # News cross-reference
        nc = report.get("news_crossref", {})
        if nc.get("searched") and nc.get("credible_coverage", 0) == 0 and nc.get("articles_found", 0) == 0:
            risk_score += 5
            risk_factors.append("No credible news outlets covering this story")
        elif nc.get("credible_coverage", 0) >= 3:
            risk_score -= 10
            risk_factors.append(f"Story covered by {nc['credible_coverage']} credible outlets")

        # Wayback
        wa = report.get("wayback_archive", {})
        if wa.get("archived"):
            risk_score -= 5  # Established URL, slightly lower risk

        # Clamp
        risk_score = max(0, min(100, risk_score))

        if risk_score >= 70:
            level = "HIGH"
            recommendation = "flag_urgent"
        elif risk_score >= 45:
            level = "MEDIUM"
            recommendation = "review"
        else:
            level = "LOW"
            recommendation = "approve"

        return {
            "risk_score": risk_score,
            "risk_level": level,
            "recommendation": recommendation,
            "risk_factors": risk_factors,
        }
