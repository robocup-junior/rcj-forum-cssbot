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

# Safety cap: max posts per feed per cycle (prevents mass reposts if something goes wrong)
MAX_POSTS_PER_CYCLE = 5

# -------------------------------------
# CONFIG: RSS → Discord channel map
# -------------------------------------
FEEDS = {
    "https://junior.forum.robocup.org/c/robocupjunior-rescue/robocupjunior-rescue-line/10.rss": 1456660154169692162,
    "https://junior.forum.robocup.org/c/robocupjunior-rescue/robocupjunior-rescue-maze/11.rss": 1456660460228051147,
    "https://junior.forum.robocup.org/c/robocupjunior-rescue/rescue-simulation/47.rss": 1456660650356117635,
    "https://junior.forum.robocup.org/c/robocupjunior-rescue/6.rss": 1466328513991933983,
    "https://junior.forum.robocup.org/c/robocupjunior-soccer/5.rss": 1446903879345373254,
    "https://junior.forum.robocup.org/c/robocupjunior-onstage/7.rss": 1446903820805345471,
    "https://junior.forum.robocup.org/c/general/1.rss": 1446904054705029301,
}

# Derived from FEEDS to avoid duplication — single source of truth for channel IDs
def _build_category_channels(feeds):
    result = {}
    for url, channel_id in feeds.items():
        if "rescue-line" in url:          result["rescue-line"] = channel_id
        elif "rescue-maze" in url:        result["rescue-maze"] = channel_id
        elif "rescue-simulation" in url:  result["rescue-sim"]  = channel_id
        elif "robocupjunior-rescue" in url: result["rescue"]    = channel_id
        elif "soccer" in url:             result["soccer"]      = channel_id
        elif "onstage" in url:            result["onstage"]     = channel_id
        else:                             result["general"]     = channel_id
    return result

CATEGORY_CHANNELS = _build_category_channels(FEEDS)

# Keywords to detect if a post title clearly belongs to a specific category
CATEGORY_KEYWORDS = {
    "rescue-line": [
        "rescue line", "line following", "line follower", "line maze", "line robot",
    ],
    "rescue-maze": [
        "rescue maze", "maze solving", "maze robot", "maze navigation",
    ],
    "rescue-sim": [
        "rescue simulation", "rescue sim", "erebus", "webots",
    ],
    "soccer": [
        "soccer", "football", "dribbler", "kicker", "ball detection",
        "open challenge soccer",
    ],
    "onstage": [
        "onstage", "on stage", "on-stage", "dance robot", "performance robot",
    ],
}

CATEGORY_EMOJIS = {
    "rescue-line": "🟢",
    "rescue-maze": "🔴",
    "rescue-sim": "🟣",
    "rescue": "🛟",
    "soccer": "⚽",
    "onstage": "🎭",
    "general": "🌍",
}

CATEGORY_COLORS = {
    "rescue-line": 0x2ECC71,   # green
    "rescue-maze": 0xE74C3C,   # red
    "rescue-sim": 0x9B59B6,    # purple
    "rescue": 0xF39C12,        # orange
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
        json.dump(state, f, indent=2)

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
def get_feed_category(feed_url):
    if "rescue-line" in feed_url:       return "rescue-line"
    if "rescue-maze" in feed_url:       return "rescue-maze"
    if "rescue-simulation" in feed_url: return "rescue-sim"
    if "robocupjunior-rescue" in feed_url: return "rescue"
    if "soccer" in feed_url:            return "soccer"
    if "onstage" in feed_url:           return "onstage"
    return "general"


def remap_category(title, current_category):
    """Return a different category key if the title unambiguously signals a mismatch, else current."""
    title_lower = title.lower()
    matches = [
        cat for cat, keywords in CATEGORY_KEYWORDS.items()
        if cat != current_category and any(kw in title_lower for kw in keywords)
    ]
    if len(matches) == 1:
        print(f"  Remapping '{title}' from '{current_category}' → '{matches[0]}'")
        return matches[0]
    if len(matches) > 1:
        print(f"  Ambiguous match for '{title}' ({matches}), keeping '{current_category}'")
    return current_category


def get_category_style(category):
    return CATEGORY_EMOJIS[category], CATEGORY_COLORS[category]


# -------------------------------------
# Helper: Post entry
# -------------------------------------
async def post_entry(channel, entry, category, prefix="New Post"):
    emoji, color = get_category_style(category)

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
            await post_entry(channel, entry, get_feed_category(feed_url), prefix="Forced Post")

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

        # Get set of seen IDs for this feed
        seen_ids = set(state.get(feed_url, []))

        # First run → mark all current entries as seen, post only the latest
        if not seen_ids:
            print("  First run: posting initial entry")
            channel = bot.get_channel(channel_id)
            if channel:
                await post_entry(channel, entries[0], get_feed_category(feed_url), prefix="Initial Post")
            state[feed_url] = sorted(e.id for e in entries)
            save_state(state)
            continue

        # Find new posts (entries we haven't seen before)
        new_posts = [e for e in entries if e.id not in seen_ids]

        # Safety cap to prevent mass reposts
        if len(new_posts) > MAX_POSTS_PER_CYCLE:
            print(f"  WARNING: {len(new_posts)} new posts, capping at {MAX_POSTS_PER_CYCLE}")
            new_posts = new_posts[:MAX_POSTS_PER_CYCLE]

        # Update seen IDs: keep IDs still in feed + mark posted ones as seen
        # (only mark posted items so backlog can catch up over subsequent cycles)
        current_feed_ids = {e.id for e in entries}
        posted_ids = {e.id for e in new_posts}
        state[feed_url] = sorted((seen_ids & current_feed_ids) | posted_ids)
        save_state(state)

        if not new_posts:
            continue

        # Post new items (oldest first), remapping to correct channel if needed
        current_category = get_feed_category(feed_url)
        for entry in reversed(new_posts):
            target_category = remap_category(entry.title, current_category)
            target_channel_id = CATEGORY_CHANNELS.get(target_category, channel_id)
            target_channel = bot.get_channel(target_channel_id)
            if target_channel is None:
                print(f"ERROR: Channel {target_channel_id} not found, falling back.")
                target_channel = bot.get_channel(channel_id)
            if target_channel is None:
                print(f"ERROR: Channel {channel_id} not found.")
                continue
            await post_entry(target_channel, entry, target_category)

# -------------------------------------
# Run bot
# -------------------------------------
bot.run(DISCORD_TOKEN)
