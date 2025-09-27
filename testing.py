# F1 RAG System - Comprehensive Test Suite
# Run this to test 15 different types of F1 questions

from f1_rag import F1RAGSystem, F1DatabaseManager
from config import config
import time
from pathlib import Path
import logging
import sys

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

def test_f1_rag_system():
    print("=" * 60)
    print("🏁 F1 RAG SYSTEM - COMPREHENSIVE TEST SUITE")
    print("=" * 60)
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
    rag = F1RAGSystem(db_manager, {
        'lm_studio_url': config.LLM_URL,
        'embedding_model': config.EMBEDDING_MODEL,
        'top_k_retrieval': config.TOP_K_RETRIEVAL,
        'temperature': config.LLM_TEMPERATURE
    })
            
    logger.info("F1 RAG System initialization complete")
    return True
     
    # Test questions covering all categories
    test_questions = [
        # Championship Questions
        "Who won the 2021 F1 championship?",
        "Who was the 2020 world champion?",
        "Who won the 1987 championship?",
        "Who was the first F1 champion ever?",
        
        # Driver Statistics
        "How many wins does Lewis Hamilton have?",
        "How many championships does Max Verstappen have?",
        "Who has the most race wins in F1 history?",
        
        # Current Team Information
        "Who drives for Ferrari?",
        "Current Red Bull drivers",
        "Which team does Lewis Hamilton drive for?",
        "Mercedes current lineup",
        
        # General F1 Knowledge
        "Who is the current F1 world champion?",
        "What team does Max Verstappen drive for?",
        
        # Historical Questions
        "Giuseppe Farina championship details",
        "Nelson Piquet 1987 season information"
    ]
    
    results = []
    total_time = 0
    
    for i, question in enumerate(test_questions, 1):
        print(f"🔍 TEST {i:2d}/15: {question}")
        print("-" * 40)
        
        start_time = time.time()
        result = rag.query(question)
        end_time = time.time()
        
        response_time = end_time - start_time
        total_time += response_time
        
        print(f"📝 Answer: {result.answer}")
        print(f"📊 Confidence: {result.confidence:.2f}")
        print(f"⏱️  Response Time: {response_time:.2f}s")
        print(f"🔍 Query Type: {result.query_type.value}")
        print(f"📚 Sources Used: {len(result.sources)}")
        
        # Store results
        results.append({
            'question': question,
            'answer': result.answer,
            'confidence': result.confidence,
            'response_time': response_time,
            'query_type': result.query_type.value,
            'sources_count': len(result.sources)
        })
        
        print()
    
    # Summary Statistics
    print("=" * 60)
    print("📈 TEST SUMMARY")
    print("=" * 60)
    
    avg_confidence = sum(r['confidence'] for r in results) / len(results)
    avg_response_time = total_time / len(results)
    
    print(f"Total Questions Tested: {len(results)}")
    print(f"Total Test Time: {total_time:.2f} seconds")
    print(f"Average Response Time: {avg_response_time:.2f}s")
    print(f"Average Confidence: {avg_confidence:.2f} ({avg_confidence*100:.1f}%)")
    print()
    
    # Category Breakdown
    query_types = {}
    for r in results:
        qt = r['query_type']
        if qt not in query_types:
            query_types[qt] = []
        query_types[qt].append(r)
    
    print("📊 Query Type Distribution:")
    for qt, queries in query_types.items():
        avg_conf = sum(q['confidence'] for q in queries) / len(queries)
        avg_time = sum(q['response_time'] for q in queries) / len(queries)
        print(f"  • {qt.upper()}: {len(queries)} queries, "
              f"avg confidence: {avg_conf:.2f}, avg time: {avg_time:.2f}s")
    
    print()
    
    # Performance Analysis
    fast_queries = [r for r in results if r['response_time'] < 2.0]
    high_conf_queries = [r for r in results if r['confidence'] > 0.7]
    
    print("🚀 Performance Analysis:")
    print(f"  • Fast queries (<2s): {len(fast_queries)}/{len(results)} ({len(fast_queries)/len(results)*100:.1f}%)")
    print(f"  • High confidence (>0.7): {len(high_conf_queries)}/{len(results)} ({len(high_conf_queries)/len(results)*100:.1f}%)")
    
    # System Stats
    print()
    print("🔧 System Statistics:")
    stats = rag.get_system_stats()
    print(f"  • Documents Loaded: {stats['total_documents']}")
    print(f"  • Cache Size: {stats['cache_size']}")
    print(f"  • Data Coverage: {stats['data_coverage']}")
    
    print()
    print("✅ Test completed successfully!")
    
    return results, stats

if __name__ == "__main__":
    test_results, system_stats = test_f1_rag_system()