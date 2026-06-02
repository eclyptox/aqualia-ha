#!/bin/bash
set -e

echo "Starting Aqualia Water Consumption addon..."
cd /app
python3 app/main.py
