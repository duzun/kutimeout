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
kutimeout -l 120 -v

# Change the time limit in the configuration and exit
kutimeout -l 120 -s

# Enable background usage tracking without a time limit
kutimeout -t -s
```

### Command Line Options

| Short | Long | Description |
|-------|------|-------------|
| `-l` | `--time-limit` | Daily time limit in minutes. Use `0` to disable. |
| `-t` | `--track-usage` | Track usage even if no time limit is set. |
| `-s` | `--save` | Update the configuration file and exit immediately. |
| `-g` | `--grace-period` | Minimum minutes to wait after startup before logout. |
| `-w` | `--warning-minutes` | Minutes before logout to show a warning. |
| `-c` | `--config` | Path to a custom configuration file. |
| `-v` | `--verbose` | Enable detailed logging for troubleshooting. |
| | `--help` | Show the help message and exit. |

## Configuration

The script stores its configuration in `~/.config/kutimeout/config.json`. **By default, `time_limit_minutes` is set to 0, which means the script will exit immediately without tracking time.**

Key configuration options:

- `time_limit_minutes`: The daily allowance in minutes. Set to a positive value (e.g., 120 for 2 hours) to enable the limit.
- `track_usage`: If `true`, the service will track usage even if `time_limit_minutes` is 0.
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
