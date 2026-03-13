# TruthLens Database Infrastructure - Quick Start

## ✅ Installation Complete

Your backend database infrastructure is now ready! All 5 tests passed successfully.

## 📁 New Files Created

1. **`database_config.py`** - Database connection manager (355 lines)
   - Multi-database support (SQLite, PostgreSQL, MySQL)
   - Connection pooling
   - Transaction management
   - Health monitoring

2. **`etl_pipeline.py`** - ETL pipeline framework (554 lines)
   - Data extraction (API, CSV, JSON, Database)
   - Data transformation & validation
   - Data loading & export

3. **`DATABASE_README.md`** - Complete documentation (504 lines)
   - Usage examples
   - Production setup guides
   - Troubleshooting

4. **`test_database_infrastructure.py`** - Test suite (399 lines)
   - 5 comprehensive tests
   - All passing ✅

## 🚀 Quick Usage Examples

### Connect to Database

```python
from database_config import get_database

# Use SQLite (default)
db = get_database('sqlite')

# Or PostgreSQL (set environment variables first)
db = get_database('postgresql')
```

### Execute Queries

```python
# SELECT
results = db.execute_query(
    "SELECT * FROM content_analysis WHERE credibility_score > ?",
    params=(70,),
    fetch='all'
)

# INSERT
db.execute_query(
    "INSERT INTO content_analysis (headline, source) VALUES (?, ?)",
    params=("Breaking News", "news.com"),
    fetch='none'
)
```

### Use Transactions

```python
with db.transaction() as cursor:
    cursor.execute("INSERT INTO content_analysis (...) VALUES (...)")
    cursor.execute("UPDATE metrics SET total_analyzed = total_analyzed + 1")
    # Auto-commit on success, auto-rollback on error
```

### ETL Pipeline - Import from CSV

```python
from etl_pipeline import ETLPipeline, CSVDataSource, DataLoader

pipeline = ETLPipeline("CSV Import")
pipeline.set_source(CSVDataSource('data.csv'))
pipeline.set_loader(DataLoader(db))

# Add transformation
pipeline.add_transformation(lambda r: {
    **r,
    'processed_at': datetime.now().isoformat()
})

# Add validation
pipeline.add_validator(lambda r: r.get('headline') and r.get('source'))

# Run
metrics = pipeline.run({'table': 'content_analysis', 'mode': 'insert'})
print(f"Loaded {metrics['records_loaded']} records")
```

### ETL Pipeline - Import from API

```python
from etl_pipeline import APIDataSource

pipeline = ETLPipeline("API Import")
source = APIDataSource(
    url="https://api.example.com/news",
    headers={"Authorization": "Bearer YOUR_TOKEN"}
)
pipeline.set_source(source)
pipeline.set_loader(DataLoader(db))

metrics = pipeline.run({'table': 'content_analysis', 'mode': 'insert'})
```

### Export Data

```python
from etl_pipeline import DataLoader

loader = DataLoader(db)

# Export to CSV
data = db.execute_query("SELECT * FROM content_analysis", fetch='all')
data_dicts = [dict(row) for row in data]
loader.load_to_csv(data_dicts, 'export.csv')

# Export to JSON
loader.load_to_json(data_dicts, 'export.json')
```

## 🔧 Configuration

### Environment Variables

```bash
# Database type (default: sqlite)
export DB_TYPE=sqlite

# PostgreSQL
export DB_TYPE=postgresql
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=truthlens
export DB_USER=truthlens_user
export DB_PASSWORD=your_password

# MySQL
export DB_TYPE=mysql
export DB_HOST=localhost
export DB_PORT=3306
export DB_NAME=truthlens
export DB_USER=truthlens_user
export DB_PASSWORD=your_password
```

## 🧪 Run Tests

```bash
python3 test_database_infrastructure.py
```

Expected output:
```
Total: 5/5 tests passed
🎉 All tests passed! Database infrastructure is ready.
```

## 📊 Database Schema

### Content Analysis Table
- `id` - Primary key
- `content_hash` - Unique hash
- `headline` - Article headline
- `source` - Source domain
- `url` - Article URL
- `credibility_score` - Score (0-100)
- `classification` - real/fake/uncertain
- `is_fake` - Boolean flag
- `viral_velocity` - Spread rate
- `shares` - Social shares
- `processed_at` - Timestamp
- `signals_json` - Detection signals (JSON)

### Source Ratings Table
- Source credibility ratings
- Bias scores
- Categories

### Fact Checks Table
- Verified fact-checks
- Verdicts
- Sources

## 🔄 Migrate to Production Database

### PostgreSQL Setup

```bash
# 1. Install PostgreSQL
brew install postgresql  # macOS

# 2. Create database
psql postgres
CREATE DATABASE truthlens;
CREATE USER truthlens_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE truthlens TO truthlens_user;
\q

# 3. Set environment variables
export DB_TYPE=postgresql
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=truthlens
export DB_USER=truthlens_user
export DB_PASSWORD=secure_password

# 4. Install Python driver
pip install psycopg2-binary

# 5. Run your app - it will auto-detect PostgreSQL!
python3 truthlens_api.py
```

### MySQL Setup

```bash
# 1. Install MySQL
brew install mysql  # macOS

# 2. Create database
mysql -u root -p
CREATE DATABASE truthlens;
CREATE USER 'truthlens_user'@'localhost' IDENTIFIED BY 'secure_password';
GRANT ALL PRIVILEGES ON truthlens.* TO 'truthlens_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;

# 3. Set environment variables
export DB_TYPE=mysql
export DB_HOST=localhost
export DB_PORT=3306
export DB_NAME=truthlens
export DB_USER=truthlens_user
export DB_PASSWORD=secure_password

# 4. Install Python driver
pip install mysql-connector-python

# 5. Run your app
python3 truthlens_api.py
```

## 💡 Best Practices

1. **Always use context managers** for connections
2. **Use transactions** for multi-step operations
3. **Validate data** before inserting
4. **Monitor database health** regularly
5. **Backup regularly** (daily recommended)
6. **Use connection pooling** for production
7. **Index frequently queried columns**

## 📚 Documentation

- **Full Documentation**: See `DATABASE_README.md` (504 lines)
- **Code Examples**: See test file `test_database_infrastructure.py`
- **API Reference**: See docstrings in `database_config.py` and `etl_pipeline.py`

## 🛠️ Troubleshooting

### Test Connection
```python
from database_config import get_database

db = get_database('sqlite')
health = db.get_health_status()
print(f"Status: {health['status']}")
```

### Check Database Size
```python
health = db.get_health_status()
print(f"Database size: {health.get('database_size', 'N/A')} MB")
```

### View Logs
All operations are logged. Check console output for detailed information.

## 🎯 Next Steps

1. ✅ **Database infrastructure is ready**
2. 📊 **Run the TruthLens app**: `python3 truthlens_api.py`
3. 🌐 **Open dashboard**: http://localhost:8080
4. 📥 **Import your data** using ETL pipelines
5. 🚀 **Deploy to production** with PostgreSQL/MySQL

## 💬 Support

- Review `DATABASE_README.md` for detailed documentation
- Run tests to verify setup: `python3 test_database_infrastructure.py`
- Check logs for error messages

---

**🎉 Your database infrastructure is ready for production!**
