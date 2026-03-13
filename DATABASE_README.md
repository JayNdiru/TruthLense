# TruthLens Database Infrastructure

## Overview

Comprehensive backend database infrastructure with support for multiple databases, connection pooling, and ETL pipelines.

## Features

- ✅ **Multi-Database Support**: SQLite, PostgreSQL, MySQL
- ✅ **Connection Pooling**: Efficient connection management
- ✅ **ETL Pipelines**: Extract, Transform, Load framework
- ✅ **Transaction Management**: ACID-compliant operations  
- ✅ **Health Monitoring**: Database health checks
- ✅ **Data Import/Export**: CSV, JSON, SQL support

## Architecture

```
TruthLens Database Infrastructure
│
├── database_config.py        # Connection management & pooling
├── etl_pipeline.py           # ETL pipeline framework
├── truthlens_engine.py       # Analytics engine
└── truthlens_api.py          # REST API layer
```

## Quick Start

### 1. Install Dependencies

```bash
# Core dependencies (already included)
pip install flask flask-cors

# Optional: PostgreSQL support
pip install psycopg2-binary

# Optional: MySQL support
pip install mysql-connector-python

# Optional: For API data sources
pip install requests
```

### 2. Configuration

Set environment variables for database connection:

```bash
# Use SQLite (default - no configuration needed)
export DB_TYPE=sqlite

# Or use PostgreSQL
export DB_TYPE=postgresql
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=truthlens
export DB_USER=truthlens_user
export DB_PASSWORD=your_password

# Or use MySQL
export DB_TYPE=mysql
export DB_HOST=localhost
export DB_PORT=3306
export DB_NAME=truthlens
export DB_USER=truthlens_user
export DB_PASSWORD=your_password
```

### 3. Test Database Connection

```python
from database_config import get_database

# Test connection
db = get_database('sqlite')  # or 'postgresql', 'mysql'
health = db.get_health_status()
print(f"Database status: {health}")
```

## Database Connection Usage

### Basic Query Execution

```python
from database_config import get_database

db = get_database()

# Execute simple query
results = db.execute_query(
    "SELECT * FROM content_analysis WHERE credibility_score > ?",
    params=(70,),
    fetch='all'
)

# Execute insert/update
db.execute_query(
    "INSERT INTO content_analysis (headline, source) VALUES (?, ?)",
    params=("Test Headline", "test.com"),
    fetch='none'
)
```

### Using Connection Context Manager

```python
# Safe connection management
with db.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM content_analysis")
    results = cursor.fetchall()
    cursor.close()
```

### Using Transactions

```python
# Atomic transactions
with db.transaction() as cursor:
    cursor.execute("INSERT INTO content_analysis (...) VALUES (...)")
    cursor.execute("UPDATE metrics SET total_analyzed = total_analyzed + 1")
    # Auto-commit on success, auto-rollback on error
```

## ETL Pipeline Usage

### Extract Data from API

```python
from etl_pipeline import ETLPipeline, APIDataSource, DataLoader
from database_config import get_database

db = get_database()

# Create pipeline
pipeline = ETLPipeline("News API Import")

# Set API source
source = APIDataSource(
    url="https://newsapi.org/v2/top-headlines",
    params={"apiKey": "YOUR_API_KEY", "country": "us"}
)
pipeline.set_source(source)

# Add transformations
def normalize(record):
    return {
        'headline': record.get('title', ''),
        'content': record.get('description', ''),
        'source': record.get('source', {}).get('name', ''),
        'url': record.get('url', ''),
        'publish_date': record.get('publishedAt', '')
    }

pipeline.add_transformation(normalize)

# Set loader
pipeline.set_loader(DataLoader(db))

# Run pipeline
metrics = pipeline.run({'table': 'content_analysis', 'mode': 'insert'})
print(f"Loaded {metrics['records_loaded']} records")
```

### Import from CSV

```python
from etl_pipeline import ETLPipeline, CSVDataSource, DataLoader

pipeline = ETLPipeline("CSV Import")
pipeline.set_source(CSVDataSource('data.csv'))
pipeline.set_loader(DataLoader(db))

# Add validator
pipeline.add_validator(lambda r: r.get('headline') and r.get('source'))

# Run
metrics = pipeline.run({'table': 'content_analysis', 'mode': 'insert'})
```

### Import from JSON

```python
from etl_pipeline import JSONDataSource

pipeline = ETLPipeline("JSON Import")
pipeline.set_source(JSONDataSource('data.json'))
pipeline.set_loader(DataLoader(db))

metrics = pipeline.run({'table': 'content_analysis', 'mode': 'insert'})
```

### Export to CSV/JSON

```python
# Export database records to CSV
loader = DataLoader(db)
data = db.execute_query("SELECT * FROM content_analysis", fetch='all')
loader.load_to_csv(data, 'export.csv')

# Export to JSON
loader.load_to_json(data, 'export.json')
```

## Database Schema

### Content Analysis Table

```sql
CREATE TABLE content_analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT UNIQUE,
    headline TEXT,
    source TEXT,
    url TEXT,
    credibility_score REAL,
    classification TEXT,
    is_fake INTEGER,
    viral_velocity REAL,
    shares INTEGER,
    processed_at TIMESTAMP,
    signals_json TEXT
);
```

### Source Ratings Table

```sql
CREATE TABLE source_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_domain TEXT UNIQUE,
    credibility_rating REAL,
    category TEXT,
    bias_score REAL,
    fact_check_history TEXT
);
```

### Fact Checks Table

```sql
CREATE TABLE fact_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim TEXT,
    verdict TEXT,
    source TEXT,
    url TEXT,
    date_checked TIMESTAMP
);
```

## Production Setup

### PostgreSQL Setup

```bash
# Install PostgreSQL
# macOS: brew install postgresql
# Ubuntu: sudo apt-get install postgresql

# Create database and user
psql postgres
CREATE DATABASE truthlens;
CREATE USER truthlens_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE truthlens TO truthlens_user;
\q

# Set environment variables
export DB_TYPE=postgresql
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=truthlens
export DB_USER=truthlens_user
export DB_PASSWORD=secure_password

# Run schema migration
python3 database_config.py  # Will test connection
```

### MySQL Setup

```bash
# Install MySQL
# macOS: brew install mysql
# Ubuntu: sudo apt-get install mysql-server

# Create database and user
mysql -u root -p
CREATE DATABASE truthlens CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'truthlens_user'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON truthlens.* TO 'truthlens_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;

# Set environment variables
export DB_TYPE=mysql
export DB_HOST=localhost
export DB_PORT=3306
export DB_NAME=truthlens
export DB_USER=truthlens_user
export DB_PASSWORD=secure_password
```

## Performance Tuning

### Connection Pooling

Adjust pool size based on your workload:

```python
# In database_config.py, modify CONFIGS:
'postgresql': {
    ...
    'pool_size': 20,      # Increase for high concurrency
    'max_overflow': 40,
    'pool_timeout': 60
}
```

### Batch Operations

Use bulk inserts for better performance:

```python
# Instead of single inserts
data_tuples = [
    ('headline1', 'source1', 85.5),
    ('headline2', 'source2', 72.3),
    # ... thousands more
]

db.execute_many(
    "INSERT INTO content_analysis (headline, source, credibility_score) VALUES (?, ?, ?)",
    data_tuples
)
```

### Indexing

Add indexes for frequently queried columns:

```sql
-- For fast credibility lookups
CREATE INDEX idx_credibility ON content_analysis(credibility_score);

-- For timestamp-based queries
CREATE INDEX idx_processed_at ON content_analysis(processed_at);

-- For source lookups
CREATE INDEX idx_source ON content_analysis(source);
```

## Monitoring & Health Checks

```python
# Check database health
health = db.get_health_status()
print(f"""
Database Type: {health['type']}
Status: {health['status']}
Size: {health.get('database_size', 'N/A')} MB
Timestamp: {health['timestamp']}
""")

# Test connection
if db.test_connection():
    print("✅ Database is healthy")
else:
    print("❌ Database connection failed")
```

## Backup & Recovery

### SQLite Backup

```bash
# Backup SQLite database
cp truthlens.db truthlens_backup_$(date +%Y%m%d_%H%M%S).db

# Or use SQLite backup command
sqlite3 truthlens.db ".backup truthlens_backup.db"
```

### PostgreSQL Backup

```bash
# Dump database
pg_dump -U truthlens_user -d truthlens -F c -f truthlens_backup.dump

# Restore
pg_restore -U truthlens_user -d truthlens truthlens_backup.dump
```

### MySQL Backup

```bash
# Dump database
mysqldump -u truthlens_user -p truthlens > truthlens_backup.sql

# Restore
mysql -u truthlens_user -p truthlens < truthlens_backup.sql
```

## Troubleshooting

### Connection Issues

```python
# Check if database is reachable
from database_config import get_database

try:
    db = get_database('postgresql')
    print("✅ Connected successfully")
except Exception as e:
    print(f"❌ Connection failed: {e}")
```

### Permission Errors

```bash
# PostgreSQL: Grant permissions
psql -U postgres
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO truthlens_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO truthlens_user;
```

### Performance Issues

```python
# Check connection pool status (PostgreSQL)
with db.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pg_stat_activity")
    print(cursor.fetchall())
```

## API Integration

The database infrastructure is already integrated with the TruthLens API:

```python
# In truthlens_api.py
from database_config import get_database

db = get_database()  # Uses environment variable DB_TYPE

# All API endpoints now use the unified database connection
```

## Best Practices

1. **Always use context managers** for connections
2. **Use transactions** for multi-step operations
3. **Implement retry logic** for production systems
4. **Monitor database health** regularly
5. **Backup regularly** (automate with cron)
6. **Use connection pooling** for high-traffic applications
7. **Index frequently queried columns**
8. **Validate data** before loading into database

## Example: Complete ETL Workflow

```python
from database_config import get_database
from etl_pipeline import (
    ETLPipeline, APIDataSource, CSVDataSource, 
    DataLoader, create_content_analysis_pipeline
)

# Initialize database
db = get_database('postgresql')  # or 'sqlite', 'mysql'

# Create and run pipeline
source_config = {
    'type': 'api',
    'url': 'https://api.example.com/content',
    'headers': {'Authorization': 'Bearer TOKEN'}
}

pipeline = create_content_analysis_pipeline(db, source_config)
metrics = pipeline.run({'table': 'content_analysis', 'mode': 'insert'})

print(f"""
ETL Pipeline Results:
- Extracted: {metrics['records_extracted']} records
- Transformed: {metrics['records_transformed']} records
- Loaded: {metrics['records_loaded']} records
- Duration: {(metrics['end_time'] - metrics['start_time']).total_seconds():.2f}s
""")
```

## Support

For issues or questions:
1. Check logs in console output
2. Verify environment variables are set correctly
3. Test connection with `database_config.py`
4. Review error messages for specific database errors

## License

Part of TruthLens AI Platform
