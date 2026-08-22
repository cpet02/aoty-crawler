#!/usr/bin/env python3
"""
Launch the AOTY Crawler Streamlit UI
"""

import subprocess
import sys
import os

# The emoji in this script's print() calls crash with UnicodeEncodeError on
# Windows consoles that default to a legacy codepage (e.g. cp1252) instead
# of UTF-8. Force UTF-8 output where the runtime supports it (Python 3.7+).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, 'reconfigure'):
        try:
            _stream.reconfigure(encoding='utf-8')
        except Exception:
            pass


def main():
    ui_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(ui_dir)
    app_path = os.path.join(ui_dir, "app.py")

    print("🎵 Starting AOTY Crawler UI...")
    print(f"UI Directory: {ui_dir}")
    print(f"App Path: {app_path}")

    # Check if streamlit is installed
    try:
        import streamlit
        print("✅ Streamlit is installed")
    except ImportError:
        # requirements.txt lives at the project root, not under ui/
        print("❌ Streamlit is not installed. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], cwd=project_root)
    
    # Run streamlit with auto-allow email prompt
    print("\n🚀 Launching UI...")
    print("Open your browser to: http://localhost:8501")
    print("Press Ctrl+C to stop\n")
    
    # Use environment variable to skip email prompt
    env = os.environ.copy()
    env['STREAMLIT_SERVER_HEADLESS'] = 'true'
    # Force UTF-8 in the streamlit subprocess too, for the same reason as above.
    env['PYTHONIOENCODING'] = 'utf-8'
    
    subprocess.run([sys.executable, "-m", "streamlit", "run", app_path, "--server.headless", "true"], cwd=ui_dir, env=env)

if __name__ == "__main__":
    main()
