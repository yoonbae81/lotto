#!/bin/bash
# Lotto Auto Purchase - Main Workflow Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# Use VENV_PYTHON if set, otherwise default to .venv python
if [ -z "$VENV_PYTHON" ]; then
    VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
fi

# Parse arguments
BUY_720=true
BUY_645=true

while [[ $# -gt 0 ]]; do
    case "$1" in
        --645)
            BUY_720=false
            BUY_645=true
            shift
            ;;
        --720)
            BUY_645=false
            BUY_720=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Step 0: Login and Save Session (Initial once)
echo "Logging in and saving session..."
"$VENV_PYTHON" "$PROJECT_DIR/src/login.py"

# Step 1: Check balance
echo "Checking balance..."
# Using tee to show output in real-time while capturing it
"$VENV_PYTHON" "$PROJECT_DIR/src/balance.py" 2>&1 | tee balance.log
BALANCE_OUTPUT=$(cat balance.log)
rm balance.log

AVAILABLE_AMOUNT=$(echo "$BALANCE_OUTPUT" | grep "__RESULT__" | grep -o '"available_amount": \?[0-9]*' | tr -dc '0-9')

if [ -z "$AVAILABLE_AMOUNT" ]; then
    echo "Error: Could not parse available amount"
    exit 1
fi

# Step 2: Charge if needed
MIN_REQUIRED=10000
if [ "$AVAILABLE_AMOUNT" -lt "$MIN_REQUIRED" ]; then
    echo "Balance low (₩${AVAILABLE_AMOUNT}). Charging ₩10,000..."
    "$VENV_PYTHON" "$PROJECT_DIR/src/charge.py" 10000
    
    echo "Updating balance after charge..."
    "$VENV_PYTHON" "$PROJECT_DIR/src/balance.py"
fi

# Step 3: Buy Lotto 720
if [ "$BUY_720" = true ]; then
    echo "Buying Lotto 720..."
    "$VENV_PYTHON" "$PROJECT_DIR/src/lotto720.py"
else
    echo "Skipping Lotto 720"
fi

# Step 4: Buy Lotto 645
if [ "$BUY_645" = true ]; then
    echo "Buying Lotto 645..."
    "$VENV_PYTHON" "$PROJECT_DIR/src/lotto645.py"
else
    echo "Skipping Lotto 645"
fi

echo ""
echo "All tasks completed successfully!"

