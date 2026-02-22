# forum-bot

Discord bot that mirrors new posts from the [RoboCupJunior Forum](https://junior.forum.robocup.org/) into Discord channels.

## Usage

```bash
python bot.py          # Long-running bot with slash commands
python bot.py --once   # Run once and exit (for cron/GitHub Actions)
```

## Deployment

### Option 1: GitHub Actions (Recommended)

Runs as a scheduled job every 4 hours with no server required.

1. Fork this repository
2. Add `DISCORD_TOKEN` as a GitHub secret (Settings → Secrets → Actions)
3. Push to GitHub — the workflow runs automatically

The workflow commits `rss_state.json` to track seen posts between runs.

> **Note:** GitHub Actions cron can be delayed 10–15 minutes during high load.

### Option 2: Long-running Bot

Run as a persistent process with slash command support (`/forcepost`).

1. Create a `.env` file with your token:
   ```
   DISCORD_TOKEN=your_token_here
   ```
2. Run:
   ```bash
   python bot.py
   ```

## Files

- `bot.py` - Main bot script (supports both modes)
- `rss_state.json` - Tracks last-seen posts per feed (auto-updated by CI)

## License

[MIT](LICENSE)
