# app.py - Simplified Flask API Server for F1 RAG System (ALL functionality preserved)
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import logging
import sys
import os
from pathlib import Path
from datetime import datetime
import uuid

# Import consolidated modules
from config import config
from f1_rag import F1RAGSystem, F1DatabaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('f1_rag.log')
    ]
)

logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = config.SECRET_KEY
CORS(app)

# Global variables
rag_system = None
session_queries = {}  # Store queries by session

def initialize_system():
    """Initialize RAG system"""
    global rag_system
    
    try:
        logger.info("Initializing F1 RAG System...")
                # Load data if database is empty
                # Initialize database manager first
        db_manager = F1DatabaseManager(config.DATABASE_PATH)

        # Load data first
        data_path = Path(config.DATA_PATH)
        if data_path.exists():
            db_stats = db_manager.get_system_stats()
            if not db_stats.get('system_ready', False):
                logger.info("Loading F1 data into database...")
                loaded_counts = db_manager.load_csv_data(str(data_path))
                logger.info(f"Loaded {len(loaded_counts)} CSV files")

        # THEN create RAG system
        rag_system = F1RAGSystem(db_manager, {
            'lm_studio_url': config.LLM_URL,
            'embedding_model': config.EMBEDDING_MODEL,
            'top_k_retrieval': config.TOP_K_RETRIEVAL,
            'temperature': config.LLM_TEMPERATURE
        })
                
        logger.info("F1 RAG System initialization complete")
        return True
        
    except Exception as e:
        logger.error(f"System initialization failed: {e}")
        return False

@app.route('/')
def serve_frontend():
    """Serve the main HTML frontend"""
    # Check multiple locations for the HTML file
    html_locations = [
        Path('index.html'),           # Root directory
        Path('static/index.html'),    # Static directory
        Path('templates/index.html')  # Templates directory
    ]
    
    for html_path in html_locations:
        if html_path.exists():
            logger.info(f"Serving frontend from: {html_path}")
            return send_file(str(html_path))
    
    # If no HTML file found, return a helpful message
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>F1 RAG System - Setup Required</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            .error {{ color: #d32f2f; }}
            .success {{ color: #2e7d32; }}
            code {{ background: #f5f5f5; padding: 2px 4px; border-radius: 3px; }}
        </style>
    </head>
    <body>
        <h1>F1 RAG System</h1>
        <p class="error">Frontend HTML file not found.</p>
        <p>Please copy <code>index.html</code> to one of these locations:</p>
        <ul>
            <li><code>./index.html</code> (project root)</li>
            <li><code>./static/index.html</code> (static directory)</li>
        </ul>
        <p class="success">API is running at <a href="/api/health">/api/health</a></p>
        <p>System Status: {'Ready' if rag_system else 'Initializing...'}</p>
    </body>
    </html>
    """, 200

@app.route('/api/query', methods=['POST'])
def handle_query():
    """Handle F1 RAG queries with session tracking"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
            
        question = data.get('question', '').strip()
        session_id = data.get('session_id', str(uuid.uuid4()))
        
        if not question:
            return jsonify({'error': 'Question cannot be empty'}), 400
        
        if not rag_system:
            return jsonify({'error': 'RAG system not available'}), 503
        
        logger.info(f"Processing query: '{question[:50]}...' [Session: {session_id[:8]}]")
        
        # Process query
        result = rag_system.query(question)
        
        # Store query in session history
        if session_id not in session_queries:
            session_queries[session_id] = []
        
        query_record = {
            'id': len(session_queries[session_id]) + 1,
            'question': question,
            'answer': result.answer,
            'confidence': result.confidence,
            'query_type': result.query_type.value,
            'response_time': result.response_time,
            'sources_count': len(result.sources),
            'timestamp': datetime.now().isoformat(),
            'cached': result.metadata.get('cached', False)
        }
        
        session_queries[session_id].append(query_record)
        
        # Prepare response
        response = {
            'answer': result.answer,
            'confidence': round(result.confidence, 3),
            'query_type': result.query_type.value,
            'response_time': round(result.response_time, 3),
            'sources': result.sources,
            'sources_count': len(result.sources),
            'session_id': session_id,
            'cached': result.metadata.get('cached', False),
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"Query completed - Confidence: {result.confidence:.3f}, Time: {result.response_time:.3f}s")
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Query processing error: {e}")
        return jsonify({
            'error': 'Query processing failed',
            'message': str(e)
        }), 500

@app.route('/api/session/<session_id>/history', methods=['GET'])
def get_session_history(session_id):
    """Get query history for a session"""
    try:
        history = session_queries.get(session_id, [])
        return jsonify({
            'session_id': session_id,
            'query_count': len(history),
            'queries': history
        })
    except Exception as e:
        logger.error(f"Failed to get session history: {e}")
        return jsonify({'error': 'Failed to retrieve history'}), 500

@app.route('/api/session/<session_id>/clear', methods=['POST'])
def clear_session_history(session_id):
    """Clear query history for a session"""
    try:
        if session_id in session_queries:
            del session_queries[session_id]
        return jsonify({'message': 'Session history cleared'})
    except Exception as e:
        logger.error(f"Failed to clear session history: {e}")
        return jsonify({'error': 'Failed to clear history'}), 500

@app.route('/api/stats', methods=['GET'])
def get_system_stats():
    """Get comprehensive system statistics"""
    try:
        if not rag_system:
            return jsonify({'error': 'RAG system not available'}), 503
        
        # Get RAG system stats
        stats = rag_system.get_system_stats()
        
        # Add session stats
        total_sessions = len(session_queries)
        total_session_queries = sum(len(queries) for queries in session_queries.values())
        
        stats.update({
            'active_sessions': total_sessions,
            'session_queries': total_session_queries,
            'rag_system_ready': rag_system is not None,
            'cache_size': len(rag_system.query_cache) if rag_system else 0
        })
        
        return jsonify(stats)
        
    except Exception as e:
        logger.error(f"Failed to get system stats: {e}")
        return jsonify({'error': 'Failed to retrieve statistics'}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """System health check with comprehensive status"""
    try:
        health = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'rag_system': rag_system is not None,
            'components': {}
        }
        
        # RAG system health
        if rag_system:
            rag_health = rag_system.health_check()
            health['components'] = rag_health['components']
            health['status'] = rag_health['status']
        else:
            health['components']['rag'] = {
                'status': 'error',
                'error': 'RAG system not initialized'
            }
            health['status'] = 'error'
        
        return jsonify(health)
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/api/sample-questions', methods=['GET'])
def get_sample_questions():
    """Get sample F1 questions organized by category"""
    samples = [
        {
            'category': 'Recent Championships',
            'questions': [
                "Who won the 2016 F1 championship?",
                "How many championships does Max Verstappen have?"
            ]
        },
        {
            'category': 'Driver Records & Stats',
            'questions': [
                "How many championships did Nikki Lauda win",
                "How many podiums does Lando Norris have?"
            ]
        },
        {
            'category': 'Current Teams 2024',
            'questions': [
                "Who drives for Ferrari in 2024?",
                "Which team does Yuki Tsunoda drive for?"
            ]
        },
        {
            'category': 'F1 History & Legends',
            'questions': [
                "Who was the 1950 F1 champion ever?",
                "Who won the 1987 F1 championship?"
                ]
        }
    ]
    
    return jsonify(samples)

# Additional utility routes

@app.route('/api/debug/sessions', methods=['GET'])
def debug_sessions():
    """Debug endpoint to view active sessions"""
    if not config.DEBUG:
        return jsonify({'error': 'Debug endpoints only available in debug mode'}), 403
    
    session_info = {}
    for session_id, queries in session_queries.items():
        session_info[session_id] = {
            'query_count': len(queries),
            'last_query': queries[-1]['timestamp'] if queries else None,
            'first_query': queries[0]['timestamp'] if queries else None
        }
    
    return jsonify({
        'total_sessions': len(session_queries),
        'sessions': session_info
    })

@app.route('/api/debug/database', methods=['GET'])
def debug_database():
    """Debug endpoint to view database status"""
    if not config.DEBUG:
        return jsonify({'error': 'Debug endpoints only available in debug mode'}), 403
    
    if not rag_system or not rag_system.db_manager:
        return jsonify({'error': 'Database not available'}), 503
    
    try:
        # Get table counts
        tables = ['drivers', 'constructors', 'races', 'results', 'query_analytics']
        table_counts = {}
        
        for table in tables:
            try:
                result = rag_system.db_manager.execute_query(f"SELECT COUNT(*) FROM {table}")
                table_counts[table] = result[0][0] if result else 0
            except:
                table_counts[table] = 'Error'
        
        return jsonify({
            'database_path': rag_system.db_manager.db_path,
            'table_counts': table_counts,
            'system_stats': rag_system.db_manager.get_system_stats()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current system configuration (non-sensitive values only)"""
    safe_config = {
        'host': config.HOST,
        'port': config.PORT,
        'debug': config.DEBUG,
        'llm_url': config.LLM_URL,
        'llm_model': config.LLM_MODEL,
        'embedding_model': config.EMBEDDING_MODEL,
        'top_k_retrieval': config.TOP_K_RETRIEVAL,
        'confidence_threshold': config.CONFIDENCE_THRESHOLD,
        'data_path': config.DATA_PATH,
        'database_path': config.DATABASE_PATH
    }
    
    return jsonify(safe_config)

# Error handlers

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Endpoint not found',
        'available_endpoints': [
            '/api/health',
            '/api/query',
            '/api/stats',
            '/api/sample-questions',
            '/api/session/<id>/history',
            '/api/session/<id>/clear'
        ]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'error': 'Internal server error',
        'message': 'Check server logs for details'
    }), 500

@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors"""
    return jsonify({
        'error': 'Method not allowed',
        'message': 'Check the HTTP method for this endpoint'
    }), 405

# Startup banner
def print_startup_banner():
    """Print startup information"""
    banner = f"""
{'='*60}
🏁 F1 RAG System - Production Server
{'='*60}
Configuration:
  • Host: {config.HOST}
  • Port: {config.PORT}
  • Debug: {config.DEBUG}
  • Database: {config.DATABASE_PATH}
  • Data Path: {config.DATA_PATH}
  • LLM URL: {config.LLM_URL}

Endpoints:
  • Frontend: http://{config.HOST}:{config.PORT}
  • API: http://{config.HOST}:{config.PORT}/api/
  • Health: http://{config.HOST}:{config.PORT}/api/health
{'='*60}
    """
    print(banner)

if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('static', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    
    # Print startup banner
    print_startup_banner()
    
    # Initialize system
    if initialize_system():
        logger.info("System ready - Starting Flask server...")
        
        # Start server with proper config
        try:
            app.run(
                host=config.HOST,
                port=config.PORT,
                debug=config.DEBUG,
                threaded=True
            )
        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        except Exception as e:
            logger.error(f"Server failed to start: {e}")
    else:
        logger.error("System initialization failed. Exiting.")
        sys.exit(1)