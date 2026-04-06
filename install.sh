#!/bin/bash

# KUTimeout Installation Script

NAME="kutimeout"
SHARE_DIR="/usr/share/$NAME"
BIN_FILE="/usr/bin/$NAME"
AUTOSTART_DIR="$HOME/.config/autostart"

echo "Starting $NAME installation..."

# Run migration/cleanup if migrate.sh exists
if [ -f "./migrate.sh" ]; then
    chmod +x ./migrate.sh
    ./migrate.sh
fi

# 1. Setup Autostart
echo "Setting up autostart..."
mkdir -p "$AUTOSTART_DIR"
cp -- "$NAME.desktop" "$AUTOSTART_DIR/$NAME.desktop"
chmod +x "$AUTOSTART_DIR/$NAME.desktop"

# 2. Global Installation
if [ "$(pwd)" != "$SHARE_DIR" ]; then
    echo "Installing to $SHARE_DIR (requires sudo)..."
    sudo bash -c "
        mkdir -p '$SHARE_DIR'
        cp -f -- kutimeout.py kutimeout.desktop config.json README.md '$SHARE_DIR/'
        cp -rf -- locale '$SHARE_DIR/'
        chmod +x '$SHARE_DIR/kutimeout.py'

        # Create symlink in /usr/bin
        mkdir -p '$(dirname "$BIN_FILE")'
        ln -sf '$SHARE_DIR/kutimeout.py' '$BIN_FILE'
    "
fi

echo "Successfully installed $NAME!"

echo "Configuration is located at: ~/.config/$NAME/config.json"
