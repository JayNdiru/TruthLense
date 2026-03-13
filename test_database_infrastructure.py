"""
Test Database Infrastructure
=============================
Verify that all database components are working correctly
"""

import sys
from datetime import datetime

def test_database_connection():
    """Test database connection"""
    print("\n" + "="*60)
    print("TEST 1: Database Connection")
    print("="*60)
    
    try:
        from database_config import get_database, close_database
        
        # Test SQLite (always available)
        print("\n📝 Testing SQLite connection...")
        db = get_database('sqlite')
        
        if db.test_connection():
            print("✅ SQLite connection successful")
            
            # Get health status
            health = db.get_health_status()
            print(f"   Status: {health['status']}")
            print(f"   Database size: {health.get('database_size', 'N/A')} MB")
        else:
            print("❌ SQLite connection failed")
            return False
        
        close_database()
        print("✅ Database closed successfully")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def test_basic_queries():
    """Test basic query operations"""
    print("\n" + "="*60)
    print("TEST 2: Basic Query Operations")
    print("="*60)
    
    try:
        from database_config import get_database
        
        db = get_database('sqlite')
        
        # Test SELECT query
        print("\n📝 Testing SELECT query...")
        results = db.execute_query(
            "SELECT name FROM sqlite_master WHERE type='table'",
            fetch='all'
        )
        print(f"✅ Found {len(results)} tables")
        
        # Test INSERT query
        print("\n📝 Testing INSERT query...")
        test_headline = f"Test Article {datetime.now().isoformat()}"
        db.execute_query(
            """INSERT INTO content_analysis 
               (content_hash, headline, source, credibility_score, classification, 
                is_fake, viral_velocity, shares, processed_at, signals_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            params=(
                str(hash(test_headline)),
                test_headline,
                'test.com',
                85.5,
                'real',
                0,
                0.3,
                100,
                datetime.now().isoformat(),
                '{"sensationalism": 0.1}'
            ),
            fetch='none'
        )
        print("✅ INSERT successful")
        
        # Verify insert
        print("\n📝 Verifying INSERT...")
        result = db.execute_query(
            "SELECT * FROM content_analysis WHERE headline = ?",
            params=(test_headline,),
            fetch='one'
        )
        if result:
            print("✅ Data verified in database")
        else:
            print("❌ Data not found")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_transactions():
    """Test transaction management"""
    print("\n" + "="*60)
    print("TEST 3: Transaction Management")
    print("="*60)
    
    try:
        from database_config import get_database
        
        db = get_database('sqlite')
        
        print("\n📝 Testing atomic transaction...")
        
        with db.transaction() as cursor:
            test_headline = f"Transaction Test {datetime.now().isoformat()}"
            cursor.execute(
                """INSERT INTO content_analysis 
                   (content_hash, headline, source, credibility_score, classification, 
                    is_fake, viral_velocity, shares, processed_at, signals_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(hash(test_headline)),
                    test_headline,
                    'transaction-test.com',
                    90.0,
                    'real',
                    0,
                    0.2,
                    50,
                    datetime.now().isoformat(),
                    '{"test": true}'
                )
            )
        
        print("✅ Transaction committed successfully")
        
        # Verify
        result = db.execute_query(
            "SELECT * FROM content_analysis WHERE source = ?",
            params=('transaction-test.com',),
            fetch='one'
        )
        
        if result:
            print("✅ Transaction data verified")
        else:
            print("❌ Transaction data not found")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        return False


def test_etl_pipeline():
    """Test ETL pipeline"""
    print("\n" + "="*60)
    print("TEST 4: ETL Pipeline")
    print("="*60)
    
    try:
        from database_config import get_database
        from etl_pipeline import ETLPipeline, DataLoader
        import json
        import tempfile
        import os
        
        db = get_database('sqlite')
        
        # Create sample JSON data
        print("\n📝 Creating sample data...")
        sample_data = [
            {
                'headline': 'ETL Test Article 1',
                'source': 'etl-test.com',
                'url': 'https://etl-test.com/1'
            },
            {
                'headline': 'ETL Test Article 2',
                'source': 'etl-test.com',
                'url': 'https://etl-test.com/2'
            }
        ]
        
        # Write to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(sample_data, f)
            temp_file = f.name
        
        try:
            # Create pipeline
            print("\n📝 Creating ETL pipeline...")
            from etl_pipeline import JSONDataSource
            
            pipeline = ETLPipeline("Test Pipeline")
            pipeline.set_source(JSONDataSource(temp_file))
            pipeline.set_loader(DataLoader(db))
            
            # Add transformation
            def add_timestamp(record):
                record['processed_at'] = datetime.now().isoformat()
                record['credibility_score'] = 85.0
                record['classification'] = 'real'
                record['is_fake'] = 0
                record['viral_velocity'] = 0.1
                record['shares'] = 10
                record['signals_json'] = '{"etl": true}'
                record['content_hash'] = str(hash(record['headline']))
                return record
            
            pipeline.add_transformation(add_timestamp)
            
            # Add validator
            pipeline.add_validator(lambda r: r.get('headline') and r.get('source'))
            
            # Run pipeline
            print("\n📝 Running pipeline...")
            metrics = pipeline.run({'table': 'content_analysis', 'mode': 'insert'})
            
            print(f"\n✅ Pipeline completed:")
            print(f"   Extracted: {metrics['records_extracted']} records")
            print(f"   Transformed: {metrics['records_transformed']} records")
            print(f"   Loaded: {metrics['records_loaded']} records")
            
            # Verify
            result = db.execute_query(
                "SELECT COUNT(*) as count FROM content_analysis WHERE source = ?",
                params=('etl-test.com',),
                fetch='one'
            )
            
            if result and result[0] >= 2:
                print("✅ ETL data verified in database")
                return True
            else:
                print("❌ ETL data not found")
                return False
                
        finally:
            # Cleanup
            os.unlink(temp_file)
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_export():
    """Test data export functionality"""
    print("\n" + "="*60)
    print("TEST 5: Data Export")
    print("="*60)
    
    try:
        from database_config import get_database
        from etl_pipeline import DataLoader
        import os
        import tempfile
        
        db = get_database('sqlite')
        loader = DataLoader(db)
        
        # Get some data
        print("\n📝 Fetching data for export...")
        results = db.execute_query(
            "SELECT headline, source, credibility_score FROM content_analysis LIMIT 5",
            fetch='all'
        )
        
        if not results:
            print("⚠️  No data to export, skipping test")
            return True
        
        # Convert to list of dicts
        data = []
        for row in results:
            if hasattr(row, 'keys'):
                data.append(dict(row))
            else:
                print("❌ Cannot convert results to dict")
                return False
        
        print(f"   Found {len(data)} records")
        
        # Test CSV export
        print("\n📝 Testing CSV export...")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            csv_file = f.name
        
        try:
            if loader.load_to_csv(data, csv_file):
                print("✅ CSV export successful")
                # Verify file exists
                if os.path.exists(csv_file):
                    size = os.path.getsize(csv_file)
                    print(f"   File size: {size} bytes")
                else:
                    print("❌ CSV file not created")
                    return False
            else:
                print("❌ CSV export failed")
                return False
        finally:
            if os.path.exists(csv_file):
                os.unlink(csv_file)
        
        # Test JSON export
        print("\n📝 Testing JSON export...")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json_file = f.name
        
        try:
            if loader.load_to_json(data, json_file):
                print("✅ JSON export successful")
                # Verify file exists
                if os.path.exists(json_file):
                    size = os.path.getsize(json_file)
                    print(f"   File size: {size} bytes")
                else:
                    print("❌ JSON file not created")
                    return False
            else:
                print("❌ JSON export failed")
                return False
        finally:
            if os.path.exists(json_file):
                os.unlink(json_file)
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("🧪 TESTING TRUTHLENS DATABASE INFRASTRUCTURE")
    print("="*60)
    
    tests = [
        ("Database Connection", test_database_connection),
        ("Basic Queries", test_basic_queries),
        ("Transactions", test_transactions),
        ("ETL Pipeline", test_etl_pipeline),
        ("Data Export", test_data_export)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n❌ {test_name} crashed: {e}")
            results[test_name] = False
    
    # Summary
    print("\n" + "="*60)
    print("📊 TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name:.<50} {status}")
    
    print("\n" + "-"*60)
    print(f"Total: {passed}/{total} tests passed")
    print("="*60)
    
    if passed == total:
        print("\n🎉 All tests passed! Database infrastructure is ready.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
