# KDE Plasma Timeout Manager

A script that limits computer usage to a predefined amount of time per day and automatically logs out the user when the time limit is reached.

## Features

- Set daily time limits for computer usage
- Automatically logs out when time limit is reached
- Persists usage data between sessions
- Resets usage counter daily
- Easy to configure via command line arguments

## Installation

1. Make the script executable:

```bash
chmod +x /home/duzun/src/timeout_kde/timeout_kde.py
```

2. Set up autostart by copying the desktop file to the KDE autostart directory:

```bash
mkdir -p ~/.config/autostart
cp /home/duzun/src/timeout_kde/timeout_kde.desktop ~/.config/autostart/
```

3. Adjust the time limit in the desktop file if needed (default is 120 minutes):

```bash
# Edit the desktop file
nano ~/.config/autostart/timeout_kde.desktop

# Change the --time-limit parameter to your desired value (in minutes)
# Example: Exec=python3 /home/duzun/src/timeout_kde/timeout_kde.py --time-limit 180
```

## Usage

The script will start automatically when you log in to your KDE Plasma session. You can also run it manually:

```bash
# Run with default settings (60 minutes limit)
python3 /home/duzun/src/timeout_kde/timeout_kde.py

# Run with custom time limit (e.g., 90 minutes)
python3 /home/duzun/src/timeout_kde/timeout_kde.py --time-limit 90

# Use a custom configuration file
python3 /home/duzun/src/timeout_kde/timeout_kde.py --config /path/to/config.json
```

## Configuration

The script stores its configuration in `~/.config/timeout_kde/config.json`. This file is created automatically when the script runs for the first time.

The configuration includes:
- Time limit in minutes
- Usage data for each day
- Timestamp of the last update

## Troubleshooting

If the script doesn't log you out properly, make sure:
1. The script has execution permissions
2. The desktop file is correctly placed in the autostart directory
3. The paths in the desktop file are correct
4. The user has permissions to run `qdbus` commands

## License

This script is provided as-is, free to use and modify.
