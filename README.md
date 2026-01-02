# forum-bot

Discord Bot to share messages from the RoboCupJunior Forum at https://junior.forum.robocup.org/

## Usage

```bash
python bot.py          # Long-running bot with slash commands
python bot.py --once   # Run once and exit (for cron/GitHub Actions)
```

## Deployment

### Option 1: GitHub Actions (Recommended)

Runs as a scheduled job every 5 minutes with no server required.

1. Add `DISCORD_TOKEN` as a GitHub secret (Settings → Secrets → Actions)
2. Push to GitHub - the workflow runs automatically

The workflow commits `rss_state.json` to track seen posts between runs.

> **Note:** GitHub Actions cron can be delayed 10-15 minutes during high load.

### Option 2: Long-running Bot

Run as a persistent process with slash command support (`/forcepost`).

```bash
python bot.py
```

Requires `DISCORD_TOKEN` in `.env` file.

## Files

- `bot.py` - Main bot script (supports both modes)
- `rss_state.json` - Tracks last-seen posts per feed
