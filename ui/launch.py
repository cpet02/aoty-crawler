#!/usr/bin/env python3
"""
Launch the AOTY Crawler Streamlit UI
"""

import subprocess
import sys
import os

def main():
    ui_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(ui_dir, "app.py")
    
    print("🎵 Starting AOTY Crawler UI...")
    print(f"UI Directory: {ui_dir}")
    print(f"App Path: {app_path}")
    
    # Check if streamlit is installed
    try:
        import streamlit
        print("✅ Streamlit is installed")
    except ImportError:
        print("❌ Streamlit is not installed. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=ui_dir)
    
    # Run streamlit with auto-allow email prompt
    print("\n🚀 Launching UI...")
    print("Open your browser to: http://localhost:8501")
    print("Press Ctrl+C to stop\n")
    
    # Use environment variable to skip email prompt
    env = os.environ.copy()
    env['STREAMLIT_SERVER_HEADLESS'] = 'true'
    
    subprocess.run([sys.executable, "-m", "streamlit", "run", app_path, "--server.headless", "true"], cwd=ui_dir, env=env)

if __name__ == "__main__":
    main()
