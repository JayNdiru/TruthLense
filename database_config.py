"""
TruthLens Database Configuration & Connection Management
========================================================
Supports: SQLite (development), PostgreSQL (production), MySQL

Features:
- Multi-database backend support
- Connection pooling
- Automatic failover
- Health monitoring
- Transaction management
"""

import os
import sqlite3
import json
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseConfig:
    """Database configuration management"""
    
    # Default configurations
    CONFIGS = {
        'sqlite': {
            'type': 'sqlite',
            'database': 'truthlens.db',
            'timeout': 30.0,
            'check_same_thread': False
        },
        'postgresql': {
            'type': 'postgresql',
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 5432)),
            'database': os.getenv('DB_NAME', 'truthlens'),
            'user': os.getenv('DB_USER', 'truthlens_user'),
            'password': os.getenv('DB_PASSWORD', ''),
            'pool_size': 10,
            'max_overflow': 20,
            'pool_timeout': 30
        },
        'mysql': {
            'type': 'mysql',
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': int(os.getenv('DB_PORT', 3306)),
            'database': os.getenv('DB_NAME', 'truthlens'),
            'user': os.getenv('DB_USER', 'truthlens_user'),
            'password': os.getenv('DB_PASSWORD', ''),
            'charset': 'utf8mb4',
            'pool_size': 10
        }
    }
    
    @classmethod
    def get_config(cls, db_type: str = None) -> Dict[str, Any]:
        """Get database configuration"""
        if db_type is None:
            db_type = os.getenv('DB_TYPE', 'sqlite')
        
        if db_type not in cls.CONFIGS:
            raise ValueError(f"Unsupported database type: {db_type}")
        
        return cls.CONFIGS[db_type].copy()


class DatabaseConnection:
    """Database connection manager with pooling support"""
    
    def __init__(self, db_type: str = None):
        """
        Initialize database connection
        
        Args:
            db_type: Database type (sqlite, postgresql, mysql)
        """
        self.config = DatabaseConfig.get_config(db_type)
        self.db_type = self.config['type']
        self.connection = None
        self.pool = None
        
        logger.info(f"Initializing {self.db_type} database connection...")
        self._initialize_connection()
    
    def _initialize_connection(self):
        """Initialize database connection based on type"""
        if self.db_type == 'sqlite':
            self._init_sqlite()
        elif self.db_type == 'postgresql':
            self._init_postgresql()
        elif self.db_type == 'mysql':
            self._init_mysql()
        else:
            raise ValueError(f"Unsupported database: {self.db_type}")
    
    def _init_sqlite(self):
        """Initialize SQLite connection"""
        try:
            db_path = self.config['database']
            self.connection = sqlite3.connect(
                db_path,
                timeout=self.config['timeout'],
                check_same_thread=self.config['check_same_thread']
            )
            self.connection.row_factory = sqlite3.Row
            logger.info(f"✅ SQLite connected: {db_path}")
        except Exception as e:
            logger.error(f"❌ SQLite connection failed: {e}")
            raise
    
    def _init_postgresql(self):
        """Initialize PostgreSQL connection with pooling"""
        try:
            import psycopg2
            from psycopg2 import pool
            
            self.pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=self.config['pool_size'],
                host=self.config['host'],
                port=self.config['port'],
                database=self.config['database'],
                user=self.config['user'],
                password=self.config['password']
            )
            logger.info(f"✅ PostgreSQL pool created: {self.config['host']}:{self.config['port']}/{self.config['database']}")
        except ImportError:
            logger.error("❌ psycopg2 not installed. Run: pip install psycopg2-binary")
            raise
        except Exception as e:
            logger.error(f"❌ PostgreSQL connection failed: {e}")
            raise
    
    def _init_mysql(self):
        """Initialize MySQL connection with pooling"""
        try:
            import mysql.connector
            from mysql.connector import pooling
            
            self.pool = pooling.MySQLConnectionPool(
                pool_name="truthlens_pool",
                pool_size=self.config['pool_size'],
                host=self.config['host'],
                port=self.config['port'],
                database=self.config['database'],
                user=self.config['user'],
                password=self.config['password'],
                charset=self.config['charset']
            )
            logger.info(f"✅ MySQL pool created: {self.config['host']}:{self.config['port']}/{self.config['database']}")
        except ImportError:
            logger.error("❌ mysql-connector-python not installed. Run: pip install mysql-connector-python")
            raise
        except Exception as e:
            logger.error(f"❌ MySQL connection failed: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """
        Get database connection (context manager)
        
        Usage:
            with db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM table")
        """
        conn = None
        try:
            if self.db_type == 'sqlite':
                conn = self.connection
                yield conn
            elif self.db_type in ['postgresql', 'mysql']:
                conn = self.pool.get_connection()
                yield conn
            else:
                raise ValueError(f"Unsupported database: {self.db_type}")
        except Exception as e:
            logger.error(f"Connection error: {e}")
            if conn and self.db_type != 'sqlite':
                conn.rollback()
            raise
        finally:
            if conn and self.db_type != 'sqlite':
                conn.close()
    
    @contextmanager
    def transaction(self):
        """
        Transaction context manager
        
        Usage:
            with db.transaction() as cursor:
                cursor.execute("INSERT INTO ...")
                cursor.execute("UPDATE ...")
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                yield cursor
                conn.commit()
                logger.debug("Transaction committed")
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction rolled back: {e}")
                raise
            finally:
                cursor.close()
    
    def execute_query(self, query: str, params: tuple = None, fetch: str = 'all') -> List[Any]:
        """
        Execute a query and return results
        
        Args:
            query: SQL query
            params: Query parameters
            fetch: 'all', 'one', or 'none'
        
        Returns:
            Query results
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if fetch == 'all':
                    return cursor.fetchall()
                elif fetch == 'one':
                    return cursor.fetchone()
                elif fetch == 'none':
                    conn.commit()
                    return []
                else:
                    raise ValueError(f"Invalid fetch type: {fetch}")
            finally:
                cursor.close()
    
    def execute_many(self, query: str, data: List[tuple]) -> int:
        """
        Execute query with multiple parameter sets
        
        Args:
            query: SQL query
            data: List of parameter tuples
        
        Returns:
            Number of rows affected
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.executemany(query, data)
                conn.commit()
                return cursor.rowcount
            finally:
                cursor.close()
    
    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if self.db_type == 'sqlite':
                    cursor.execute("SELECT 1")
                elif self.db_type == 'postgresql':
                    cursor.execute("SELECT 1")
                elif self.db_type == 'mysql':
                    cursor.execute("SELECT 1")
                cursor.close()
                logger.info("✅ Database connection test passed")
                return True
        except Exception as e:
            logger.error(f"❌ Database connection test failed: {e}")
            return False
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get database health status"""
        status = {
            'type': self.db_type,
            'status': 'unknown',
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            if self.test_connection():
                status['status'] = 'healthy'
                
                # Get database-specific metrics
                if self.db_type == 'sqlite':
                    status['database_size'] = os.path.getsize(self.config['database']) / (1024 * 1024)  # MB
                elif self.db_type == 'postgresql':
                    with self.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT pg_database_size(current_database())")
                        size = cursor.fetchone()[0] / (1024 * 1024)  # MB
                        status['database_size'] = round(size, 2)
                        cursor.close()
                elif self.db_type == 'mysql':
                    with self.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(f"SELECT SUM(data_length + index_length) / 1024 / 1024 FROM information_schema.tables WHERE table_schema = '{self.config['database']}'")
                        size = cursor.fetchone()[0]
                        status['database_size'] = round(size, 2) if size else 0
                        cursor.close()
            else:
                status['status'] = 'unhealthy'
        except Exception as e:
            status['status'] = 'error'
            status['error'] = str(e)
        
        return status
    
    def close(self):
        """Close database connections"""
        try:
            if self.db_type == 'sqlite' and self.connection:
                self.connection.close()
                logger.info("SQLite connection closed")
            elif self.pool:
                if hasattr(self.pool, 'closeall'):
                    self.pool.closeall()
                logger.info(f"{self.db_type} connection pool closed")
        except Exception as e:
            logger.error(f"Error closing connections: {e}")


# Singleton instance
_db_instance: Optional[DatabaseConnection] = None


def get_database(db_type: str = None) -> DatabaseConnection:
    """
    Get database connection singleton
    
    Args:
        db_type: Database type (sqlite, postgresql, mysql)
    
    Returns:
        DatabaseConnection instance
    """
    global _db_instance
    
    if _db_instance is None:
        _db_instance = DatabaseConnection(db_type)
    
    return _db_instance


def close_database():
    """Close global database connection"""
    global _db_instance
    
    if _db_instance:
        _db_instance.close()
        _db_instance = None


# Example usage
if __name__ == "__main__":
    # Test SQLite connection
    print("Testing SQLite connection...")
    db = get_database('sqlite')
    print(f"Health status: {db.get_health_status()}")
    
    # Test query
    results = db.execute_query("SELECT name FROM sqlite_master WHERE type='table'", fetch='all')
    print(f"Tables: {results}")
    
    close_database()
