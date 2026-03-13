"""
TruthLens ETL Pipeline Framework
=================================
Extract, Transform, Load pipeline for data ingestion

Features:
- Multi-source data extraction (API, CSV, JSON, Database)
- Data transformation and validation
- Batch and streaming processing
- Error handling and retry logic
- Pipeline monitoring and logging
"""

import json
import csv
import requests
from typing import Dict, List, Any, Callable, Optional
from datetime import datetime
import logging
from abc import ABC, abstractmethod

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataSource(ABC):
    """Abstract base class for data sources"""
    
    @abstractmethod
    def extract(self) -> List[Dict[str, Any]]:
        """Extract data from source"""
        pass


class APIDataSource(DataSource):
    """Extract data from REST APIs"""
    
    def __init__(self, url: str, headers: Dict[str, str] = None, params: Dict[str, Any] = None):
        """
        Initialize API data source
        
        Args:
            url: API endpoint URL
            headers: HTTP headers
            params: Query parameters
        """
        self.url = url
        self.headers = headers or {}
        self.params = params or {}
    
    def extract(self) -> List[Dict[str, Any]]:
        """Extract data from API"""
        try:
            logger.info(f"Extracting data from API: {self.url}")
            response = requests.get(self.url, headers=self.headers, params=self.params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Handle different response formats
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # Try common keys for data arrays
                for key in ['data', 'results', 'items', 'records']:
                    if key in data and isinstance(data[key], list):
                        return data[key]
                # If no array found, wrap dict in list
                return [data]
            else:
                logger.warning(f"Unexpected API response type: {type(data)}")
                return []
                
        except Exception as e:
            logger.error(f"API extraction failed: {e}")
            return []


class CSVDataSource(DataSource):
    """Extract data from CSV files"""
    
    def __init__(self, file_path: str, delimiter: str = ','):
        """
        Initialize CSV data source
        
        Args:
            file_path: Path to CSV file
            delimiter: CSV delimiter
        """
        self.file_path = file_path
        self.delimiter = delimiter
    
    def extract(self) -> List[Dict[str, Any]]:
        """Extract data from CSV"""
        try:
            logger.info(f"Extracting data from CSV: {self.file_path}")
            data = []
            
            with open(self.file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=self.delimiter)
                for row in reader:
                    data.append(dict(row))
            
            logger.info(f"Extracted {len(data)} records from CSV")
            return data
            
        except Exception as e:
            logger.error(f"CSV extraction failed: {e}")
            return []


class JSONDataSource(DataSource):
    """Extract data from JSON files"""
    
    def __init__(self, file_path: str):
        """
        Initialize JSON data source
        
        Args:
            file_path: Path to JSON file
        """
        self.file_path = file_path
    
    def extract(self) -> List[Dict[str, Any]]:
        """Extract data from JSON"""
        try:
            logger.info(f"Extracting data from JSON: {self.file_path}")
            
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Ensure data is a list
            if isinstance(data, dict):
                data = [data]
            elif not isinstance(data, list):
                logger.error(f"Invalid JSON format: expected list or dict, got {type(data)}")
                return []
            
            logger.info(f"Extracted {len(data)} records from JSON")
            return data
            
        except Exception as e:
            logger.error(f"JSON extraction failed: {e}")
            return []


class DatabaseDataSource(DataSource):
    """Extract data from database"""
    
    def __init__(self, db_connection, query: str, params: tuple = None):
        """
        Initialize database data source
        
        Args:
            db_connection: Database connection object
            query: SQL query
            params: Query parameters
        """
        self.db_connection = db_connection
        self.query = query
        self.params = params
    
    def extract(self) -> List[Dict[str, Any]]:
        """Extract data from database"""
        try:
            logger.info(f"Extracting data from database")
            
            results = self.db_connection.execute_query(self.query, self.params, fetch='all')
            
            # Convert to list of dicts
            data = []
            if results:
                # Handle different cursor types
                if hasattr(results[0], 'keys'):
                    # sqlite3.Row objects
                    data = [dict(row) for row in results]
                elif isinstance(results[0], dict):
                    data = results
                else:
                    logger.warning("Unable to convert results to dict format")
                    return []
            
            logger.info(f"Extracted {len(data)} records from database")
            return data
            
        except Exception as e:
            logger.error(f"Database extraction failed: {e}")
            return []


class DataTransformer:
    """Transform and validate data"""
    
    def __init__(self):
        self.transformations: List[Callable] = []
        self.validators: List[Callable] = []
    
    def add_transformation(self, func: Callable):
        """
        Add transformation function
        
        Args:
            func: Function that takes a record dict and returns transformed dict
        """
        self.transformations.append(func)
        return self
    
    def add_validator(self, func: Callable):
        """
        Add validation function
        
        Args:
            func: Function that takes a record dict and returns bool
        """
        self.validators.append(func)
        return self
    
    def transform(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform data records
        
        Args:
            data: List of data records
        
        Returns:
            Transformed data records
        """
        transformed = []
        
        for record in data:
            try:
                # Apply transformations
                transformed_record = record.copy()
                for transform_func in self.transformations:
                    transformed_record = transform_func(transformed_record)
                
                # Apply validations
                is_valid = True
                for validator_func in self.validators:
                    if not validator_func(transformed_record):
                        is_valid = False
                        logger.debug(f"Record failed validation: {transformed_record}")
                        break
                
                if is_valid:
                    transformed.append(transformed_record)
                    
            except Exception as e:
                logger.error(f"Transformation error: {e}")
                continue
        
        logger.info(f"Transformed {len(transformed)} / {len(data)} records")
        return transformed


class DataLoader:
    """Load data into destination"""
    
    def __init__(self, db_connection):
        """
        Initialize data loader
        
        Args:
            db_connection: Database connection object
        """
        self.db_connection = db_connection
    
    def load_to_database(self, data: List[Dict[str, Any]], table: str, 
                        mode: str = 'insert') -> int:
        """
        Load data into database table
        
        Args:
            data: List of data records
            table: Target table name
            mode: 'insert', 'upsert', or 'replace'
        
        Returns:
            Number of records loaded
        """
        if not data:
            logger.warning("No data to load")
            return 0
        
        try:
            # Get column names from first record
            columns = list(data[0].keys())
            placeholders = ', '.join(['?' for _ in columns])
            column_names = ', '.join(columns)
            
            # Build query based on mode
            if mode == 'insert':
                query = f"INSERT INTO {table} ({column_names}) VALUES ({placeholders})"
            elif mode == 'replace':
                query = f"REPLACE INTO {table} ({column_names}) VALUES ({placeholders})"
            elif mode == 'upsert':
                # For SQLite, use INSERT OR REPLACE
                query = f"INSERT OR REPLACE INTO {table} ({column_names}) VALUES ({placeholders})"
            else:
                raise ValueError(f"Invalid load mode: {mode}")
            
            # Prepare data tuples
            data_tuples = [tuple(record.get(col) for col in columns) for record in data]
            
            # Execute batch insert
            rows_affected = self.db_connection.execute_many(query, data_tuples)
            
            logger.info(f"Loaded {rows_affected} records into {table}")
            return rows_affected
            
        except Exception as e:
            logger.error(f"Data loading failed: {e}")
            return 0
    
    def load_to_csv(self, data: List[Dict[str, Any]], file_path: str) -> bool:
        """
        Load data to CSV file
        
        Args:
            data: List of data records
            file_path: Output CSV file path
        
        Returns:
            Success status
        """
        if not data:
            logger.warning("No data to export")
            return False
        
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=data[0].keys())
                writer.writeheader()
                writer.writerows(data)
            
            logger.info(f"Exported {len(data)} records to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"CSV export failed: {e}")
            return False
    
    def load_to_json(self, data: List[Dict[str, Any]], file_path: str) -> bool:
        """
        Load data to JSON file
        
        Args:
            data: List of data records
            file_path: Output JSON file path
        
        Returns:
            Success status
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            
            logger.info(f"Exported {len(data)} records to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"JSON export failed: {e}")
            return False


class ETLPipeline:
    """Complete ETL pipeline"""
    
    def __init__(self, name: str):
        """
        Initialize ETL pipeline
        
        Args:
            name: Pipeline name
        """
        self.name = name
        self.source: Optional[DataSource] = None
        self.transformer = DataTransformer()
        self.loader: Optional[DataLoader] = None
        self.metrics = {
            'start_time': None,
            'end_time': None,
            'records_extracted': 0,
            'records_transformed': 0,
            'records_loaded': 0,
            'errors': 0
        }
    
    def set_source(self, source: DataSource):
        """Set data source"""
        self.source = source
        return self
    
    def set_loader(self, loader: DataLoader):
        """Set data loader"""
        self.loader = loader
        return self
    
    def add_transformation(self, func: Callable):
        """Add transformation function"""
        self.transformer.add_transformation(func)
        return self
    
    def add_validator(self, func: Callable):
        """Add validation function"""
        self.transformer.add_validator(func)
        return self
    
    def run(self, load_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Execute ETL pipeline
        
        Args:
            load_config: Configuration for loader (e.g., {'table': 'content_analysis', 'mode': 'insert'})
        
        Returns:
            Pipeline execution metrics
        """
        logger.info(f"🚀 Starting ETL pipeline: {self.name}")
        self.metrics['start_time'] = datetime.now()
        
        try:
            # Extract
            if not self.source:
                raise ValueError("No data source configured")
            
            data = self.source.extract()
            self.metrics['records_extracted'] = len(data)
            logger.info(f"📥 Extracted {len(data)} records")
            
            if not data:
                logger.warning("No data extracted, pipeline stopped")
                self.metrics['end_time'] = datetime.now()
                return self.metrics
            
            # Transform
            transformed_data = self.transformer.transform(data)
            self.metrics['records_transformed'] = len(transformed_data)
            logger.info(f"🔄 Transformed {len(transformed_data)} records")
            
            # Load
            if self.loader and load_config:
                if 'table' in load_config:
                    # Load to database
                    loaded = self.loader.load_to_database(
                        transformed_data,
                        table=load_config.get('table'),
                        mode=load_config.get('mode', 'insert')
                    )
                    self.metrics['records_loaded'] = loaded
                    logger.info(f"📤 Loaded {loaded} records")
                elif 'file_path' in load_config:
                    # Load to file
                    file_path = load_config['file_path']
                    if file_path.endswith('.csv'):
                        self.loader.load_to_csv(transformed_data, file_path)
                    elif file_path.endswith('.json'):
                        self.loader.load_to_json(transformed_data, file_path)
                    self.metrics['records_loaded'] = len(transformed_data)
            
            self.metrics['end_time'] = datetime.now()
            duration = (self.metrics['end_time'] - self.metrics['start_time']).total_seconds()
            
            logger.info(f"✅ Pipeline completed in {duration:.2f}s")
            logger.info(f"📊 Metrics: {self.metrics}")
            
        except Exception as e:
            logger.error(f"❌ Pipeline failed: {e}")
            self.metrics['errors'] += 1
            self.metrics['end_time'] = datetime.now()
        
        return self.metrics


# Example usage and helper functions
def create_content_analysis_pipeline(db_connection, source_config: Dict[str, Any]) -> ETLPipeline:
    """
    Create a pipeline for content analysis data
    
    Args:
        db_connection: Database connection
        source_config: Source configuration
    
    Returns:
        Configured ETL pipeline
    """
    pipeline = ETLPipeline("Content Analysis Pipeline")
    
    # Configure source
    if source_config['type'] == 'api':
        source = APIDataSource(
            url=source_config['url'],
            headers=source_config.get('headers'),
            params=source_config.get('params')
        )
    elif source_config['type'] == 'csv':
        source = CSVDataSource(source_config['file_path'])
    elif source_config['type'] == 'json':
        source = JSONDataSource(source_config['file_path'])
    else:
        raise ValueError(f"Unsupported source type: {source_config['type']}")
    
    pipeline.set_source(source)
    
    # Add transformations
    def normalize_content(record):
        """Normalize content fields"""
        record['content'] = record.get('content', '').strip()
        record['headline'] = record.get('headline', '').strip()
        record['source'] = record.get('source', '').lower()
        return record
    
    def add_timestamp(record):
        """Add processing timestamp"""
        if 'processed_at' not in record:
            record['processed_at'] = datetime.now().isoformat()
        return record
    
    pipeline.add_transformation(normalize_content)
    pipeline.add_transformation(add_timestamp)
    
    # Add validators
    def validate_required_fields(record):
        """Validate required fields"""
        required = ['content', 'headline', 'source']
        return all(record.get(field) for field in required)
    
    pipeline.add_validator(validate_required_fields)
    
    # Set loader
    loader = DataLoader(db_connection)
    pipeline.set_loader(loader)
    
    return pipeline


# Example usage
if __name__ == "__main__":
    from database_config import get_database
    
    # Example: Load data from JSON file
    db = get_database('sqlite')
    
    pipeline = ETLPipeline("Test Pipeline")
    pipeline.set_source(JSONDataSource('sample_data.json'))
    pipeline.set_loader(DataLoader(db))
    
    # Add transformation to add timestamps
    pipeline.add_transformation(lambda r: {**r, 'processed_at': datetime.now().isoformat()})
    
    # Run pipeline
    # metrics = pipeline.run({'table': 'content_analysis', 'mode': 'insert'})
    # print(f"Pipeline metrics: {metrics}")
