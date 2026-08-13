#!/bin/bash
# ============================================================
# SmartCivic AI - Mac / Linux Setup Script
# Run this after cloning the repo: bash setup.sh
# ============================================================

echo ""
echo "===================================="
echo "  SmartCivic AI - Project Setup"
echo "===================================="
echo ""

# --- Step 1: Create Python virtual environment ---
echo "[1/4] Creating Python virtual environment..."
if [ -d ".venv" ]; then
    echo "      .venv already exists, skipping..."
else
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "ERROR: Python3 not found. Please install Python 3.9+"
        exit 1
    fi
    echo "      Done!"
fi

# --- Step 2: Activate venv and install dependencies ---
echo "[2/4] Installing Python dependencies..."
source .venv/bin/activate
pip install -r backend/requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies."
    exit 1
fi
echo "      Done!"

# --- Step 3: Create .env from .env.example if it doesn't exist ---
echo "[3/4] Setting up environment variables..."
if [ -f "backend/.env" ]; then
    echo "      backend/.env already exists, skipping..."
else
    cp backend/.env.example backend/.env
    echo "      Created backend/.env from .env.example"
    echo "      IMPORTANT: Edit backend/.env with your actual credentials!"
fi

# --- Step 4: Done ---
echo "[4/4] Setup complete!"
echo ""
echo "===================================="
echo "  To start the server, run:"
echo "    source .venv/bin/activate"
echo "    python backend/app.py"
echo ""
echo "  Then open: http://127.0.0.1:5000"
echo "===================================="
echo ""
