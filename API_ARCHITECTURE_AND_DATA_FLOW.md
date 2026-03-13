# TruthLens API Architecture, Data Flow & Live Data Connections

## Table of Contents

1. [Live Data Source Status](#1-live-data-source-status)
2. [API Endpoints](#2-api-endpoints)
3. [Link Scrutiny Pipeline (NEW)](#3-link-scrutiny-pipeline)
4. [Data Flow: Live Sources → Engine → Database](#4-data-flow-live-sources--engine--database)
5. [Database Schema](#5-database-schema)
6. [Configuration & API Keys](#6-configuration--api-keys)
7. [Architecture Diagram](#7-architecture-diagram)

---

## 1. Live Data Source Status

TruthLens connects to **7 real, live data sources**. Three work immediately with no configuration. Four more activate when you add free API keys to the `.env` file.

### Active NOW (no key needed)

**Fact-Check RSS Feeds** — `live_data_sources.py → RSSFactCheckFetcher`
- Pulls real fact-checks from PolitiFact, FactCheck.org, and Snopes via RSS
- Auto-syncs on startup and every 30 minutes via background thread
- Data flows into `fact_checks` table in SQLite
- No API key required, no rate limit

**Wayback Machine (Internet Archive)** — `live_data_sources.py → WaybackMachineAPI`
- Checks if a URL has been archived, retrieves archive timestamps
- Used during link scrutiny to verify URL history
- Endpoint: `https://archive.org/wayback/available`
- No API key required, no rate limit

**URL Content Extractor** — `live_data_sources.py → URLContentExtractor`
- Fetches any URL and extracts: headline, body text, author, publish date, outbound links
- Uses `requests` + `BeautifulSoup` (HTML parsing)
- Core of the link scrutiny pipeline (Step 1)
- No API key required

### Activate with free API key

**Google Fact Check Tools API** — `live_data_sources.py → GoogleFactCheckAPI`
- Searches Google's aggregated fact-check database (ClaimReview markup from 100+ publishers)
- Signup: https://console.cloud.google.com/ → Enable "Fact Check Tools API"
- Free tier: 10,000 queries/day
- Set: `GOOGLE_FACTCHECK_API_KEY` in `.env`

**Google Safe Browsing API** — `live_data_sources.py → GoogleSafeBrowsingAPI`
- Checks URLs against Google's threat lists (malware, phishing, social engineering)
- Signup: https://console.cloud.google.com/ → Enable "Safe Browsing API"
- Free tier: 10,000 lookups/day
- Set: `GOOGLE_SAFEBROWSING_API_KEY` in `.env`

**NewsAPI.org** — `live_data_sources.py → NewsAPIClient`
- Searches 80,000+ news sources to cross-reference stories
- Used to verify if credible outlets are covering the same story
- Signup: https://newsapi.org/register
- Free tier: 100 requests/day
- Set: `NEWSAPI_KEY` in `.env`

**VirusTotal** — `live_data_sources.py → VirusTotalAPI`
- Scans URLs against 70+ security engines for malware/phishing
- Signup: https://www.virustotal.com/gui/join-us
- Free tier: 4 lookups/minute
- Set: `VIRUSTOTAL_API_KEY` in `.env`

---

## 2. API Endpoints

The Flask API runs on `http://localhost:8080` with 9 endpoints:

### Core Analysis

**POST /api/analyze** — Analyze content directly
```json
Body: {
  "content": "Article text",
  "headline": "Title",
  "source": "publisher.com",
  "url": "https://...",
  "metadata": { "shares": 1000, "likes": 500, "comments": 100 }
}
```
Returns: credibility_score, classification, signals, viral_metrics, fact_checks, recommendation

**POST /api/scrutinize-link** — Full link scrutiny via live data (NEW)
```json
Body: { "url": "https://example.com/suspicious-article" }
```
Returns: Comprehensive report from all 7 data sources (see Section 3)

### Dashboard Data

**GET /api/stats** — Summary statistics (total analyzed, fake detected, accuracy)

**GET /api/recent?limit=20** — Recent analyses from `content_analysis` table

**GET /api/sources** — Source credibility ratings (38+ domains in database)

**GET /api/fact-checks** — Fact-check database (seed data + live RSS data)

**GET /api/competitors** — Competitor comparison (TruthLens vs NewsGuard, Factmata, etc.)

**GET /api/data-sources** — Real live data source connection status (not simulated)
- Returns actual `available` status for each source
- Reports missing API keys
- Shows `fact_checks_in_db` and `source_ratings_in_db` counts

**GET /api/engine-metrics** — Engine performance metrics

---

## 3. Link Scrutiny Pipeline

The new `POST /api/scrutinize-link` endpoint runs a URL through a 7-step pipeline using all available live data sources.

### Pipeline Steps

```
POST /api/scrutinize-link  { "url": "https://..." }
         │
         ▼
Step 1: URL Content Extraction ──── requests + BeautifulSoup
         │  → headline, body, author, date, outbound links
         ▼
Step 2: Google Safe Browsing ────── Is URL flagged as malware/phishing?
         │  (skipped if no API key)
         ▼
Step 3: VirusTotal Scan ────────── 70+ security engines check URL
         │  (skipped if no API key)
         ▼
Step 4: Fact-Check Search ──────── Google Fact Check API + local RSS DB
         │  → matching claims, verdicts, sources
         ▼
Step 5: Wayback Machine ────────── Is URL archived? When was it first seen?
         │
         ▼
Step 6: News Cross-Reference ───── NewsAPI.org: are credible outlets covering this?
         │  (skipped if no API key)
         ▼
Step 7: NLP Engine Analysis ────── BERT/keyword credibility scoring
         │  → signals, score, classification
         ▼
Risk Aggregation ───────────────── Combine all signals → risk_score (0-100)
         │                          risk_level: LOW / MEDIUM / HIGH
         ▼                          recommendation: approve / review / flag_urgent
    Full Report (JSON)
```

### Example Response

```json
{
  "success": true,
  "data": {
    "url": "https://example.com/article",
    "domain": "example.com",
    "scrutinized_at": "2026-03-13T19:10:00Z",
    "sources_checked": 5,
    "processing_time_ms": 2340,
    "page_content": {
      "headline": "Article Title",
      "word_count": 1200,
      "outbound_links_count": 8,
      "fetched": true
    },
    "safe_browsing": { "checked": true, "safe": true, "threats": [] },
    "virustotal": { "scanned": true, "malicious": 0, "harmless": 65 },
    "fact_check_results": {
      "searched": true,
      "matches_found": 1,
      "matches": [{ "claim": "...", "verdict": "FALSE", "source": "PolitiFact" }]
    },
    "wayback_archive": { "archived": true, "archive_timestamp": "20260101..." },
    "news_crossref": { "articles_found": 3, "credible_coverage": 3 },
    "engine_analysis": {
      "credibility_score": 82.5,
      "classification": "real",
      "signals": { "sensationalism": 0.1, "source_credibility": 0.9 }
    },
    "overall_risk": {
      "risk_score": 25,
      "risk_level": "LOW",
      "recommendation": "approve",
      "risk_factors": ["High credibility score: 82.5/100"]
    }
  }
}
```

---

## 4. Data Flow: Live Sources → Engine → Database

### Startup Sequence

```
Server starts (truthlens_api.py)
  │
  ├── Engine initializes (truthlens_engine.py)
  │     ├── Create SQLite tables (if not exist)
  │     ├── Load seed fact-checks (5 baseline entries)
  │     ├── Load seed source ratings (8 baseline entries)
  │     ├── sync_live_fact_checks()  ←── LIVE: Pull from PolitiFact, FactCheck.org, Snopes RSS
  │     │     └── INSERT OR IGNORE into fact_checks table (typically 60-90 new entries)
  │     ├── sync_extended_source_ratings()  ←── Load 30 additional source ratings
  │     └── Load BERT models (if transformers installed)
  │
  ├── LiveDataSourceRegistry initializes
  │     └── 7 connectors created, each checks for API keys in env
  │
  ├── RSS sync thread starts (every 30 minutes)
  │     └── Calls engine.sync_live_fact_checks() periodically
  │
  └── Content simulator thread starts (every 5-15 seconds)
```

### Analysis Data Path

```
Input (POST /api/analyze or simulator)
  │
  └──▶ engine.analyze_content(data)
         ├── _calculate_signals()         → 5 NLP signals (BERT or keyword)
         ├── _calculate_viral_metrics()   → engagement analysis
         ├── _match_fact_checks()         → search against DB (now has live RSS data)
         ├── _aggregate_credibility()     → weighted score 0-100
         ├── _classify()                  → real/fake/uncertain
         ├── _recommend()                 → approve/flag/review
         └── _store_result()              → INSERT INTO content_analysis
```

### Scrutiny Data Path

```
Input (POST /api/scrutinize-link)
  │
  └──▶ scrutinizer.scrutinize(url)
         ├── Step 1: url_extractor.extract(url)       → fetch page content
         ├── Step 2: safe_browsing.check_url(url)     → Google threat check
         ├── Step 3: virustotal.scan_url(url)          → malware scan
         ├── Step 4: google_factcheck.search_claim()   → claim search
         │           + local DB keyword search         → RSS-synced fact-checks
         ├── Step 5: wayback.check_url(url)            → archive history
         ├── Step 6: newsapi.search_articles()          → cross-reference
         ├── Step 7: engine.analyze_content()           → NLP analysis → DB INSERT
         └── _compute_overall_risk()                   → aggregate risk score
```

---

## 5. Database Schema

### content_analysis (primary data sink)
```sql
CREATE TABLE content_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT UNIQUE,
    headline TEXT, source TEXT, url TEXT,
    credibility_score REAL,      -- 0-100
    classification TEXT,          -- real/fake/uncertain
    is_fake INTEGER,             -- 0 or 1
    viral_velocity REAL,         -- 0-1
    shares INTEGER,
    processed_at TIMESTAMP,
    signals_json TEXT             -- JSON of 5 signal scores
);
```

### fact_checks (live RSS data + seeds)
```sql
CREATE TABLE fact_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim TEXT, verdict TEXT, source TEXT, url TEXT,
    date_checked TIMESTAMP
);
-- Populated on startup from:
--   1. 5 hardcoded seed entries
--   2. ~60-90 live entries from PolitiFact, FactCheck.org, Snopes RSS
--   3. Refreshed every 30 minutes by background thread
```

### source_ratings (38+ domains)
```sql
CREATE TABLE source_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_domain TEXT UNIQUE,
    credibility_rating REAL,     -- 0-100
    category TEXT,               -- News, Science, Conspiracy, Propaganda, etc.
    bias_score REAL,             -- 0-1
    fact_check_history TEXT
);
-- 8 seed entries + 30 extended entries loaded on startup
-- Covers: reuters, bbc, nasa, nytimes, apnews, nature, cdc, who,
--         infowars, breitbart, rt.com, naturalnews, and more
```

### metrics (unused — reserved for future)
```sql
CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP, total_analyzed INTEGER,
    fake_detected INTEGER, avg_credibility REAL, avg_response_time REAL
);
```

---

## 6. Configuration & API Keys

### .env file (in project root)

```bash
# Works immediately — no key needed:
# - PolitiFact RSS, FactCheck.org RSS, Snopes RSS
# - Wayback Machine API
# - URL Content Extractor

# Free API keys (sign up at the URLs below):
GOOGLE_FACTCHECK_API_KEY=       # https://console.cloud.google.com/
GOOGLE_SAFEBROWSING_API_KEY=    # https://console.cloud.google.com/
NEWSAPI_KEY=                     # https://newsapi.org/register
VIRUSTOTAL_API_KEY=              # https://www.virustotal.com/gui/join-us
```

### How to activate key-based sources

1. Sign up at the URL listed next to each key
2. Copy the API key
3. Paste it into `.env` in the project root
4. Restart the server: `python3 truthlens_api.py`
5. Check `GET /api/data-sources` to verify the source shows `"available": true`

### Dependencies

```bash
pip install flask flask-cors requests beautifulsoup4 feedparser python-dotenv

# Optional (for BERT-based NLP instead of keyword fallback):
pip install transformers sentence-transformers torch
```

---

## 7. Architecture Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                    LIVE DATA SOURCES                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  [NO KEY]  PolitiFact RSS ─────┐                             │
│  [NO KEY]  FactCheck.org RSS ──┤── RSSFactCheckFetcher       │
│  [NO KEY]  Snopes RSS ─────────┘     │                       │
│                                      ▼                       │
│                              fact_checks table               │
│                              (auto-sync every 30 min)        │
│                                                              │
│  [NO KEY]  Wayback Machine ────── Archive history check      │
│  [NO KEY]  URL Extractor ──────── Page content parsing       │
│                                                              │
│  [KEY]  Google Fact Check ─────── ClaimReview search         │
│  [KEY]  Google Safe Browsing ──── Threat detection           │
│  [KEY]  NewsAPI.org ───────────── News cross-reference       │
│  [KEY]  VirusTotal ────────────── URL malware scan           │
│                                                              │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                     FLASK API (port 8080)                     │
├──────────────────────────────────────────────────────────────┤
│  POST /api/scrutinize-link ── LinkScrutinizer pipeline       │
│  POST /api/analyze ────────── Direct content analysis        │
│  GET  /api/data-sources ───── Real source status             │
│  GET  /api/stats, /recent, /sources, /fact-checks, etc.      │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│              TruthLensAnalyticsEngine                         │
├──────────────────────────────────────────────────────────────┤
│  NLP Analysis (BERT zero-shot / keyword fallback)            │
│  Signal Detection: sensationalism, emotional, source cred    │
│  Fact-Check Matching: semantic similarity / keyword overlap  │
│  Credibility Scoring: weighted aggregation → 0-100           │
│  Classification: real / fake / uncertain                     │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                   SQLite Database (truthlens.db)              │
├──────────────────────────────────────────────────────────────┤
│  content_analysis  │ Every analyzed article stored here      │
│  fact_checks       │ Live RSS data + seeds (~95+ entries)    │
│  source_ratings    │ 38+ domains with credibility scores     │
│  metrics           │ Reserved for future use                 │
└──────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
TruthLense/
├── .env                          # API keys (edit this)
├── live_data_sources.py          # 7 real API connectors
├── link_scrutinizer.py           # URL scrutiny pipeline
├── truthlens_engine.py           # NLP engine (with live RSS sync)
├── truthlens_api.py              # Flask API (with /api/scrutinize-link)
├── database_config.py            # Multi-DB config (PostgreSQL/MySQL support)
├── etl_pipeline.py               # ETL framework
├── dashboard_template.html       # Web dashboard
├── truthlens.db                  # SQLite database
├── requirements.txt              # Python dependencies
└── API_ARCHITECTURE_AND_DATA_FLOW.md  # This file
```
