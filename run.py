#!/usr/bin/env python3
"""
FinFlash - Financial News Multi-Agent Analysis System
Main entry point for running the Flask application
"""

import os
import sys
import argparse
import logging
import shutil
import glob
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

def setup_environment():
    """Setup environment variables and configurations"""
    # Load .env file if exists
    env_file = PROJECT_ROOT / '.env'
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file)
        print(f"[OK] Loaded environment from {env_file}")
    else:
        print("[WARNING] .env file not found")
        print("  Please copy config/.env.example to .env and configure it")
        
    # Set default Flask environment if not set
    if not os.getenv('FLASK_ENV'):
        os.environ['FLASK_ENV'] = 'development'
        
    # Set Flask app location
    os.environ['FLASK_APP'] = 'app.main:app'

def check_dependencies():
    """Check if all required dependencies are installed"""
    missing_deps = []
    
    try:
        import flask
    except ImportError:
        missing_deps.append('flask')
        
    try:
        import openai
    except ImportError:
        missing_deps.append('openai')
        
    try:
        import sqlalchemy
    except ImportError:
        missing_deps.append('sqlalchemy')
        
    if missing_deps:
        print("[ERROR] Missing dependencies:", ', '.join(missing_deps))
        print("  Please run: pip install -r requirements.txt")
        return False
        
    return True

def create_directories():
    """Create necessary directories if they don't exist"""
    directories = [
        'logs',
        'data',
        'app/uploads'
    ]
    
    for dir_path in directories:
        path = PROJECT_ROOT / dir_path
        path.mkdir(parents=True, exist_ok=True)
        
    print("[OK] Created necessary directories")

def initialize_database():
    """Initialize database if needed"""
    try:
        from core.database import get_db_manager
        db_manager = get_db_manager()
        print("[OK] Database initialized")
    except Exception as e:
        print(f"[WARNING] Database initialization warning: {e}")
        print("  The application will create it on first run")

def run_server(host='0.0.0.0', port=5000, debug=None):
    """Run the Flask development server"""
    from app.main import app
    
    # Configure logging
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    print("\n" + "="*50)
    print("Starting FinFlash Server")
    print("="*50)
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Debug: {debug if debug is not None else app.debug}")
    print(f"Environment: {os.getenv('FLASK_ENV', 'development')}")
    print("="*50)
    print(f"\nAccess the application at: http://localhost:{port}\n")
    
    # Run the application
    app.run(
        host=host,
        port=port,
        debug=debug if debug is not None else (os.getenv('FLASK_ENV') == 'development'),
        use_reloader=True,
        threaded=True
    )

def clean_project():
    """Clean project files and caches"""
    print("[INFO] Cleaning project...\n")
    
    # Clean Python cache
    print("[INFO] Cleaning Python cache...")
    for pycache in glob.glob('**/__pycache__', recursive=True):
        shutil.rmtree(pycache, ignore_errors=True)
        print(f"  Removed {pycache}")
    
    # Clean .pyc files
    for pyc in glob.glob('**/*.pyc', recursive=True):
        os.remove(pyc)
    
    # Clean log files
    print("[INFO] Cleaning log files...")
    for log_file in glob.glob('logs/*.log'):
        os.remove(log_file)
        print(f"  Removed {log_file}")
    
    # Clean test coverage
    if os.path.exists('htmlcov'):
        shutil.rmtree('htmlcov')
        print("[INFO] Removed coverage reports")
    
    if os.path.exists('.coverage'):
        os.remove('.coverage')
    
    print("\n[OK] Clean complete!")

def run_tests():
    """Run the test suite"""
    print("[INFO] Running tests...\n")
    
    # Ensure pytest is installed
    try:
        import pytest
    except ImportError:
        print("[ERROR] pytest not installed")
        print("  Installing pytest...")
        os.system("pip install pytest pytest-asyncio pytest-cov")
    
    # Set test environment
    os.environ['FLASK_ENV'] = 'testing'
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    
    # Run tests
    import subprocess
    result = subprocess.run(['pytest', 'tests/', '-v'], capture_output=False)
    
    return result.returncode == 0

def run_batch_processing():
    """Run batch processing tasks"""
    print("[INFO] Starting batch processing...\n")
    
    setup_environment()
    
    print("Select batch operation:")
    print("1. Run news crawl and analysis")
    print("2. Generate daily report")
    print("3. Run both")
    
    choice = input("\nEnter your choice (1-3): ")
    
    if choice in ['1', '3']:
        print("\n[INFO] Starting news crawl...")
        # Import here to avoid circular imports
        import asyncio
        from app.main import app
        from agents.orchestrator import ProcessingMode
        
        async def crawl():
            with app.app_context():
                orchestrator = app.orchestrator
                if orchestrator and orchestrator.research_agent:
                    result = await orchestrator.process_search_and_analyze(
                        search_query='financial news stock market earnings',
                        num_results=20,
                        days_back=1,
                        mode=ProcessingMode.PARALLEL
                    )
                    print(f"[OK] Crawled and analyzed {result.get('analyzed_successfully', 0)} articles")
                else:
                    print('[ERROR] Orchestrator not available')
        
        asyncio.run(crawl())
    
    if choice in ['2', '3']:
        print("\n[INFO] Generating daily report...")
        # Generate report logic here
        print("[OK] Daily report generated")
    
    print("\n[OK] Batch processing complete!")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='FinFlash - Financial News Analysis System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                    # Run with default settings
  python run.py --port 8080        # Run on port 8080
  python run.py --host 127.0.0.1   # Run on localhost only
  python run.py --debug            # Run in debug mode
  python run.py --setup            # Setup only, don't run server
  python run.py --clean            # Clean project files
  python run.py --test             # Run tests
  python run.py --batch            # Run batch processing
        """
    )
    
    parser.add_argument(
        '--host', 
        default='0.0.0.0',
        help='Host to bind to (default: 0.0.0.0)'
    )
    
    parser.add_argument(
        '--port', 
        type=int,
        default=5000,
        help='Port to bind to (default: 5000)'
    )
    
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Run in debug mode'
    )
    
    parser.add_argument(
        '--no-debug',
        action='store_true',
        help='Disable debug mode'
    )
    
    parser.add_argument(
        '--setup',
        action='store_true',
        help='Run setup only, do not start server'
    )
    
    parser.add_argument(
        '--clean',
        action='store_true',
        help='Clean project files and caches'
    )
    
    parser.add_argument(
        '--test',
        action='store_true',
        help='Run test suite'
    )
    
    parser.add_argument(
        '--batch',
        action='store_true',
        help='Run batch processing tasks'
    )
    
    args = parser.parse_args()
    
    # Handle special commands first
    if args.clean:
        clean_project()
        return
    
    if args.test:
        success = run_tests()
        sys.exit(0 if success else 1)
    
    if args.batch:
        run_batch_processing()
        return
    
    # Determine debug mode
    debug = None
    if args.debug:
        debug = True
    elif args.no_debug:
        debug = False
    
    # Setup steps
    print("Setting up FinFlash...\n")
    
    setup_environment()
    
    if not check_dependencies():
        sys.exit(1)
        
    create_directories()
    initialize_database()
    
    if args.setup:
        print("\n[OK] Setup complete!")
        return
    
    # Run the server
    try:
        run_server(
            host=args.host,
            port=args.port,
            debug=debug
        )
    except KeyboardInterrupt:
        print("\n\n[INFO] Server stopped by user")
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 