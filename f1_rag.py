# f1_rag.py - Consolidated F1 RAG System with ALL functionality preserved
import requests
import logging
import time
import json
import re
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import os

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

class QueryType(Enum):
    """Query type classification"""
    CHAMPIONSHIP = "championship"
    DRIVER_STATS = "driver_stats"
    CONSTRUCTOR_STATS = "constructor_stats"
    RACE_RESULTS = "race_results"
    CURRENT_INFO = "current_info"
    COMPARISON = "comparison"
    GENERAL = "general"

@dataclass
class QueryResult:
    """Structured query result"""
    answer: str
    confidence: float
    query_type: QueryType
    sources: List[Dict[str, Any]]
    response_time: float
    metadata: Dict[str, Any]

class F1DatabaseManager:
    """SQLite database manager for F1 data with enhanced error handling"""
    
    def __init__(self, db_path: str = "f1_rag.db"):
        self.db_path = db_path
        self.connection = None
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize SQLite database with F1-specific schema"""
        try:
            self.connection = sqlite3.connect(
                self.db_path, 
                check_same_thread=False,
                timeout=30.0
            )
            self.connection.row_factory = sqlite3.Row
            # Disable foreign keys completely during setup
            self.connection.execute("PRAGMA foreign_keys = OFF")
            self.connection.execute("PRAGMA synchronous = NORMAL")
            self.connection.execute("PRAGMA journal_mode = WAL")
            
            self._create_tables()
            logger.info(f"Database initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    def _create_tables(self):
        """Create all F1 tables with simplified schema"""
        
        # Clean slate approach
        cursor = self.connection.cursor()
        
        # Get all table names and drop them
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [table[0] for table in cursor.fetchall()]
        
        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
        
        # Create tables with minimal constraints
        schema_sql = """
        -- Core F1 tables with minimal constraints
        
        CREATE TABLE IF NOT EXISTS seasons (
            year INTEGER PRIMARY KEY,
            url TEXT
        );
        
        CREATE TABLE IF NOT EXISTS status (
            statusId INTEGER PRIMARY KEY,
            status TEXT NOT NULL
        );
        
        CREATE TABLE IF NOT EXISTS circuits (
            circuitId INTEGER PRIMARY KEY,
            circuitRef TEXT,
            name TEXT NOT NULL,
            location TEXT,
            country TEXT,
            lat REAL,
            lng REAL,
            alt INTEGER,
            url TEXT
        );
        
        CREATE TABLE IF NOT EXISTS constructors (
            constructorId INTEGER PRIMARY KEY,
            constructorRef TEXT,
            name TEXT NOT NULL,
            nationality TEXT,
            url TEXT
        );
        
        CREATE TABLE IF NOT EXISTS drivers (
            driverId INTEGER PRIMARY KEY,
            driverRef TEXT,
            number TEXT,
            code TEXT,
            forename TEXT,
            surname TEXT,
            dob TEXT,
            nationality TEXT,
            url TEXT
        );
        
        CREATE TABLE IF NOT EXISTS races (
            raceId INTEGER PRIMARY KEY,
            year INTEGER,
            round INTEGER,
            circuitId INTEGER,
            name TEXT NOT NULL,
            date TEXT,
            time TEXT,
            url TEXT,
            fp1_date TEXT,
            fp1_time TEXT,
            fp2_date TEXT,
            fp2_time TEXT,
            fp3_date TEXT,
            fp3_time TEXT,
            quali_date TEXT,
            quali_time TEXT,
            sprint_date TEXT,
            sprint_time TEXT
        );
        
        CREATE TABLE IF NOT EXISTS results (
            resultId INTEGER PRIMARY KEY,
            raceId INTEGER,
            driverId INTEGER,
            constructorId INTEGER,
            number TEXT,
            grid INTEGER,
            position TEXT,
            positionText TEXT,
            positionOrder INTEGER,
            points REAL DEFAULT 0,
            laps INTEGER,
            time TEXT,
            milliseconds TEXT,
            fastestLap TEXT,
            rank TEXT,
            fastestLapTime TEXT,
            fastestLapSpeed TEXT,
            statusId INTEGER
        );
        
        CREATE TABLE IF NOT EXISTS sprint_results (
            resultId INTEGER PRIMARY KEY,
            raceId INTEGER,
            driverId INTEGER,
            constructorId INTEGER,
            number INTEGER,
            grid INTEGER,
            position TEXT,
            positionText TEXT,
            positionOrder INTEGER,
            points INTEGER DEFAULT 0,
            laps INTEGER,
            time TEXT,
            milliseconds TEXT,
            fastestLap TEXT,
            fastestLapTime TEXT,
            statusId INTEGER
        );
        
        CREATE TABLE IF NOT EXISTS driver_standings (
            driverStandingsId INTEGER PRIMARY KEY,
            raceId INTEGER,
            driverId INTEGER,
            points REAL DEFAULT 0,
            position INTEGER,
            positionText TEXT,
            wins INTEGER DEFAULT 0
        );
        
        CREATE TABLE IF NOT EXISTS constructor_standings (
            constructorStandingsId INTEGER PRIMARY KEY,
            raceId INTEGER,
            constructorId INTEGER,
            points REAL DEFAULT 0,
            position INTEGER,
            positionText TEXT,
            wins INTEGER DEFAULT 0
        );
        
        CREATE TABLE IF NOT EXISTS constructor_results (
            constructorResultsId INTEGER PRIMARY KEY,
            raceId INTEGER,
            constructorId INTEGER,
            points REAL,
            status TEXT
        );
        
        CREATE TABLE IF NOT EXISTS qualifying (
            qualifyId INTEGER PRIMARY KEY,
            raceId INTEGER,
            driverId INTEGER,
            constructorId INTEGER,
            number INTEGER,
            position INTEGER,
            q1 TEXT,
            q2 TEXT,
            q3 TEXT
        );
        
        CREATE TABLE IF NOT EXISTS lap_times (
            raceId INTEGER,
            driverId INTEGER,
            lap INTEGER,
            position INTEGER,
            time TEXT,
            milliseconds INTEGER
        );
        
        CREATE TABLE IF NOT EXISTS pit_stops (
            raceId INTEGER,
            driverId INTEGER,
            stop INTEGER,
            lap INTEGER,
            time TEXT,
            duration TEXT,
            milliseconds INTEGER
        );
        
        -- System tables
        CREATE TABLE IF NOT EXISTS query_analytics (
            query_id INTEGER PRIMARY KEY,
            query_text TEXT NOT NULL,
            query_type TEXT,
            response_text TEXT,
            response_time REAL,
            confidence REAL,
            sources_count INTEGER,
            user_feedback INTEGER DEFAULT 0,
            session_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS system_stats (
            stat_id INTEGER PRIMARY KEY,
            stat_name TEXT UNIQUE NOT NULL,
            stat_value TEXT,
            stat_type TEXT DEFAULT 'string',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        cursor.executescript(schema_sql)
        self.connection.commit()
        logger.info("Database schema created successfully")
    
    def load_csv_data(self, data_path: str) -> Dict[str, int]:
        """Load CSV data with enhanced error handling"""
        data_path = Path(data_path)
        loaded_counts = {}
        
        # Priority order for loading (though constraints are disabled)
        csv_mappings = [
            ('seasons.csv', 'seasons'),
            ('status.csv', 'status'),
            ('circuits.csv', 'circuits'),
            ('constructors.csv', 'constructors'),
            ('drivers.csv', 'drivers'),
            ('races.csv', 'races'),
            ('results.csv', 'results'),
            ('sprint_results.csv', 'sprint_results'),
            ('driver_standings.csv', 'driver_standings'),
            ('constructor_standings.csv', 'constructor_standings'),
            ('constructor_results.csv', 'constructor_results'),
            ('qualifying.csv', 'qualifying'),
            ('lap_times.csv', 'lap_times'),
            ('pit_stops.csv', 'pit_stops')
        ]
        
        logger.info("Starting F1 data loading...")
        total_loaded = 0
        
        for csv_file, table_name in csv_mappings:
            file_path = data_path / csv_file
            
            if not file_path.exists():
                logger.warning(f"File {csv_file} not found in {data_path}, skipping...")
                continue
            
            try:
                logger.info(f"Loading {csv_file} into {table_name}...")
                
                # Read CSV with error handling
                try:
                    df = pd.read_csv(file_path, encoding='utf-8')
                except UnicodeDecodeError:
                    logger.warning(f"UTF-8 encoding failed for {csv_file}, trying latin-1...")
                    df = pd.read_csv(file_path, encoding='latin-1')
                
                if df.empty:
                    logger.warning(f"File {csv_file} is empty, skipping...")
                    continue
                
                # Clean data
                df = self._clean_dataframe(df, table_name)
                
                # Load with chunking for large files
                record_count = self._load_dataframe_safe(df, table_name)
                
                loaded_counts[csv_file] = record_count
                total_loaded += record_count
                logger.info(f"Successfully loaded {record_count:,} records into {table_name}")
                
            except Exception as e:
                logger.error(f"Failed to load {csv_file}: {e}")
                # Continue with other files instead of failing completely
                continue
        
        # Create indexes after loading data
        self._create_indexes()
        
        # Update system statistics
        self._update_system_stats(loaded_counts)
        
        logger.info(f"Data loading complete. Loaded {len(loaded_counts)} files with {total_loaded:,} total records")
        return loaded_counts
    
    def _load_dataframe_safe(self, df: pd.DataFrame, table_name: str, chunk_size: int = 1000) -> int:
        """Safely load DataFrame with better error handling"""
        
        try:
            if len(df) <= chunk_size:
                # Small dataframe
                df.to_sql(table_name, self.connection, if_exists='replace', index=False, method='multi')
                return len(df)
            else:
                # Large dataframe - load in chunks
                logger.info(f"Loading large file in chunks of {chunk_size}...")
                
                # Clear table first
                cursor = self.connection.cursor()
                cursor.execute(f"DELETE FROM {table_name}")
                
                total_loaded = 0
                
                for i in range(0, len(df), chunk_size):
                    chunk = df.iloc[i:i+chunk_size]
                    
                    try:
                        chunk.to_sql(table_name, self.connection, if_exists='append', index=False, method='multi')
                        total_loaded += len(chunk)
                        
                        if i % (chunk_size * 10) == 0 and i > 0:  # Log every 10 chunks
                            logger.info(f"Loaded {total_loaded:,} / {len(df):,} records...")
                    
                    except Exception as chunk_error:
                        logger.error(f"Failed to load chunk starting at row {i}: {chunk_error}")
                        # Continue with next chunk instead of failing completely
                        continue
                
                self.connection.commit()
                return total_loaded
                
        except Exception as e:
            logger.error(f"Failed to load {table_name}: {e}")
            return 0
    
    def _clean_dataframe(self, df: pd.DataFrame, table_name: str) -> pd.DataFrame:
        """Enhanced DataFrame cleaning"""
        
        # Replace various null representations
        null_values = ['\\N', 'NULL', 'null', '', 'N/A', 'n/a', 'nan', 'NaN']
        df = df.replace(null_values, None)
        df = df.where(pd.notnull(df), None)
        
        # Table-specific cleaning
        if table_name == 'results':
            # Clean numeric columns
            numeric_cols = ['points', 'laps', 'grid', 'positionOrder']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
        
        elif table_name == 'races':
            if 'year' in df.columns:
                df['year'] = pd.to_numeric(df['year'], errors='coerce')
            if 'round' in df.columns:
                df['round'] = pd.to_numeric(df['round'], errors='coerce')
        
        elif table_name in ['driver_standings', 'constructor_standings']:
            if 'points' in df.columns:
                df['points'] = pd.to_numeric(df['points'], errors='coerce').fillna(0)
            if 'wins' in df.columns:
                df['wins'] = pd.to_numeric(df['wins'], errors='coerce').fillna(0)
            if 'position' in df.columns:
                df['position'] = pd.to_numeric(df['position'], errors='coerce')
        
        # Remove completely empty rows
        df = df.dropna(how='all')
        
        return df
    
    def _create_indexes(self):
        """Create performance indexes after data loading"""
        index_sql = """
        CREATE INDEX IF NOT EXISTS idx_drivers_name ON drivers(surname, forename);
        CREATE INDEX IF NOT EXISTS idx_drivers_nationality ON drivers(nationality);
        CREATE INDEX IF NOT EXISTS idx_constructors_name ON constructors(name);
        CREATE INDEX IF NOT EXISTS idx_races_year ON races(year);
        CREATE INDEX IF NOT EXISTS idx_races_date ON races(date);
        CREATE INDEX IF NOT EXISTS idx_results_driver ON results(driverId);
        CREATE INDEX IF NOT EXISTS idx_results_constructor ON results(constructorId);
        CREATE INDEX IF NOT EXISTS idx_results_race ON results(raceId);
        CREATE INDEX IF NOT EXISTS idx_results_position ON results(positionOrder);
        CREATE INDEX IF NOT EXISTS idx_query_created ON query_analytics(created_at);
        """
        
        try:
            cursor = self.connection.cursor()
            cursor.executescript(index_sql)
            self.connection.commit()
            logger.info("Performance indexes created")
        except Exception as e:
            logger.error(f"Failed to create indexes: {e}")
    
    def _update_system_stats(self, loaded_counts: Dict[str, int]):
        """Update system statistics with better error handling"""
        try:
            cursor = self.connection.cursor()
            
            # Calculate totals
            total_records = sum(loaded_counts.values())
            total_files = len(loaded_counts)
            
            # Get data coverage safely
            try:
                cursor.execute("SELECT MIN(year), MAX(year) FROM races WHERE year IS NOT NULL AND year > 1900")
                year_result = cursor.fetchone()
                year_range = year_result if year_result and year_result[0] else (None, None)
                data_coverage = f"{year_range[0]}-{year_range[1]}" if year_range[0] else "Unknown"
            except:
                data_coverage = "Unknown"
            
            # Get counts safely
            counts = {}
            stat_queries = [
                ("SELECT COUNT(*) FROM drivers", "total_drivers"),
                ("SELECT COUNT(*) FROM constructors", "total_constructors"), 
                ("SELECT COUNT(*) FROM races", "total_races"),
                ("SELECT COUNT(*) FROM results", "total_results")
            ]
            
            for query, key in stat_queries:
                try:
                    cursor.execute(query)
                    result = cursor.fetchone()
                    counts[key] = result[0] if result else 0
                except Exception as e:
                    logger.warning(f"Failed to get {key}: {e}")
                    counts[key] = 0
            
            # Prepare stats
            stats = [
                ('total_records', str(total_records), 'integer'),
                ('total_files_loaded', str(total_files), 'integer'),
                ('total_drivers', str(counts.get('total_drivers', 0)), 'integer'),
                ('total_constructors', str(counts.get('total_constructors', 0)), 'integer'),
                ('total_races', str(counts.get('total_races', 0)), 'integer'),
                ('total_results', str(counts.get('total_results', 0)), 'integer'),
                ('data_coverage', data_coverage, 'string'),
                ('last_data_update', datetime.now().isoformat(), 'datetime'),
                ('database_ready', 'true', 'boolean')
            ]
            
            # Insert/update stats
            for stat_name, stat_value, stat_type in stats:
                cursor.execute("""
                    INSERT OR REPLACE INTO system_stats (stat_name, stat_value, stat_type, updated_at) 
                    VALUES (?, ?, ?, ?)
                """, (stat_name, stat_value, stat_type, datetime.now().isoformat()))
            
            self.connection.commit()
            logger.info("System statistics updated")
            
        except Exception as e:
            logger.error(f"Failed to update system stats: {e}")
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics with better error handling"""
        try:
            cursor = self.connection.cursor()
            
            # Initialize default stats
            default_stats = {
                'system_ready': False,
                'total_records': 0,
                'total_drivers': 0,
                'total_constructors': 0,
                'total_races': 0,
                'data_coverage': 'Unknown',
                'total_queries': 0,
                'avg_response_time': 0,
                'avg_confidence': 0,
                'last_updated': 'Unknown'
            }
            
            # Get stored stats
            try:
                cursor.execute("SELECT stat_name, stat_value, stat_type FROM system_stats")
                stored_stats = {row[0]: row[1] for row in cursor.fetchall()}
                
                # Update defaults with stored values
                for key, value in stored_stats.items():
                    if key in ['total_records', 'total_drivers', 'total_constructors', 'total_races']:
                        try:
                            default_stats[key] = int(value)
                        except (ValueError, TypeError):
                            pass
                    elif key == 'database_ready':
                        default_stats['system_ready'] = value == 'true'
                    elif key in ['data_coverage', 'last_data_update']:
                        default_stats[key.replace('last_data_update', 'last_updated')] = value
                        
            except Exception as e:
                logger.warning(f"Could not load stored stats: {e}")
            
            # Get query analytics
            try:
                cursor.execute("SELECT COUNT(*) FROM query_analytics")
                result = cursor.fetchone()
                default_stats['total_queries'] = result[0] if result else 0
                
                # Get averages
                cursor.execute("SELECT AVG(response_time), AVG(confidence) FROM query_analytics WHERE response_time IS NOT NULL")
                avg_result = cursor.fetchone()
                if avg_result and avg_result[0]:
                    default_stats['avg_response_time'] = round(avg_result[0], 2)
                if avg_result and avg_result[1]:
                    default_stats['avg_confidence'] = round(avg_result[1] * 100, 1)
                    
            except Exception as e:
                logger.warning(f"Could not load query analytics: {e}")
            
            return default_stats
            
        except Exception as e:
            logger.error(f"Failed to get system stats: {e}")
            return {'system_ready': False, 'error': str(e)}
    
    def execute_query(self, query: str, params: tuple = None) -> List[sqlite3.Row]:
        """Execute SQL query with better error handling"""
        try:
            cursor = self.connection.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            logger.error(f"Query: {query[:100]}...")
            return []
    
    def log_query(self, query_text: str, query_type: str = None, response_text: str = None, 
                  response_time: float = None, confidence: float = None, sources_count: int = None):
        """Log query with error handling"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("""
                INSERT INTO query_analytics (query_text, query_type, response_text, response_time, confidence, sources_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (query_text, query_type, response_text, response_time, confidence, sources_count))
            self.connection.commit()
        except Exception as e:
            logger.error(f"Failed to log query: {e}")
    
    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")

class F1RAGSystem:
    """Purely Data-Driven F1 RAG System - extracts everything from CSV data"""
    
    def __init__(self, db_manager, config=None):
        self.db_manager = db_manager
        self.query_cache = {}
        self.query_history = []
        
        # Configuration
        self.config = config or {
            'embedding_model': 'all-MiniLM-L6-v2',
            'max_tokens': 600,
            'temperature': 0.15,
            'timeout': 30,
            'top_k_retrieval': 12,
            'confidence_threshold': 0.25,
            'lm_studio_url': 'http://localhost:1234'
        }
        
        # Initialize system
        print("Initializing Data-Driven F1 RAG System...")
        self._initialize_ml_models()
        self._load_f1_data_from_database()
        self._build_knowledge_from_data()
        self._setup_search_system()
        
        print(f"Data-Driven F1 RAG System Ready: {len(self.documents)} documents generated from data")
    
    def _initialize_ml_models(self):
        """Initialize ML models"""
        print("Loading embedding model...")
        self.embedding_model = SentenceTransformer(self.config['embedding_model'])
    
    def _load_f1_data_from_database(self):
        """Load all F1 data from database"""
        print("Loading F1 data from database...")
        self.f1_data = {}
        
        # Check if database has data
        stats = self.db_manager.get_system_stats()
        if stats.get('total_records', 0) == 0:
            print("No database records found - system will work with minimal fallback only")
            return
        
        try:
            # Load core data tables
            tables_to_load = [
                'drivers', 'constructors', 'races', 'results', 
                'driver_standings', 'constructor_standings', 'circuits'
            ]
            
            for table in tables_to_load:
                query = f"SELECT * FROM {table}"
                try:
                    rows = self.db_manager.execute_query(query)
                    if rows:
                        # Convert to list of dicts for easier processing
                        self.f1_data[table] = [dict(row) for row in rows]
                        print(f"  Loaded {table}: {len(self.f1_data[table])} records")
                    else:
                        print(f"  No data found in {table}")
                        self.f1_data[table] = []
                except Exception as e:
                    print(f"  Error loading {table}: {e}")
                    self.f1_data[table] = []
            
            print(f"Database loading complete. Total tables: {len(self.f1_data)}")
            
        except Exception as e:
            print(f"Database loading failed: {e}")
            self.f1_data = {}
    
    def _build_knowledge_from_data(self):
        """Build knowledge base purely from CSV data"""
        print("Building knowledge base from data...")
        self.documents = []
        
        if not self.f1_data or not any(self.f1_data.values()):
            print("No data available - using minimal fallback knowledge")
            self._add_minimal_fallback()
            return
        
        # Generate documents from actual data
        self.documents.extend(self._generate_championship_documents())
        self.documents.extend(self._generate_driver_profile_documents())
        self.documents.extend(self._generate_constructor_profile_documents())
        self.documents.extend(self._generate_race_result_documents())
        self.documents.extend(self._generate_current_lineup_documents())
        self.documents.extend(self._generate_circuit_documents())
        
        print(f"Knowledge base built: {len(self.documents)} documents from data")
    
    def _generate_championship_documents(self) -> List[Dict]:
        """Generate championship documents from driver_standings data"""
        documents = []
        
        try:
            drivers = {d['driverId']: d for d in self.f1_data.get('drivers', [])}
            races = {r['raceId']: r for r in self.f1_data.get('races', [])}
            constructors = {c['constructorId']: c for c in self.f1_data.get('constructors', [])}
            standings = self.f1_data.get('driver_standings', [])
            results = self.f1_data.get('results', [])
            
            # Find championship winners by finding position 1 in final race of each year
            final_races_by_year = {}
            for race in races.values():
                year = race['year']
                if year not in final_races_by_year or race['round'] > final_races_by_year[year]['round']:
                    final_races_by_year[year] = race
            
            champions_by_year = {}
            for standing in standings:
                if standing['position'] == 1:
                    race = races.get(standing['raceId'])
                    if race and final_races_by_year.get(race['year'], {}).get('raceId') == race['raceId']:
                        year = race['year']
                        driver = drivers.get(standing['driverId'])
                        
                        # Find constructor for this championship
                        champion_results = [r for r in results if r['driverId'] == standing['driverId'] and r['raceId'] == race['raceId']]
                        constructor_name = "Unknown"
                        if champion_results:
                            constructor = constructors.get(champion_results[0]['constructorId'])
                            constructor_name = constructor['name'] if constructor else "Unknown"
                        
                        if driver:
                            champions_by_year[year] = {
                                'driver': f"{driver['forename']} {driver['surname']}",
                                'points': standing['points'],
                                'wins': standing['wins'],
                                'constructor': constructor_name,
                                'nationality': driver['nationality']
                            }
            
            # Create championship documents
            for year, champ_data in sorted(champions_by_year.items(), reverse=True):
                if year >= 1950:  # Only F1 era
                    content = f"""WORLD CHAMPIONSHIP {year}
Champion: {champ_data['driver']}
Constructor: {champ_data['constructor']}
Nationality: {champ_data['nationality']}
Final Points: {champ_data['points']:.0f}
Season Wins: {champ_data['wins']}

{champ_data['driver']} won the {year} Formula 1 World Drivers' Championship.
The {year} F1 champion was {champ_data['driver']}.
{year} world champion: {champ_data['driver']}.
{champ_data['driver']} {year} championship winner driving for {champ_data['constructor']}."""
                    
                    documents.append({
                        'content': content,
                        'metadata': {
                            'type': 'championship',
                            'year': year,
                            'champion': champ_data['driver'],
                            'constructor': champ_data['constructor']
                        }
                    })
            
            print(f"Generated {len(documents)} championship documents from data")
            
        except Exception as e:
            print(f"Error generating championship documents: {e}")
        
        return documents
    
    def _generate_driver_profile_documents(self) -> List[Dict]:
        """Generate driver profiles from results data"""
        documents = []
        
        try:
            drivers = {d['driverId']: d for d in self.f1_data.get('drivers', [])}
            races = {r['raceId']: r for r in self.f1_data.get('races', [])}
            results = self.f1_data.get('results', [])
            standings = self.f1_data.get('driver_standings', [])
            
            # Calculate driver statistics
            driver_stats = {}
            
            for result in results:
                driver_id = result['driverId']
                if driver_id not in driver_stats:
                    driver_stats[driver_id] = {
                        'races': 0,
                        'wins': 0,
                        'podiums': 0,
                        'points': 0,
                        'years': set()
                    }
                
                race = races.get(result['raceId'])
                if race:
                    driver_stats[driver_id]['races'] += 1
                    driver_stats[driver_id]['years'].add(race['year'])
                    
                    # Count wins
                    if result['position'] == '1':
                        driver_stats[driver_id]['wins'] += 1
                    
                    # Count podiums
                    if result['position'] in ['1', '2', '3']:
                        driver_stats[driver_id]['podiums'] += 1
                    
                    # Add points
                    if result['points']:
                        driver_stats[driver_id]['points'] += float(result['points'])
            
            # Count championships
            championships = {}
            for standing in standings:
                if standing['position'] == 1:
                    race = races.get(standing['raceId'])
                    if race:
                        # Check if this is the final race of the year
                        year_races = [r for r in races.values() if r['year'] == race['year']]
                        max_round = max(r['round'] for r in year_races)
                        if race['round'] == max_round:
                            driver_id = standing['driverId']
                            if driver_id not in championships:
                                championships[driver_id] = 0
                            championships[driver_id] += 1
            
            # Create driver profile documents for drivers with significant careers
            for driver_id, stats in driver_stats.items():
                if stats['races'] >= 5:  # Only drivers with 5+ races
                    driver = drivers.get(driver_id)
                    if driver:
                        years = sorted(stats['years'])
                        first_year = years[0] if years else 'Unknown'
                        last_year = years[-1] if years else 'Unknown'
                        career_span = f"{first_year}-{last_year}" if first_year != last_year else str(first_year)
                        
                        # Determine if active (raced in last 3 years)
                        current_year = max(races[r]['year'] for r in races.keys()) if races else 2024
                        status = "Active" if last_year >= current_year - 2 else "Retired"
                        
                        driver_championships = championships.get(driver_id, 0)
                        win_rate = (stats['wins'] / stats['races'] * 100) if stats['races'] > 0 else 0
                        
                        name = f"{driver['forename']} {driver['surname']}"
                        
                        content = f"""DRIVER PROFILE: {name}
Full Name: {name}
Nationality: {driver['nationality']}
Status: {status}
Career: {career_span}
Driver Code: {driver.get('code', 'N/A')}

CAREER STATISTICS:
- Total Races: {stats['races']}
- Race Wins: {stats['wins']}
- Podium Finishes: {stats['podiums']}
- World Championships: {driver_championships}
- Career Points: {stats['points']:.0f}
- Win Rate: {win_rate:.1f}%

{name} is a {driver['nationality']} Formula 1 driver who has competed in {stats['races']} races.
{name} has {stats['wins']} race wins and {driver_championships} world championships.
{name} achieved {stats['podiums']} podium finishes during career from {career_span}."""
                        
                        documents.append({
                            'content': content,
                            'metadata': {
                                'type': 'driver_profile',
                                'name': name,
                                'nationality': driver['nationality'],
                                'wins': stats['wins'],
                                'championships': driver_championships,
                                'status': status,
                                'races': stats['races']
                            }
                        })
            
            print(f"Generated {len(documents)} driver profile documents from data")
            
        except Exception as e:
            print(f"Error generating driver profiles: {e}")
        
        return documents
    
    def _generate_constructor_profile_documents(self) -> List[Dict]:
        """Generate constructor profiles from results data"""
        documents = []
        
        try:
            constructors = {c['constructorId']: c for c in self.f1_data.get('constructors', [])}
            results = self.f1_data.get('results', [])
            constructor_standings = self.f1_data.get('constructor_standings', [])
            races = {r['raceId']: r for r in self.f1_data.get('races', [])}
            
            # Calculate constructor statistics
            constructor_stats = {}
            
            for result in results:
                constructor_id = result['constructorId']
                if constructor_id not in constructor_stats:
                    constructor_stats[constructor_id] = {
                        'entries': 0,
                        'wins': 0,
                        'points': 0,
                        'years': set()
                    }
                
                race = races.get(result['raceId'])
                if race:
                    constructor_stats[constructor_id]['entries'] += 1
                    constructor_stats[constructor_id]['years'].add(race['year'])
                    
                    if result['position'] == '1':
                        constructor_stats[constructor_id]['wins'] += 1
                    
                    if result['points']:
                        constructor_stats[constructor_id]['points'] += float(result['points'])
            
            # Count constructor championships
            constructor_championships = {}
            for standing in constructor_standings:
                if standing['position'] == 1:
                    race = races.get(standing['raceId'])
                    if race:
                        # Check if final race of year
                        year_races = [r for r in races.values() if r['year'] == race['year']]
                        max_round = max(r['round'] for r in year_races)
                        if race['round'] == max_round:
                            constructor_id = standing['constructorId']
                            if constructor_id not in constructor_championships:
                                constructor_championships[constructor_id] = 0
                            constructor_championships[constructor_id] += 1
            
            # Create constructor documents
            for constructor_id, stats in constructor_stats.items():
                if stats['entries'] >= 10:  # Only constructors with 10+ entries
                    constructor = constructors.get(constructor_id)
                    if constructor:
                        championships = constructor_championships.get(constructor_id, 0)
                        success_rate = (stats['wins'] / stats['entries'] * 100) if stats['entries'] > 0 else 0
                        years = sorted(stats['years'])
                        career_span = f"{years[0]}-{years[-1]}" if len(years) > 1 else str(years[0]) if years else "Unknown"
                        
                        content = f"""CONSTRUCTOR PROFILE: {constructor['name']}
Full Name: {constructor['name']}
Nationality: {constructor['nationality']}
Active Period: {career_span}

STATISTICS:
- Total Entries: {stats['entries']}
- Race Wins: {stats['wins']}
- Constructor Championships: {championships}
- Total Points: {stats['points']:.0f}
- Success Rate: {success_rate:.1f}%

{constructor['name']} is a {constructor['nationality']} Formula 1 constructor.
{constructor['name']} has {stats['wins']} race wins and {championships} constructor championships.
{constructor['name']} has {stats['entries']} race entries in Formula 1."""
                        
                        documents.append({
                            'content': content,
                            'metadata': {
                                'type': 'constructor_profile',
                                'name': constructor['name'],
                                'nationality': constructor['nationality'],
                                'wins': stats['wins'],
                                'championships': championships,
                                'entries': stats['entries']
                            }
                        })
            
            print(f"Generated {len(documents)} constructor profile documents from data")
            
        except Exception as e:
            print(f"Error generating constructor profiles: {e}")
        
        return documents
    
    def _generate_race_result_documents(self) -> List[Dict]:
        """Generate race result documents from results data"""
        documents = []
        
        try:
            drivers = {d['driverId']: d for d in self.f1_data.get('drivers', [])}
            constructors = {c['constructorId']: c for c in self.f1_data.get('constructors', [])}
            circuits = {c['circuitId']: c for c in self.f1_data.get('circuits', [])}
            races = {r['raceId']: r for r in self.f1_data.get('races', [])}
            results = self.f1_data.get('results', [])
            
            # Group race winners by race name
            race_winners = {}
            
            for result in results:
                if result['position'] == '1':  # Race winner
                    race = races.get(result['raceId'])
                    if race and race['year'] >= 2000:  # Focus on modern era
                        race_name = race['name']
                        driver = drivers.get(result['driverId'])
                        constructor = constructors.get(result['constructorId'])
                        circuit = circuits.get(race['circuitId'])
                        
                        if driver and constructor:
                            if race_name not in race_winners:
                                race_winners[race_name] = []
                            
                            race_winners[race_name].append({
                                'year': race['year'],
                                'winner': f"{driver['forename']} {driver['surname']}",
                                'constructor': constructor['name'],
                                'circuit': circuit['name'] if circuit else 'Unknown Circuit',
                                'location': f"{circuit['location']}, {circuit['country']}" if circuit else 'Unknown'
                            })
            
            # Create race result documents for races with multiple years of data
            for race_name, winners in race_winners.items():
                if len(winners) >= 3:  # Only races with 3+ years of data
                    winners_sorted = sorted(winners, key=lambda x: x['year'], reverse=True)
                    recent_winners = winners_sorted[:10]  # Last 10 years
                    
                    content = f"""RACE WINNERS: {race_name}
Circuit: {recent_winners[0]['circuit']}
Location: {recent_winners[0]['location']}

RECENT WINNERS:
"""
                    for winner_info in recent_winners:
                        content += f"- {winner_info['year']}: {winner_info['winner']} ({winner_info['constructor']})\n"
                    
                    # Add query-friendly phrases
                    latest = recent_winners[0]
                    content += f"\nWho won the last {race_name}? {latest['winner']} ({latest['year']})."
                    content += f"\n{latest['year']} {race_name} winner: {latest['winner']}."
                    content += f"\nMost recent {race_name} winner: {latest['winner']} driving for {latest['constructor']}."
                    
                    documents.append({
                        'content': content,
                        'metadata': {
                            'type': 'race_results',
                            'race_name': race_name,
                            'circuit': recent_winners[0]['circuit'],
                            'recent_winner': latest['winner'],
                            'recent_year': latest['year']
                        }
                    })
            
            print(f"Generated {len(documents)} race result documents from data")
            
        except Exception as e:
            print(f"Error generating race results: {e}")
        
        return documents
    
    def _generate_current_lineup_documents(self) -> List[Dict]:
        """Generate current team lineups from recent results"""
        documents = []
        
        try:
            drivers = {d['driverId']: d for d in self.f1_data.get('drivers', [])}
            constructors = {c['constructorId']: c for c in self.f1_data.get('constructors', [])}
            races = {r['raceId']: r for r in self.f1_data.get('races', [])}
            results = self.f1_data.get('results', [])
            
            # Find the most recent year with data
            recent_years = sorted([r['year'] for r in races.values()], reverse=True)[:2]
            
            if not recent_years:
                return documents
            
            # Get recent results
            recent_results = []
            for result in results:
                race = races.get(result['raceId'])
                if race and race['year'] in recent_years:
                    recent_results.append(result)
            
            # Group drivers by constructor for recent years
            constructor_drivers = {}
            for result in recent_results:
                constructor_id = result['constructorId']
                driver_id = result['driverId']
                
                if constructor_id not in constructor_drivers:
                    constructor_drivers[constructor_id] = set()
                constructor_drivers[constructor_id].add(driver_id)
            
            # Create lineup documents
            for constructor_id, driver_ids in constructor_drivers.items():
                if len(driver_ids) >= 1:  # At least 1 driver
                    constructor = constructors.get(constructor_id)
                    if constructor:
                        driver_names = []
                        for driver_id in driver_ids:
                            driver = drivers.get(driver_id)
                            if driver:
                                driver_names.append(f"{driver['forename']} {driver['surname']}")
                        
                        if driver_names:
                            driver_list = sorted(driver_names)  # Sort for consistency
                            max_year = max(recent_years)
                            
                            content = f"""CURRENT LINEUP: {constructor['name']}
Year: {max_year}
Drivers: {', '.join(driver_list)}

Current {constructor['name']} drivers are {' and '.join(driver_list[:2])}.
{constructor['name']} current lineup: {' and '.join(driver_list[:2])}.
Who drives for {constructor['name']}? {' and '.join(driver_list[:2])}.
{constructor['name']} team drivers: {', '.join(driver_list)}."""
                            
                            documents.append({
                                'content': content,
                                'metadata': {
                                    'type': 'current_lineup',
                                    'constructor': constructor['name'],
                                    'drivers': driver_list,
                                    'year': max_year
                                }
                            })
            
            print(f"Generated {len(documents)} current lineup documents from data")
            
        except Exception as e:
            print(f"Error generating current lineups: {e}")
        
        return documents
    
    def _generate_circuit_documents(self) -> List[Dict]:
        """Generate circuit information documents"""
        documents = []
        
        try:
            circuits = self.f1_data.get('circuits', [])
            races = {r['raceId']: r for r in self.f1_data.get('races', [])}
            
            # Count races per circuit
            circuit_race_counts = {}
            for race in races.values():
                circuit_id = race['circuitId']
                if circuit_id not in circuit_race_counts:
                    circuit_race_counts[circuit_id] = 0
                circuit_race_counts[circuit_id] += 1
            
            # Create circuit documents for circuits with multiple races
            for circuit in circuits:
                race_count = circuit_race_counts.get(circuit['circuitId'], 0)
                if race_count >= 5:  # Circuits with 5+ races
                    content = f"""CIRCUIT: {circuit['name']}
Location: {circuit['location']}, {circuit['country']}
Altitude: {circuit.get('alt', 'N/A')}m
Coordinates: {circuit.get('lat', 'N/A')}, {circuit.get('lng', 'N/A')}
Total F1 Races: {race_count}

{circuit['name']} is located in {circuit['location']}, {circuit['country']}.
{circuit['name']} circuit has hosted {race_count} Formula 1 races.
The {circuit['location']} circuit is {circuit['name']}."""
                    
                    documents.append({
                        'content': content,
                        'metadata': {
                            'type': 'circuit_info',
                            'name': circuit['name'],
                            'location': circuit['location'],
                            'country': circuit['country'],
                            'race_count': race_count
                        }
                    })
            
            print(f"Generated {len(documents)} circuit documents from data")
            
        except Exception as e:
            print(f"Error generating circuit documents: {e}")
        
        return documents
    
    def _add_minimal_fallback(self):
        """Add minimal fallback when no data is available"""
        fallback_doc = {
            'content': """F1 RAG SYSTEM STATUS
Status: Data loading required
Message: Please load F1 CSV data to enable comprehensive F1 knowledge

This system requires F1 data from CSV files including:
- drivers.csv: Driver information and profiles
- races.csv: Race calendar and information  
- results.csv: Race results and standings
- constructors.csv: Team information
- driver_standings.csv: Championship standings
- constructor_standings.csv: Constructor championships

Once data is loaded, the system will provide detailed F1 information including:
- Championship winners by year
- Driver statistics and career information
- Constructor profiles and achievements  
- Race results and winners
- Current team lineups
- Circuit information""",
            'metadata': {'type': 'system_status'}
        }
        
        self.documents = [fallback_doc]
        print("Added minimal fallback document")
    
    def _setup_search_system(self):
        """Setup search system"""
        print("Setting up search system...")
        
        if not self.documents:
            print("No documents to index")
            return
        
        try:
            # Generate embeddings
            contents = [doc['content'] for doc in self.documents]
            print("Generating embeddings...")
            self.document_embeddings = self.embedding_model.encode(contents, show_progress_bar=False)
            
            # Setup BM25
            print("Setting up BM25...")
            tokenized_docs = [doc.lower().split() for doc in contents]
            self.bm25 = BM25Okapi(tokenized_docs)
            
            print("Search system ready")
            
        except Exception as e:
            print(f"Search system setup failed: {e}")
    
    def _preprocess_query(self, question: str) -> str:
        """Preprocess query with F1-specific normalizations"""
        processed = question.lower().strip()
        
        # Basic normalizations
        normalizations = {
            'formula one': 'f1',
            'formula 1': 'f1', 
            'grand prix': 'race',
            'gp': 'race',
            'world championship': 'championship',
            'drives for': 'team',
            'current team': 'team',
            'who won': 'winner',
            'winner': 'champion'
        }
        
        for old, new in normalizations.items():
            processed = processed.replace(old, new)
        
        return processed
    
    def _classify_query(self, question: str) -> Dict:
        """Classify query type"""
        q = question.lower()
        
        if re.search(r'\b(champion|championship)\b.*\b(20\d{2}|19\d{2})\b', q):
            return {'type': 'championship_year', 'priority': 'high'}
        elif re.search(r'\b(how many|total).*\b(win|championship)', q):
            return {'type': 'stats_count', 'priority': 'high'}  
        elif re.search(r'\b(current|drives? for|team)\b', q):
            return {'type': 'current_team', 'priority': 'high'}
        elif re.search(r'\b(who won|winner).*\b(race|grand prix)\b', q):
            return {'type': 'race_result', 'priority': 'high'}
        else:
            return {'type': 'general', 'priority': 'medium'}
    
    def _hybrid_search(self, question: str, n_results: int = 8) -> List[str]:
        """Simple hybrid search"""
        if not hasattr(self, 'document_embeddings') or not hasattr(self, 'bm25'):
            return [doc['content'] for doc in self.documents[:n_results]]
        
        try:
            # Vector search
            query_embedding = self.embedding_model.encode([question])
            similarities = cosine_similarity(query_embedding, self.document_embeddings)[0]
            top_vector_indices = np.argsort(similarities)[::-1][:n_results//2]
            
            # BM25 search  
            tokenized_query = question.lower().split()
            bm25_scores = self.bm25.get_scores(tokenized_query)
            top_bm25_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:n_results//2]
            
            # Combine results
            all_indices = list(top_vector_indices) + list(top_bm25_indices)
            unique_docs = []
            seen = set()
            
            for idx in all_indices:
                if idx < len(self.documents) and idx not in seen:
                    seen.add(idx)
                    unique_docs.append(self.documents[idx]['content'])
                    if len(unique_docs) >= n_results:
                        break
            
            return unique_docs
            
        except Exception as e:
            print(f"Hybrid search failed: {e}")
            return [doc['content'] for doc in self.documents[:n_results]]
    
    def _calculate_confidence(self, question: str, answer: str, sources: List[str], query_type: Dict) -> float:
        """Calculate response confidence"""
        confidence_factors = []
        
        # Base confidence
        base_score = 0.4
        if len(answer.strip()) > 30:
            base_score += 0.2
        if re.search(r'\d+', answer):
            base_score += 0.2
        if re.search(r'[A-Z][a-z]+ [A-Z][a-z]+', answer):
            base_score += 0.1
        if not any(phrase in answer.lower() for phrase in ['unable to', 'cannot find']):
            base_score += 0.1
        
        confidence_factors.append(base_score)
        
        # Query type confidence
        if query_type.get('priority') == 'high':
            confidence_factors.append(0.8)
        else:
            confidence_factors.append(0.6)
        
        # Source relevance
        if sources:
            question_words = set(question.lower().split())
            source_text = ' '.join(sources).lower()
            matches = sum(1 for word in question_words if len(word) > 3 and word in source_text)
            overlap_score = min(matches / max(len(question_words), 1), 1.0)
            confidence_factors.append(0.3 + overlap_score * 0.7)
        else:
            confidence_factors.append(0.5)
        
        return min(np.mean(confidence_factors), 1.0)
    
    def _generate_fallback_answer(self, prompt: str, query_type: Dict, question: str) -> str:
        """Generate fallback answer from data"""
        
        if query_type['type'] == 'championship_year':
            # Extract championship info from prompt
            year_match = re.search(r'\b(20\d{2}|19\d{2})\b', question)
            champion_matches = re.findall(r'Champion:\s*([^\n]+)', prompt, re.I)
            
            if year_match and champion_matches:
                year = year_match.group()
                champion = champion_matches[0].strip()
                return f"{champion} won the {year} Formula 1 World Drivers' Championship."
        
        elif query_type['type'] == 'current_team':
            # Extract team lineup info
            lineup_matches = re.findall(r'Current ([^:]+) drivers are ([^\.]+)', prompt, re.I)
            
            if lineup_matches:
                team, drivers = lineup_matches[0]
                return f"Current {team} drivers are {drivers}."
        
        elif query_type['type'] == 'race_result':
            # Extract race result info
            winner_matches = re.findall(r'(\d{4}):\s*([^(]+)(?:\s*\([^)]+\))?', prompt)
            year_match = re.search(r'\b(20\d{2})\b', question)
            
            if year_match and winner_matches:
                target_year = year_match.group()
                for year, winner in winner_matches:
                    if year == target_year:
                        return f"{winner.strip()} won the {target_year} race."
        
        elif query_type['type'] == 'stats_count':
            # Extract win/championship counts
            wins_matches = re.findall(r'Race Wins:\s*(\d+)', prompt, re.I)
            championships_matches = re.findall(r'World Championships:\s*(\d+)', prompt, re.I)
            name_matches = re.findall(r'DRIVER PROFILE:\s*([^\n]+)', prompt, re.I)
            
            if 'how many wins' in question.lower() and wins_matches and name_matches:
                return f"{name_matches[0]} has {wins_matches[0]} Formula 1 race wins."
            elif 'championship' in question.lower() and championships_matches and name_matches:
                return f"{name_matches[0]} has {championships_matches[0]} world championships."
        
        # Generic fallback based on available data
        if len(self.documents) > 1:
            return "Based on the available F1 data, relevant information was found. Please try rephrasing your question for more specific results."
        else:
            return "F1 data is not currently loaded. Please ensure F1 CSV files are available in the data directory for comprehensive F1 information."
    
    def _query_llm(self, prompt: str, query_type: Dict) -> str:
        """Query LLM with fallback"""
        try:
            lm_studio_url = self.config.get('lm_studio_url', 'http://localhost:1234')
            
            # Adaptive system message
            if query_type['type'] == 'championship_year':
                system_msg = "You are an F1 historian. Provide exact championship winners and years clearly. Do not mention sources."
            elif query_type['type'] == 'current_team':
                system_msg = "You are an F1 expert. Provide current team lineups clearly. Do not mention sources."
            else:
                system_msg = "You are an F1 expert. Provide accurate F1 information clearly. Do not mention sources."
            
            response = requests.post(
                f"{lm_studio_url}/v1/chat/completions",
                json={
                    "model": "llama-3.2-3b-instruct",
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": self.config.get('max_tokens', 400),
                    "temperature": self.config.get('temperature', 0.15)
                },
                timeout=self.config.get('timeout', 30)
            )
            
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content'].strip()
            else:
                return f"LLM Error {response.status_code}"
        
        except Exception as e:
            return f"LLM Connection Error: {str(e)}"
    
    def query(self, question: str) -> QueryResult:
        """Main query interface - purely data-driven"""
        start_time = time.time()
        
        original_question = question
        processed_question = self._preprocess_query(question)
        
        # Check cache
        if original_question in self.query_cache:
            cached_result = self.query_cache[original_question]
            cached_result.metadata['cached'] = True
            return cached_result
        
        # Classify query
        query_type_info = self._classify_query(processed_question)
        
        # Map to enum
        type_mapping = {
            'championship_year': QueryType.CHAMPIONSHIP,
            'stats_count': QueryType.DRIVER_STATS,
            'current_team': QueryType.CURRENT_INFO,
            'race_result': QueryType.RACE_RESULTS,
            'general': QueryType.GENERAL
        }
        query_type = type_mapping.get(query_type_info['type'], QueryType.GENERAL)
        
        # Search relevant documents
        relevant_docs = self._hybrid_search(processed_question, self.config['top_k_retrieval'])
        
        # Build context
        context = "F1 DATA KNOWLEDGE BASE:\n\n"
        for i, doc in enumerate(relevant_docs, 1):
            context += f"[DATA SOURCE {i}]\n{doc}\n\n"
        
        prompt = f"""{context}

QUESTION: {original_question}

INSTRUCTIONS: Answer the F1 question using the data provided. Be direct and factual. Do not reference data sources in your answer."""
        
        # Query LLM with fallback
        try:
            answer = self._query_llm(prompt, query_type_info)
            
            # Use fallback if LLM fails
            if (len(answer) < 20 or 
                'error' in answer.lower() or
                any(phrase in answer.lower() for phrase in ['unable to', 'cannot find'])):
                answer = self._generate_fallback_answer(prompt, query_type_info, original_question)
        except:
            answer = self._generate_fallback_answer(prompt, query_type_info, original_question)
        
        # Calculate confidence
        confidence = self._calculate_confidence(original_question, answer, relevant_docs, query_type_info)
        response_time = time.time() - start_time
        
        # Create result
        result = QueryResult(
            answer=answer,
            confidence=confidence,
            query_type=query_type,
            sources=[{'content': doc[:200] + '...' if len(doc) > 200 else doc} for doc in relevant_docs[:3]],
            response_time=response_time,
            metadata={
                'question': original_question,
                'query_classification': query_type_info,
                'sources_count': len(relevant_docs),
                'cached': False,
                'data_driven': True,
                'total_documents': len(self.documents)
            }
        )
        
        # Cache and log
        self.query_cache[original_question] = result
        self.query_history.append(result)
        
        # Log to database
        try:
            self.db_manager.log_query(original_question, query_type.value, answer, response_time, confidence, len(relevant_docs))
        except Exception as e:
            logger.error(f"Failed to log query: {e}")
        
        return result
    
    def get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics"""
        # Get database stats
        db_stats = self.db_manager.get_system_stats()
        
        # Add RAG-specific stats
        stats = {
            **db_stats,
            'rag_system_ready': True,
            'data_driven': True,
            'total_documents': len(self.documents),
            'documents_from_data': len([d for d in self.documents if d['metadata'].get('type') != 'system_status']),
            'query_cache_size': len(self.query_cache),
            'session_queries': len(self.query_history),
            'has_championship_data': len([d for d in self.documents if d['metadata'].get('type') == 'championship']) > 0,
            'has_driver_data': len([d for d in self.documents if d['metadata'].get('type') == 'driver_profile']) > 0,
            'has_constructor_data': len([d for d in self.documents if d['metadata'].get('type') == 'constructor_profile']) > 0
        }
        
        # Performance stats
        if self.query_history:
            response_times = [q.response_time for q in self.query_history]
            confidences = [q.confidence for q in self.query_history]
            
            stats.update({
                'avg_response_time': round(np.mean(response_times), 3),
                'avg_confidence': round(np.mean(confidences) * 100, 1),
                'cache_hit_rate': round(sum(1 for q in self.query_history if q.metadata.get('cached', False)) / len(self.query_history) * 100, 1)
            })
        else:
            stats.update({
                'avg_response_time': 0,
                'avg_confidence': 0,
                'cache_hit_rate': 0
            })
        
        return stats
    
    def health_check(self) -> Dict[str, Any]:
        """System health check"""
        health = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'data_driven': True,
            'components': {}
        }
        
        # Database health
        try:
            db_stats = self.db_manager.get_system_stats()
            health['components']['database'] = {
                'status': 'ok' if db_stats.get('system_ready', False) else 'warning',
                'records': db_stats.get('total_records', 0),
                'message': 'Database loaded with F1 data' if db_stats.get('system_ready') else 'No F1 data loaded'
            }
        except Exception as e:
            health['components']['database'] = {
                'status': 'error',
                'error': str(e)
            }
        
        # Knowledge base health
        data_docs = len([d for d in self.documents if d['metadata'].get('type') != 'system_status'])
        health['components']['knowledge_base'] = {
            'status': 'ok' if data_docs > 0 else 'warning',
            'total_documents': len(self.documents),
            'data_driven_documents': data_docs,
            'message': f'{data_docs} documents generated from F1 data' if data_docs > 0 else 'No F1 data available'
        }
        
        # Search system
        health['components']['search_system'] = {
            'status': 'ok' if hasattr(self, 'document_embeddings') else 'error',
            'message': 'Hybrid search operational' if hasattr(self, 'document_embeddings') else 'Search system not initialized'
        }
        
        # LLM health
        try:
            lm_studio_url = self.config.get('lm_studio_url', 'http://localhost:1234')
            response = requests.get(f"{lm_studio_url}/v1/models", timeout=5)
            health['components']['llm'] = {
                'status': 'ok' if response.status_code == 200 else 'degraded',
                'connected': response.status_code == 200,
                'message': 'LM Studio connected' if response.status_code == 200 else 'Using fallback responses'
            }
        except:
            health['components']['llm'] = {
                'status': 'degraded',
                'connected': False,
                'message': 'LM Studio unavailable - using data-driven fallbacks'
            }
        
        # Overall status
        component_statuses = [comp['status'] for comp in health['components'].values()]
        if 'error' in component_statuses:
            health['status'] = 'degraded'
        elif 'warning' in component_statuses or 'degraded' in component_statuses:
            health['status'] = 'degraded'
        
        return health
    
    def clear_cache(self):
        """Clear query cache"""
        self.query_cache.clear()
        print("Query cache cleared")
    
    def get_sample_questions(self) -> List[Dict[str, Any]]:
        """Get sample questions based on available data"""
        samples = [
            {
                'category': 'Championships',
                'questions': [
                    "Who won the 2021 F1 championship?",
                    "Who was the 1987 world champion?", 
                    "Who won the 2020 championship?",
                    "1950 first F1 champion"
                ]
            },
            {
                'category': 'Driver Stats', 
                'questions': [
                    "How many wins does Lewis Hamilton have?",
                    "How many championships does Michael Schumacher have?",
                    "Max Verstappen career statistics",
                    "Ayrton Senna total wins"
                ]
            },
            {
                'category': 'Current Teams',
                'questions': [
                    "Who drives for Ferrari?",
                    "Current Red Bull drivers", 
                    "Mercedes current lineup",
                    "Which team does Charles Leclerc drive for?"
                ]
            },
            {
                'category': 'Race Results',
                'questions': [
                    "Who won the 2018 British Grand Prix?",
                    "Monaco Grand Prix recent winners",
                    "Last Italian Grand Prix winner", 
                    "Recent Spanish Grand Prix winners"
                ]
            }
        ]
        
        return samples
    
    def __del__(self):
        """Cleanup"""
        if hasattr(self, 'db_manager'):
            try:
                self.db_manager.close()
            except:
                pass