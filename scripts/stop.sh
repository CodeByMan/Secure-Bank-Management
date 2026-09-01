#!/bin/bash
# stop.sh - Stop the Flask application

# Message colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}=== Stopping the banking application ===${NC}\n"

# Find and terminate the Flask process
FLASK_PID=$(ps aux | grep 'flask run' | grep -v grep | awk '{print $2}')

if [ -z "$FLASK_PID" ]; then
    echo -e "${YELLOW}✗ No Flask process is running${NC}"
else
    echo -e "Stopping Flask process (PID: $FLASK_PID)..."
    kill $FLASK_PID
    echo -e "${RED}✓ Application stopped${NC}"
fi

# Stop Python too if necessary
PYTHON_FLASK=$(ps aux | grep 'python.*app.py' | grep -v grep | awk '{print $2}')
if [ ! -z "$PYTHON_FLASK" ]; then
    kill $PYTHON_FLASK
    echo -e "${RED}✓ Python process stopped${NC}"
fi

echo ""
