#!/bin/bash
# Lotto Auto Purchase - Main Workflow Script (improved error handling & logging)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# Use VENV_PYTHON if set, otherwise default to .venv python
if [ -z "$VENV_PYTHON" ]; then
    VENV_PYTHON="$PROJECT_DIR/.venv/bin/python"
fi

# Logging setup
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"
LOGFILE="$LOG_DIR/purchase-$(date '+%Y%m%d').log"

log() {
    local level="$1"; shift
    local msg="$*"
    local ts
    ts="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "$ts [$level] $msg" | tee -a "$LOGFILE"
}

log "INFO" "🎰 Lotto Auto Purchase started"
log "INFO" "========================================"
log "INFO" "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Step 1: Check balance
log "INFO" "💰 Checking balance..."
# Run balance.py and capture both stdout and stderr.
# If balance.py fails (non-zero exit), log and exit.
if ! BALANCE_OUTPUT=$("$VENV_PYTHON" "$PROJECT_DIR/src/balance.py" 2>&1); then
    EXIT_CODE=$?
    log "ERROR" "balance.py failed with exit code $EXIT_CODE"
    # Log the full output for debugging
    log "ERROR" "balance.py output: $BALANCE_OUTPUT"
    # Also print to stderr for immediate visibility
    echo "$BALANCE_OUTPUT" >&2
    exit 1
fi

# Log successful output
log "INFO" "balance.py output: $BALANCE_OUTPUT"

# Parse available amount (keep original parsing logic)
AVAILABLE_AMOUNT=$(echo "$BALANCE_OUTPUT" | grep -oE '[0-9,]+원' | tail -n 1 | tr -d '원,')

if [ -z "$AVAILABLE_AMOUNT" ]; then
    log "ERROR" "Could not parse available amount from balance.py output"
    log "ERROR" "balance.py output was: $BALANCE_OUTPUT"
    exit 1
fi

log "INFO" "Parsed available amount: ₩${AVAILABLE_AMOUNT}"

# Step 2: Charge if needed
MIN_REQUIRED=10000
if [ "$AVAILABLE_AMOUNT" -lt "$MIN_REQUIRED" ]; then
    log "INFO" "Balance low (₩${AVAILABLE_AMOUNT}). Charging ₩10,000..."
    if ! "$VENV_PYTHON" "$PROJECT_DIR/src/charge.py" 10000 >>"$LOGFILE" 2>&1; then
        log "ERROR" "charge.py failed. See $LOGFILE for details."
        exit 1
    fi
    log "INFO" "Charge completed."
fi

# Step 3: Buy Lotto 720
log "INFO" "🎫 Buying Lotto 720..."
if ! "$VENV_PYTHON" "$PROJECT_DIR/src/lotto720.py" >>"$LOGFILE" 2>&1; then
    log "ERROR" "lotto720.py failed. See $LOGFILE for details."
    exit 1
fi
log "INFO" "Lotto 720 purchase completed."

# Step 4: Buy Lotto 645
log "INFO" "🎫 Buying Lotto 645..."
if ! "$VENV_PYTHON" "$PROJECT_DIR/src/lotto645.py" >>"$LOGFILE" 2>&1; then
    log "ERROR" "lotto645.py failed. See $LOGFILE for details."
    exit 1
fi
log "INFO" "Lotto 645 purchase completed."

echo ""
log "INFO" "✅ All tasks completed successfully!"
log "INFO" "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"