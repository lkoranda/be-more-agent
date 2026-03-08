#!/bin/bash
# Installs a desktop entry for be-more-agent pointing to this directory.
# Run once after setup.sh to get the app in your Pi launcher.

INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$DESKTOP_DIR/be-more-agent.desktop"

mkdir -p "$DESKTOP_DIR"

# Use the idle face as icon if it exists, otherwise fall back to terminal icon
ICON_PATH="$INSTALL_DIR/faces/idle/idle_0.png"
if [ ! -f "$ICON_PATH" ]; then
    ICON_PATH="utilities-terminal"
fi

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=Be More Agent
Comment=Launch the Be More Agent AI assistant
Exec=$INSTALL_DIR/start_agent.sh
Path=$INSTALL_DIR
Icon=$ICON_PATH
Terminal=true
Categories=Utility;
EOF

chmod +x "$DESKTOP_FILE" 2>/dev/null || true
echo "Desktop entry installed to: $DESKTOP_FILE"
echo "You may need to log out and back in for it to appear in your launcher."
