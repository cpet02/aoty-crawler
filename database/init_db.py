#!/usr/bin/env python3
"""
Database initialization script for AOTY Crawler
Creates the database and all necessary tables
"""

import os
import sys
from database.models import init_database, create_database_engine, create_tables


def main():
    """Main function to initialize the database"""
    print("Initializing AOTY Crawler Database...")
    
    try:
        # Initialize database
        engine = init_database()
        
        # Verify tables were created
        from database.models import Base
        inspector = Base.metadata.reflect(engine)
        tables = Base.metadata.tables.keys()
        
        print(f"✅ Database initialized successfully!")
        print(f"📊 Tables created: {', '.join(sorted(tables))}")
        
        # Show database info
        db_url = os.environ.get('DATABASE_URL', 'sqlite:///data/aoty_database.db')
        if db_url.startswith('sqlite:///'):
            db_path = db_url.replace('sqlite:///', '')
            if os.path.exists(db_path):
                size = os.path.getsize(db_path)
                print(f"📁 Database file: {db_path} ({size} bytes)")
        
        return 0
        
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
