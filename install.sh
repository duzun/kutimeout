#!/bin/bash

# Install timeout_kde

[ -d ~/.config/autostart/ ] || mkdir -p ~/.config/autostart/

cp -- timeout_kde.desktop ~/.config/autostart/ && \
chmod +x ~/.config/autostart/timeout_kde.desktop

if [ "$(pwd)" != "/opt/timeout_kde" ]; then
    sudo  bash -c '(
        [ -d /opt/timeout_kde ] || mkdir -p /opt/timeout_kde;
        cp -f -- ./* /opt/timeout_kde/ && \
        chmod +x /opt/timeout_kde/timeout_kde.py
    )'
fi