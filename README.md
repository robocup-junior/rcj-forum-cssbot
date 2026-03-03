# forum-bot

Discord bot that mirrors new posts from the [RoboCupJunior Forum](https://junior.forum.robocup.org/) into Discord channels.

## Features

- Monitors RSS feeds for all RoboCupJunior categories (Rescue Line, Rescue Maze, Rescue Simulation, Rescue, Soccer, OnStage, General)
- Posts new topics as Discord embeds with category-specific colour and emoji
- **Auto-remaps misposted topics** — if a post title clearly signals a different category (e.g. a rescue line topic posted under General), the bot routes it to the correct channel
- Deduplicates across feeds — a post moved by a moderator on the forum won't be posted twice
- Safety cap of 5 posts per feed per cycle to prevent mass reposts on state loss

## Usage

```bash
python bot.py          # Long-running bot with slash commands
python bot.py --once   # Run once and exit (for cron/GitHub Actions)
```

### Slash commands

| Command | Description |
|---|---|
| `/forcepost` | Force-send the 2 most recent posts from every feed (useful for testing) |

## Deployment

### Option 1: GitHub Actions (Recommended)

Runs as a scheduled job every 4 hours with no server required.

1. Fork this repository
2. Add `DISCORD_TOKEN` as a GitHub secret (Settings → Secrets → Actions)
3. Push to GitHub — the workflow runs automatically

The workflow commits `rss_state.json` after each run to track seen posts between runs.

> **Note:** GitHub Actions cron can be delayed 10–15 minutes during high load.

### Option 2: Long-running Bot

Run as a persistent process with slash command support.

1. Create a `.env` file with your token:
   ```
   DISCORD_TOKEN=your_token_here
   ```
2. Run:
   ```bash
   python bot.py
   ```

## Adding or tuning category keywords

Open `bot.py` and edit `CATEGORY_KEYWORDS`. Each entry is a list of lowercase substrings checked against the post title. A post is only remapped if **exactly one** non-current category matches — ambiguous titles are left in the original channel.

```python
CATEGORY_KEYWORDS = {
    "rescue-line": ["rescue line", "line following", ...],
    "rescue-maze": ["rescue maze", "maze solving", ...],
    ...
}
```

## Files

- `bot.py` — Main bot script (supports both run modes)
- `rss_state.json` — Tracks seen post IDs across all feeds (auto-updated by CI)

## License

[MIT](LICENSE)
