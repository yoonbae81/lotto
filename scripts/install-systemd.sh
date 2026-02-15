#!/bin/bash
# Lotto Auto Purchase - Systemd Timer Installation Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

echo "Lotto - Systemd Timer Installation"
echo "========================================"
echo "Project directory: $PROJECT_DIR"
echo ""

# Setup systemd
echo "Setting up systemd timer..."
mkdir -p "$SYSTEMD_USER_DIR"

# Copy and modify service file with actual project path
echo "Creating lotto.service..."
sed "s|{{PROJECT_ROOT}}|$PROJECT_DIR|g" \
    "$SCRIPT_DIR/systemd/lotto.service" > "$SYSTEMD_USER_DIR/lotto.service"

# Copy timer file
echo "Copying lotto.timer..."
cp "$SCRIPT_DIR/systemd/lotto.timer" "$SYSTEMD_USER_DIR/"

echo "Systemd files installed"
echo ""

# Reload systemd daemon
echo "Reloading systemd daemon..."
systemctl --user daemon-reload

# Enable linger for the user
echo "Enabling linger for user $USER..."
loginctl enable-linger "$USER"

# Enable and start timer
echo "Enabling and starting timer..."
systemctl --user enable lotto.timer
systemctl --user start lotto.timer

echo ""
echo "Timer installation completed!"
echo ""
echo "Useful commands:"
echo "  • Check timer status:   systemctl --user status lotto.timer"
echo "  • Check service logs:   journalctl --user -u lotto.service"
echo "  • Follow logs:          journalctl --user -u lotto.service -f"
echo ""
