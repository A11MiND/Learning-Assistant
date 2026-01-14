#!/bin/bash

echo "Starting DSE AI Learner Platform (Streamlit)..."

# Setup Virtual Environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Starting Application..."
# Try to get local IP (works on Mac)
IP=$(ipconfig getifaddr en0)
if [ -z "$IP" ]; then
    IP=$(ipconfig getifaddr en1) # Try Wi-Fi if Ethernet is empty
fi

if [ -z "$IP" ]; then
    IP="localhost"
fi
echo "Access the app at http://$IP:8501"

# Run without flags, let config.toml handle it
streamlit run app.py
