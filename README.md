# KUTimeout

A KDE Plasma session manager that limits daily computer usage and automatically logs out the user when the time limit is reached.

WARNING! No work is saved automatically when logging out. You can lose date. Use it at your own risk!

## Features

- Set daily time limits for computer usage
- Automatically logs out when the time limit is reached
- **Smart Warning**: Always gives at least a 5-minute warning before logout, even if the limit is reached unexpectedly.
- **Screen Lock Detection**: Pauses the usage timer when the screen is locked.
- **CLI Overrides**: Easily change the time limit from the command line.
- **Inactive by Default**: Exits silently if no time limit is set.
- Persists usage data between sessions and resets daily.
- Verbose logging for easy troubleshooting.

## Installation

### Manjaro / Arch Linux (AUR)

You can build and install the package using `makepkg` from this repository:

```bash
makepkg -si
```

### Manual Installation

1. Clone or download this repository.
2. Run the installation script:

```bash
./install.sh
```

This will:

- Install the script to `/usr/share/kutimeout/`
- Set up a system-wide symlink as `/usr/bin/kutimeout`
- Set up autostart for the current user in `~/.config/autostart/`

## Usage

The script starts automatically upon login. You can also run it manually or with custom settings:

```bash
# Run with default settings (or from config)
kutimeout

# Run with a custom 2-hour limit and verbose logging
kutimeout --time-limit 120 --verbose

# Change the time limit in the configuration and exit without running the service
kutimeout --time-limit 120 --save

# Use a specific configuration file
kutimeout --config ~/my_limits.json
```

## Configuration

The script stores its configuration in `~/.config/kutimeout/config.json`. **By default, `time_limit_minutes` is set to 0, which means the script will exit immediately without tracking time.**

Key configuration options:

- `time_limit_minutes`: The daily allowance in minutes. Set to a positive value (e.g., 120 for 2 hours) to enable the limit.
- `grace_period_minutes`: Minimum minutes to wait after startup before enforcing logout.
- `warning_minutes`: Minutes before logout to show a warning notification.
- `usage`: Tracks minutes used per day.
- `last_update`: Timestamp of the last usage update.

## Troubleshooting

- Check logs: `kutimeout --verbose`
- Ensure `qdbus` and `notify-send` are installed on your system.
- The script should NOT be run as root; it manages individual user sessions.

## License

This script is provided as-is, free to use and modify. No waranty of any kind is provided.
