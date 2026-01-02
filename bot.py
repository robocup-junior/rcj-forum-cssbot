import os
import sys
import json
import discord
import feedparser
from discord.ext import tasks, commands
from discord import app_commands
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
STATE_FILE = "rss_state.json"
RUN_ONCE = "--once" in sys.argv

# -------------------------------------
# CONFIG: RSS → Discord channel map
# -------------------------------------
FEEDS = {
    "https://junior.forum.robocup.org/c/robocupjunior-rescue/robocupjunior-rescue-line/10.rss": 1456660154169692162,
    "https://junior.forum.robocup.org/c/robocupjunior-rescue/robocupjunior-rescue-maze/11.rss": 1456660460228051147,
    "https://junior.forum.robocup.org/c/robocupjunior-rescue/rescue-simulation/47.rss": 1456660650356117635,
    "https://junior.forum.robocup.org/c/robocupjunior-soccer/5.rss": 1446903879345373254,
    "https://junior.forum.robocup.org/c/robocupjunior-onstage/7.rss": 1446903820805345471,
    "https://junior.forum.robocup.org/c/general/1.rss": 1446904054705029301,
}

CATEGORY_EMOJIS = {
    "rescue-line": "🟢",
    "rescue-maze": "🔴",
    "rescue-sim": "🟣",
    "soccer": "⚽",
    "onstage": "🎭",
    "general": "🌍",
}

CATEGORY_COLORS = {
    "rescue-line": 0x2ECC71,   # green
    "rescue-maze": 0xE74C3C,   # red
    "rescue-sim": 0x9B59B6,    # purple
    "soccer": 0x3498DB,        # blue
    "onstage": 0xE91E63,       # pink
    "general": 0x95A5A6,       # gray
}

# -------------------------------------
# Load/Save state
# -------------------------------------
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

state = load_state()

# -------------------------------------
# Clean and prettify HTML → Discord markdown
# -------------------------------------
def clean_html(html: str) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # 🔥 Replace Discourse emoji images with their ALT text (e.g., :loudspeaker:)
    for img in soup.find_all("img"):
        alt = img.get("alt", "").replace(":", "")  # remove colons
        emoji_map = {
            "loudspeaker": "📢",
            "globe_with_meridians": "🌐",
        }
        replacement = emoji_map.get(alt, alt)
        img.replace_with(replacement)

    # Convert <strong> → **text**
    for tag in soup.find_all("strong"):
        text = tag.get_text()
        tag.replace_with(f"**{text}**")

    # Convert links <a>text</a> → text (url)
    for a in soup.find_all("a"):
        link_text = a.get_text(strip=True)
        href = a.get("href", "")
        a.replace_with(f"{link_text} ({href})")

    # Remove Discourse footer junk like "3 posts - 1 participant"
    for small in soup.find_all("small"):
        small.decompose()

    # Convert to clean plaintext with newlines, strip blank lines
    text = soup.get_text("\n")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)

# -------------------------------------
# Discord Setup
# -------------------------------------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    if RUN_ONCE:
        await rss_checker()
        await bot.close()
    else:
        await tree.sync()
        print("Slash commands synced.")
        rss_checker.start()


# -------------------------------------
# Determine category appearance
# -------------------------------------
def get_category_style(feed_url):
    if "rescue-line" in feed_url:
        return CATEGORY_EMOJIS["rescue-line"], CATEGORY_COLORS["rescue-line"]
    if "rescue-maze" in feed_url:
        return CATEGORY_EMOJIS["rescue-maze"], CATEGORY_COLORS["rescue-maze"]
    if "rescue-simulation" in feed_url:
        return CATEGORY_EMOJIS["rescue-sim"], CATEGORY_COLORS["rescue-sim"]
    if "soccer" in feed_url:
        return CATEGORY_EMOJIS["soccer"], CATEGORY_COLORS["soccer"]
    if "onstage" in feed_url:
        return CATEGORY_EMOJIS["onstage"], CATEGORY_COLORS["onstage"]
    return CATEGORY_EMOJIS["general"], CATEGORY_COLORS["general"]


# -------------------------------------
# Helper: Post entry
# -------------------------------------
async def post_entry(channel, entry, feed_url, prefix="New Post"):
    emoji, color = get_category_style(feed_url)

    raw_html = entry.get("summary", "")
    clean_text = clean_html(raw_html)

    embed = discord.Embed(
        title=f"{emoji} {entry.title}",
        url=entry.link,
        description=clean_text[:4000],
        color=color,
    )
    embed.set_footer(text=prefix)
    await channel.send(embed=embed)


# -------------------------------------
# Slash Command: Force Post
# -------------------------------------
@tree.command(name="forcepost", description="Force the bot to send the latest forum posts for testing.")
async def forcepost(interaction: discord.Interaction):
    await interaction.response.send_message("Sending latest posts...", ephemeral=True)

    for feed_url, channel_id in FEEDS.items():
        feed = feedparser.parse(feed_url)
        entries = feed.entries[:2]  # send 2 most recent posts

        channel = bot.get_channel(channel_id)
        if channel is None:
            print(f"ERROR: Channel {channel_id} not found.")
            continue

        for entry in reversed(entries):
            await post_entry(channel, entry, feed_url, prefix="Forced Post")

    print("Forcepost complete.")


# -------------------------------------
# RSS Checker Loop
# -------------------------------------
@tasks.loop(minutes=2)
async def rss_checker():
    global state

    for feed_url, channel_id in FEEDS.items():
        print(f"Checking feed: {feed_url}")
        feed = feedparser.parse(feed_url)
        entries = feed.entries

        if not entries:
            continue

        latest_id = entries[0].id
        last_seen = state.get(feed_url)

        # First run → post most recent entry
        if last_seen is None:
            print("  First run: posting initial entry")
            channel = bot.get_channel(channel_id)
            if channel:
                await post_entry(channel, entries[0], feed_url, prefix="Initial Post")
            state[feed_url] = latest_id
            save_state(state)
            continue

        # Find new posts
        new_posts = []
        for entry in entries:
            if entry.id == last_seen:
                break
            new_posts.append(entry)

        if not new_posts:
            continue

        # Update last seen
        state[feed_url] = latest_id
        save_state(state)

        # Post new items
        channel = bot.get_channel(channel_id)
        if channel is None:
            print(f"ERROR: Channel {channel_id} not found.")
            continue

        for entry in reversed(new_posts):
            await post_entry(channel, entry, feed_url)

# -------------------------------------
# Run bot
# -------------------------------------
bot.run(DISCORD_TOKEN)
