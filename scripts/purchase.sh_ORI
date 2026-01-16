#!/bin/bash
# Lotto Auto Purchase - Main Workflow Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# Use VENV_PYTHON if set, otherwise default to .venv python
if [ -z "$VENV_PYTHON" ]; then
    VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
fi

echo "🎰 Lotto Auto Purchase"
echo "========================================"
date "+%Y-%m-%d %H:%M:%S"
echo ""

# Step 1: Check balance
echo "💰 Checking balance..."
BALANCE_OUTPUT=$("$VENV_PYTHON" "$PROJECT_DIR/src/balance.py" 2>&1)
echo "$BALANCE_OUTPUT"

AVAILABLE_AMOUNT=$(echo "$BALANCE_OUTPUT" | grep -oE '[0-9,]+원' | tail -n 1 | tr -d '원,')

if [ -z "$AVAILABLE_AMOUNT" ]; then
    echo "❌ Error: Could not parse available amount"
    exit 1
fi

# Step 2: Charge if needed
MIN_REQUIRED=10000
if [ "$AVAILABLE_AMOUNT" -lt "$MIN_REQUIRED" ]; then
    echo "💳 Balance low (₩${AVAILABLE_AMOUNT}). Charging ₩10,000..."
    "$VENV_PYTHON" "$PROJECT_DIR/src/charge.py" 10000
fi

# Step 3: Buy Lotto 720
echo "🎫 Buying Lotto 720..."
"$VENV_PYTHON" "$PROJECT_DIR/src/lotto720.py"

# Step 4: Buy Lotto 645
echo "🎫 Buying Lotto 645..."
"$VENV_PYTHON" "$PROJECT_DIR/src/lotto645.py"

echo ""
echo "✅ All tasks completed successfully!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
