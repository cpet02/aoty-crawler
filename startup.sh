#!/bin/bash
# Radius startup script

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.10+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
if [ "$(echo "$PYTHON_VERSION < 3.10" | bc -l)" -eq 1 ]; then
    echo "❌ Python $PYTHON_VERSION is too old. Please install Python 3.10+"
    exit 1
fi

echo "✅ Python $PYTHON_VERSION detected"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

if [ -f "requirements.txt" ]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

echo "✅ Radius is ready!"
echo ""
echo "Usage:"
echo "  python -m radius \"Artist - Album\"   # CLI"
echo "  python -m ui.launch                  # Browser UI"
echo ""
