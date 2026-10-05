"""
Gester - an animated rainbow GUI.

BEFORE RUNNING:
  1. Install pygame (for sound):   pip install pygame
  2. Put these files in the SAME folder as gester.py:
       hover.wav       - plays when the mouse touches a button (keep it short!)
       click.wav       - plays when you click a button
       jester.wav      - plays when you click a jester
       party_song.mp3  - the song that loops in Party Mode (.wav or .ogg also work)
  Missing files are fine, Gester just stays quiet for that sound.
  3. For the Discord bot:  pip install discord.py
     Then make a file called config.json next to gester.py containing:
       {"token": "YOUR_BOT_TOKEN", "channel_id": 123456789012345678}
     (To get a channel ID: Discord Settings > Advanced > turn on Developer Mode,
      then right-click the channel > Copy Channel ID. The bot needs permission
      to view and send messages in that channel.)
     NEVER share your token or config.json with anyone!

RUN:  python gester.py
"""
import tkinter as tk
import colorsys, math, random, os, sys, json, asyncio, threading, wave, hashlib
from collections import deque

# ---------- SETTINGS (change these to experiment!) ----------
WIDTH, HEIGHT = 720, 480
NORMAL_SPEED = 0.004      # how fast the rainbow cycles
PARTY_SPEED = 0.02        # rainbow speed in Party Mode
NUM_PARTICLES = 40
NUM_JESTERS = 6

# WHO CAN CHAT: each person's ID -> the name shown for them.
# Friends open the CHAT tab and click "ID" to copy theirs, then send it to you.
# You add a line below, upload gester.py, and they can chat. Remove a line to remove them.
ROSTER = {
    # "3fa9c2e1b7d4": "Flug",
    # "9c01d5e2a8b3": "Emii",
}

# Messages containing these words are blocked (whole words only). Add your own!
BLOCKED_WORDS = {"fuck", "fucking", "shit", "bitch", "asshole", "dick", "cunt"}

# AUTO-UPDATING SOUNDS: your GitHub repo as "yourname/gester" ("" = off).
# Put your sound files in a folder called "sounds" in that repo.
GITHUB_REPO = ""

# MULTIPLAYER: paste your Discord channel IDs here (0 = that feature is off)
SYNC_CHANNEL_ID = 1556072377530458174      # the channel that keeps everyone's name list in sync
CHAT_CHANNEL_ID = 1556072398111903784      # the channel the chat box uses
USE_MESSAGE_CONTENT_INTENT = False   # only set True if the chat shows blank messages
CHAT_W = 300             # how much wider the window gets when the chat is open
VERSION = "1.5.0"          # change this each update so you can see it worked

HOVER_SOUND = "hover.wav"
CLICK_SOUND = "click.wav"
JESTER_SOUND = "jester.wav"
PARTY_SONG = "party_song.mp3"
CHAT_SEND_SOUND = "chat_send.wav"          # plays when YOU send a chat message
CHAT_RECEIVE_SOUND = "chat_receive.wav"    # plays when SOMEONE ELSE sends one
# -------------------------------------------------------------

# The folder Gester lives in (works for both gester.py and the packaged .exe)
if getattr(sys, "frozen", False):
    HERE = os.path.dirname(sys.executable)
else:
    HERE = os.path.dirname(os.path.abspath(__file__))

# Files bundled inside the .exe get unpacked here
BUNDLE = getattr(sys, "_MEIPASS", HERE)


# Things Gester keeps on each computer (downloaded sounds, your secret chat ID)
DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Gester")
SYNC_DIR = os.path.join(DATA_DIR, "sounds")
DEFAULT_DIR = os.path.join(DATA_DIR, "defaults")   # built-in beeps, used if a sound is missing


def find_file(filename):
    """Look next to the program, then in the downloaded sounds, then inside the .exe."""
    for folder in (HERE, SYNC_DIR, BUNDLE, DEFAULT_DIR):
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            return path
    return None

def sync_sounds(updates):
    """Download new or changed files from the repo's sounds/ folder (runs in the background)."""
    if not GITHUB_REPO:
        return
    try:
        import urllib.request

        def fetch(url, accept):
            request = urllib.request.Request(url, headers={"User-Agent": "Gester", "Accept": accept})
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.read()

        listing = json.loads(fetch(f"https://api.github.com/repos/{GITHUB_REPO}/contents/sounds",
                                   "application/vnd.github+json"))
        os.makedirs(SYNC_DIR, exist_ok=True)
        index_path = os.path.join(SYNC_DIR, "index.json")   # remembers which version of each file we have
        try:
            with open(index_path) as f:
                index = json.load(f)
        except Exception:
            index = {}
        changed = 0
        for entry in listing:
            if entry.get("type") != "file":
                continue
            name = os.path.basename(entry["name"])
            path = os.path.join(SYNC_DIR, name)
            if index.get(name) == entry["sha"] and os.path.exists(path):
                continue    # already have this exact version
            data = fetch(entry["url"], "application/vnd.github.raw+json")
            if len(data) != entry["size"]:
                continue    # incomplete download: try again next time
            with open(path + ".tmp", "wb") as f:
                f.write(data)
            os.replace(path + ".tmp", path)
            index[name] = entry["sha"]
            with open(index_path, "w") as f:
                json.dump(index, f)
            changed += 1
        if changed:
            updates.append(("sounds", changed))
    except Exception:
        pass    # offline, rate-limited, or no sounds folder yet: just keep what we have


def make_default_sounds():
    """Make simple built-in chat beeps, but only for sounds you haven't provided."""
    defaults = {CHAT_SEND_SOUND: [(660, 60), (880, 90)],        # quick rising "whoosh"
                CHAT_RECEIVE_SOUND: [(988, 80), (784, 140)]}    # soft falling "ding-dong"
    for name, notes in defaults.items():
        if find_file(name) is not None:
            continue
        try:
            os.makedirs(DEFAULT_DIR, exist_ok=True)
            rate = 22050
            data = bytearray()
            for frequency, milliseconds in notes:
                count = int(rate * milliseconds / 1000)
                for i in range(count):
                    value = int(9000 * math.sin(2 * math.pi * frequency * i / rate) * (1 - i / count))
                    data += value.to_bytes(2, "little", signed=True)
            with wave.open(os.path.join(DEFAULT_DIR, name), "wb") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(rate)
                f.writeframes(bytes(data))
        except Exception:
            pass


# ---------- SOUND (uses pygame so music + effects can play together) ----------
try:
    import pygame
    pygame.mixer.init()
    SOUND_ON = True
except Exception:
    SOUND_ON = False
    print("Sound is off. To turn it on, run:  pip install pygame")


def load_sound(filename, volume=1.0):
    path = find_file(filename)
    if SOUND_ON and path:
        sound = pygame.mixer.Sound(path)
        sound.set_volume(volume)
        return sound
    return None


def play(sound):
    if sound:
        sound.play()


def start_song():
    """Start the party song on loop. Returns False if it couldn't play."""
    path = find_file(PARTY_SONG)
    if SOUND_ON and path:
        try:
            pygame.mixer.music.load(path)
            pygame.mixer.music.set_volume(0.7)
            pygame.mixer.music.play(-1)  # -1 means loop forever
            return True
        except Exception:
            pass
    return False


def stop_song():
    if SOUND_ON:
        pygame.mixer.music.stop()


# ---------- THEMES ----------
# Every color in Gester comes from here. "palette" is what the animated colors
# cycle through (None = the full rainbow). Add your own theme by copying one!
THEMES = {
    "RAINBOW": dict(
        palette=None, swatches=["#ff4d4d", "#ffb84d", "#4dff88", "#4d9dff", "#c04dff"],
        bg="#0d0d14", panel="#161622", panel_hi="#1e1e30", panel_dark="#10101a",
        border="#333344", grid="#2a2a3a", sel="#2b2b44", same="#222240",
        text="white", given="#e8e8ff", muted="#6a6a88", dim="#8888aa", faint="#444460"),
    "EMII": dict(    # minion: yellow, blue and black
        palette=["#ffd90f", "#3d8bff"], swatches=["#ffd90f", "#3d8bff"],
        bg="#090b12", panel="#0f1a36", panel_hi="#18285a", panel_dark="#0a1124",
        border="#2a4a9a", grid="#1b2d5c", sel="#27408a", same="#1a2d63",
        text="#fff6c2", given="#fffbe0", muted="#7a8fc7", dim="#9db0e0", faint="#3a4a7a"),
    "MILLANA": dict(    # orange and purple
        palette=["#ff8a1f", "#a259ff"], swatches=["#ff8a1f", "#a259ff"],
        bg="#0f0818", panel="#1c1030", panel_hi="#2a1848", panel_dark="#140a22",
        border="#5a2f99", grid="#2d1a4d", sel="#3d2468", same="#2a1a47",
        text="#fff1e0", given="#ffe3c4", muted="#9c7fc4", dim="#b79be0", faint="#4a3470"),
    "FLUG": dict(    # green and white
        palette=["#2ee66b", "#f4fff7"], swatches=["#2ee66b", "#f4fff7"],
        bg="#06110b", panel="#0d2016", panel_hi="#143321", panel_dark="#09170f",
        border="#1f6b3d", grid="#112a1b", sel="#1f4d30", same="#143a25",
        text="#ffffff", given="#e9fff0", muted="#6fa386", dim="#8fc7a6", faint="#2f5a42"),
}
COLOR_KEYS = ["bg", "panel", "panel_hi", "panel_dark", "border", "grid", "sel",
              "same", "text", "given", "muted", "dim", "faint"]
THEME_FILE = os.path.join(HERE, "theme.json")


def load_theme_name():
    try:
        with open(THEME_FILE) as f:
            name = json.load(f)["theme"]
        return name if name in THEMES else "RAINBOW"
    except Exception:
        return "RAINBOW"


def save_theme(name):
    try:
        with open(THEME_FILE, "w") as f:
            json.dump({"theme": name}, f)
    except OSError:
        pass


THEME = dict(THEMES[load_theme_name()])   # the theme in use right now


def hex_to_rgb(color):
    return [int(color[i:i + 2], 16) for i in (1, 3, 5)]


def rainbow(hue, saturation=0.8, brightness=1.0):
    """Turn a number into a color that cycles through the current theme."""
    palette = THEME["palette"]
    if palette is None:
        r, g, b = colorsys.hsv_to_rgb(hue % 1.0, saturation, brightness)
        return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
    position = (hue % 1.0) * len(palette)
    i = int(position)
    mix = min(1.0, max(0.0, (position - i - 0.25) * 2))   # hold each color, then blend quickly
    first = hex_to_rgb(palette[i % len(palette)])
    second = hex_to_rgb(palette[(i + 1) % len(palette)])
    r, g, b = [min(255, int((first[k] + (second[k] - first[k]) * mix) * brightness)) for k in range(3)]
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------- SAVING NAMES ----------
NAMES_FILE = os.path.join(HERE, "names.json")


def load_names():
    """Read the saved names (or start with an empty list the first time)."""
    try:
        with open(NAMES_FILE) as f:
            return [str(n) for n in json.load(f)]
    except Exception:
        return []


def save_names(names):
    try:
        with open(NAMES_FILE, "w") as f:
            json.dump(names, f)
    except OSError:
        print("Could not save names.json")


# ---------- CHAT SECURITY: names that can't be faked ----------
# Every install makes a secret key (kept in your Gester data folder, never shared).
# Messages are signed with it, and everyone checks the signature against ROSTER, so
# nobody can type as someone else. (Schnorr signatures; the numbers below are a
# standard kind of public "group" that everyone uses.)
GROUP_P = int(
    "8957b00e8f30b5ff68e4e5fb4881cf73dbc5c4fc21a1f22c6509f833813331cf"
    "8f16254c87a24e6b6aff54a6998a1861e4908da63b9e7fcc1b859f5d9be83649"
    "c25b36b5e3ccf4156962180aed318a4be56efe639f2447b3b7d5eea95ad7a1bf"
    "a5b9ce1d474addd7091b1fd914ffdd2e0c722d93061a6fcdab1ccc73a02a271e"
    "d18851707d46c1f62464368b569710707ed8193b55f75a8c735411cb60168651"
    "641484c6f6f12402548935eef64c16272484d8943bfff828aac57f6cd55006a7"
    "6644ec5477665472012d5ef74eba1039ba99dd9b0c1f99f05124a27fb6ada137"
    "6756043f54e4a8075d6b801c9a44bac03f006b8bf43184773f1290ef2ae1cbb3", 16)
GROUP_Q = int(
    "ae5993c877ddc667c6a93d117c5413aec1299bceaf979a541d33798a6f278c67", 16)
GROUP_G = int(
    "1de7067a94655927a3961abfd1bfd2a497c4a0374e29d5de0abedb81d873f2d9"
    "208c25aed3f3dc2c90b7d97e23b3768f14e0d0b2ec04af49f38d7f7d785340f6"
    "547884352a9236eb7cd0e5015d04f5e59af9fbad61e8d547d0a0181b19a1e2b6"
    "6fa12b217eee5e3a735c9f1c1d7bdb3ef0e62047b3f9361998378b2e73304284"
    "b6a9b6cb99aa9a2fa4ccb5f40bf5c7f104f52c7507ad74ae2dd724a7001c6b1e"
    "9207b09f5d860cb40439ab807d6c603a9fa16c3f7a020d3e3d422ae6214748ed"
    "63211d1b59d5ad78aa8efa1b48d56f0c719ad3e3007f4d2682385162dd1f6135"
    "b685051ffa9d51cf99327e71c589b0a13ee4e0abd203824d577c53feaddfb1fe", 16)
_RANDOM = random.SystemRandom()
IDENTITY_FILE = os.path.join(DATA_DIR, "identity.json")


def _challenge(r, message):
    text = f"{r}|{message}".encode()
    return int(hashlib.sha256(text).hexdigest(), 16) % GROUP_Q


def load_identity():
    """This install's (secret key, public key). Made the first time Gester runs."""
    try:
        with open(IDENTITY_FILE) as f:
            secret = int(json.load(f)["x"], 16)
        if not 0 < secret < GROUP_Q:
            raise ValueError
    except Exception:
        secret = _RANDOM.randrange(1, GROUP_Q)
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(IDENTITY_FILE, "w") as f:
                json.dump({"x": f"{secret:x}"}, f)
        except OSError:
            pass
    return secret, pow(GROUP_G, secret, GROUP_P)


def fingerprint(public):
    """The short ID people send you to get on the ROSTER."""
    return hashlib.sha256(f"{public:x}".encode()).hexdigest()[:12]


def sign(secret, message):
    k = _RANDOM.randrange(1, GROUP_Q)
    e = _challenge(pow(GROUP_G, k, GROUP_P), message)
    return e, (k + secret * e) % GROUP_Q


def verify(public, message, e, s):
    if not (1 < public < GROUP_P and pow(public, GROUP_Q, GROUP_P) == 1):
        return False
    if not (0 < e < GROUP_Q and 0 <= s < GROUP_Q):
        return False
    r = pow(GROUP_G, s, GROUP_P) * pow(public, GROUP_Q - e, GROUP_P) % GROUP_P
    return e == _challenge(r, message)


def read_chat(content):
    """Check a chat message from Discord. Returns (id, name, text, message_id) or None."""
    try:
        body, _, tail = content.rpartition(" ||")
        if not (tail.endswith("||") and body.startswith("**") and "**: " in body[2:]):
            return None
        text = body[2:].split("**: ", 1)[1]
        public_hex, e_hex, s_hex, message_id = tail[:-2].split(":")
        public = int(public_hex, 16)
        who = fingerprint(public)
        if who not in ROSTER:
            return None      # not on the approved list
        if not verify(public, f"{message_id}|{text}", int(e_hex, 16), int(s_hex, 16)):
            return None      # fake or changed message
        return who, ROSTER[who], text, message_id
    except Exception:
        return None


_LOOKALIKES = str.maketrans("@013$5", "aoiess")


def has_blocked(text):
    """True if the text contains a blocked word (also catches things like sh1t)."""
    cleaned = "".join(ch if ch.isalpha() else " " for ch in text.lower().translate(_LOOKALIKES))
    return any(word in BLOCKED_WORDS for word in cleaned.split())


# ---------- SHARED NAME LIST + USERNAME ----------
USER_FILE = os.path.join(HERE, "username.txt")
SEEDED_FILE = os.path.join(HERE, "synced.flag")


def load_username():
    try:
        with open(USER_FILE) as f:
            return f.read().strip()[:20] or "Guest"
    except OSError:
        return "Guest"


def save_username(name):
    try:
        with open(USER_FILE, "w") as f:
            f.write(name)
    except OSError:
        pass


def apply_event(names, kind, name=""):
    """Change a name list the way a shared ADD / REMOVE / CLEAR event says."""
    lowered = [n.lower() for n in names]
    if kind == "ADD" and name and not has_blocked(name) and name.lower() not in lowered:
        names.append(name)
    elif kind == "REMOVE" and name.lower() in lowered:
        names.pop(lowered.index(name.lower()))
    elif kind == "CLEAR":
        names.clear()


def parse_sync(content):
    """'GESTER-SYNC abc123 ADD bob' -> ('abc123', 'ADD', 'bob'), or None."""
    parts = content.split(" ", 3)
    if len(parts) >= 3 and parts[0] == "GESTER-SYNC":
        return parts[1], parts[2], (parts[3] if len(parts) == 4 else "")
    return None


# ---------- SUDOKU ENGINE ----------
SU_CELL, SU_X, SU_Y = 38, 40, 68       # cell size and where the grid starts
PROGRESS_FILE = os.path.join(HERE, "sudoku.json")


def load_progress():
    """How many levels this person has beaten (0 to 100)."""
    try:
        with open(PROGRESS_FILE) as f:
            return max(0, min(100, int(json.load(f)["completed"])))
    except Exception:
        return 0


def save_progress(completed):
    try:
        with open(PROGRESS_FILE, "w") as f:
            json.dump({"completed": completed}, f)
    except OSError:
        pass


def solve(grid, limit, rng=None):
    """Count solutions (up to limit). Returns (count, first_solution)."""
    cells = grid[:]
    rows, cols, boxes = [0] * 9, [0] * 9, [0] * 9
    for i, v in enumerate(cells):
        if v:
            bit = 1 << v
            rows[i // 9] |= bit
            cols[i % 9] |= bit
            boxes[i // 27 * 3 + i % 9 // 3] |= bit
    found = {"count": 0, "first": None}

    def search():
        best, best_mask, best_n = -1, 0, 10
        for i in range(81):
            if cells[i] == 0:
                used = rows[i // 9] | cols[i % 9] | boxes[i // 27 * 3 + i % 9 // 3]
                mask = ~used & 0x3FE
                n = bin(mask).count("1")
                if n < best_n:
                    best, best_mask, best_n = i, mask, n
                    if n <= 1:
                        break
        if best == -1:
            found["count"] += 1
            if found["first"] is None:
                found["first"] = cells[:]
            return
        if best_n == 0:
            return
        r, c, b = best // 9, best % 9, best // 27 * 3 + best % 9 // 3
        values = [v for v in range(1, 10) if best_mask >> v & 1]
        if rng:
            rng.shuffle(values)
        for v in values:
            bit = 1 << v
            cells[best] = v
            rows[r] |= bit
            cols[c] |= bit
            boxes[b] |= bit
            search()
            cells[best] = 0
            rows[r] &= ~bit
            cols[c] &= ~bit
            boxes[b] &= ~bit
            if found["count"] >= limit:
                return

    search()
    return found["count"], found["first"]


def make_puzzle(level):
    """Make Sudoku level 1-100. The same level is the same puzzle for everyone."""
    rng = random.Random(level * 7919)
    solution = solve([0] * 81, 1, rng)[1]
    puzzle = solution[:]
    target = round(46 - 24 * (level - 1) / 99)   # fewer clues = harder
    order = list(range(81))
    rng.shuffle(order)
    clues = 81
    for i in order:
        if clues <= target:
            break
        saved, puzzle[i] = puzzle[i], 0
        if solve(puzzle, 2)[0] == 1:
            clues -= 1
        else:
            puzzle[i] = saved
    return puzzle, solution


# ---------- THE DISCORD BOT ----------
try:
    import discord
except ImportError as error:
    discord = None
    print(f"Could not load discord: {error}")
    print(f"Gester is running with this Python: {sys.executable}")


class DiscordLink:
    """Runs the bot in the background so the window never freezes."""

    def __init__(self):
        self.ready = False
        self.problem = None      # a message explaining what's wrong, if anything
        self.inbox = deque()     # things that arrived from Discord, waiting for the window
        self.client_id = "%06x" % random.randrange(16 ** 6)   # lets us ignore our own echoes
        self.loaded = False
        if discord is None:
            self.problem = "discord.py not found by this Python (see terminal)"
            return
        config_path = find_file("config.json")
        if config_path is None:
            if os.path.exists(os.path.join(HERE, "config.json.txt")):
                self.problem = "rename config.json.txt to config.json"
            else:
                self.problem = "no config.json in ..." + HERE[-40:]
            return
        try:
            with open(config_path) as f:
                config = json.load(f)
        except Exception:
            self.problem = "config.json has a typo (check quotes and commas)"
            return
        try:
            self.token = config["token"]
            self.channel_id = int(config["channel_id"])
        except Exception:
            self.problem = "config.json needs a token and a channel_id"
            return
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        intents = discord.Intents.default()
        intents.message_content = USE_MESSAGE_CONTENT_INTENT
        self.client = discord.Client(intents=intents)

        @self.client.event
        async def on_ready():
            self.ready = True
            if not self.loaded:
                self.loaded = True
                await self.load_history()

        @self.client.event
        async def on_message(message):
            if message.channel.id == SYNC_CHANNEL_ID:
                self.inbox.append(("sync", message.content))
            elif message.channel.id == CHAT_CHANNEL_ID:
                self.inbox.append(("chat", message.content))

        try:
            self.loop.run_until_complete(self.client.start(self.token))
        except Exception as error:
            self.ready = False
            self.problem = f"bot error: {error}"

    async def find_channel(self, channel_id):
        return self.client.get_channel(channel_id) or await self.client.fetch_channel(channel_id)

    async def load_history(self):
        """Read what happened before we started (shared names + recent chat)."""
        try:
            if SYNC_CHANNEL_ID:
                channel = await self.find_channel(SYNC_CHANNEL_ID)
                found = [m.content async for m in channel.history(limit=500)]
                self.inbox.append(("sync_history", found[::-1]))   # oldest first
            if CHAT_CHANNEL_ID:
                channel = await self.find_channel(CHAT_CHANNEL_ID)
                found = [m.content async for m in channel.history(limit=40)]
                self.inbox.append(("chat_history", found[::-1]))
        except Exception as error:
            self.inbox.append(("error", f"Discord history error: {error}"))

    def send(self, text, channel_id=None):
        """Send a message. Returns a 'future' we can check later."""
        channel_id = channel_id or self.channel_id

        async def go():
            channel = await self.find_channel(channel_id)
            # no_mentions: a name like @everyone must never ping anyone
            await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
        return asyncio.run_coroutine_threadsafe(go(), self.loop)

    def post(self, text, channel_id):
        """Send without waiting. Returns False if it couldn't even be tried."""
        if self.problem or not self.ready or not channel_id:
            return False
        self.send(text, channel_id).add_done_callback(self.report_failure)
        return True

    def report_failure(self, future):
        if future.cancelled():
            return
        error = future.exception()
        if error:
            self.inbox.append(("error", f"Discord error: {error}"))

    def post_sync(self, kind, name=""):
        return self.post(f"GESTER-SYNC {self.client_id} {kind} {name}".strip(), SYNC_CHANNEL_ID)


# ---------- A LITTLE JESTER ----------
class Jester:
    def __init__(self, canvas, x, y, on_click):
        self.canvas = canvas
        self.x, self.y = x, y
        self.dx = random.choice([-1, 1]) * random.uniform(0.6, 1.5)
        self.dy = random.choice([-1, 1]) * random.uniform(0.4, 1.0)
        self.offset = random.random()          # gives each jester its own color
        self.phase = random.random() * 6       # makes them wiggle at different times
        self.boost = 0                         # extra speed after being clicked

        def at(points):  # shift shape coordinates to where the jester is
            return [v + (x if i % 2 == 0 else y) for i, v in enumerate(points)]

        c = canvas
        self.body = c.create_polygon(at([-8, 10, 8, 10, 13, 34, -13, 34]), outline="")
        self.head = c.create_oval(at([-10, -10, 10, 10]), fill="#e8d2b4", outline="")
        self.hat = c.create_polygon(at([-12, -6, -19, -24, -8, -13, 0, -27, 8, -13, 19, -24, 12, -6]), outline="")
        bells = [c.create_oval(at([bx - 3, by - 3, bx + 3, by + 3]), fill="#f2c94c", outline="")
                 for bx, by in [(-19, -24), (0, -27), (19, -24)]]
        eyes = [c.create_oval(at([ex - 1.5, -3, ex + 1.5, 0]), fill="#222222", outline="")
                for ex in (-4, 4)]
        self.parts = [self.body, self.head, self.hat] + bells + eyes

        # make every part of the jester clickable
        for part in self.parts:
            c.tag_bind(part, "<Button-1>", lambda e: on_click(e, self))
            c.tag_bind(part, "<Enter>", lambda e: c.config(cursor="hand2"))
            c.tag_bind(part, "<Leave>", lambda e: c.config(cursor=""))

    def poke(self):
        """Called when clicked: turn around and zoom off."""
        self.dx *= -1
        self.dy *= -1
        self.boost = 20

    def update(self, hue, speed_multiplier, frame):
        speed_multiplier *= 1 + self.boost / 5
        self.boost = max(0, self.boost - 1)

        dx = self.dx * speed_multiplier
        dy = self.dy * speed_multiplier + math.sin(frame * 0.15 + self.phase) * 0.8
        self.x += dx
        self.y += dy

        # bounce off the edges
        if (self.x < 25 and self.dx < 0) or (self.x > WIDTH - 25 and self.dx > 0):
            self.dx *= -1
        if (self.y < 40 and self.dy < 0) or (self.y > HEIGHT - 45 and self.dy > 0):
            self.dy *= -1

        for part in self.parts:
            self.canvas.move(part, dx, dy)

        # softer colors so they stay in the background
        self.canvas.itemconfig(self.hat, fill=rainbow(hue + self.offset, 0.7, 0.6))
        self.canvas.itemconfig(self.body, fill=rainbow(hue + self.offset + 0.5, 0.7, 0.5))


# ---------- THE APP ----------
class Gester:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Gester")
        icon = find_file("gester.ico")   # optional window icon
        if icon:
            try:
                self.root.iconbitmap(icon)
            except Exception:
                pass
        self.root.geometry(f"{WIDTH}x{HEIGHT}")
        self.root.resizable(False, False)

        self.canvas = tk.Canvas(self.root, width=WIDTH, height=HEIGHT,
                                bg=THEME["bg"], highlightthickness=0)
        self.canvas.pack()

        self.hue = 0.0
        self.speed = NORMAL_SPEED
        self.party = False
        self.page = "home"
        self.hovered = None
        self.leave_job = None   # used to avoid repeating the hover sound
        self.ripples = []   # expanding rings made by clicks
        self.frame = 0
        self.names = load_names()   # the Name Chooser list (saved between runs)
        self.secret, self.public = load_identity()
        self.my_fp = fingerprint(self.public)
        self.username = ROSTER.get(self.my_fp, "Guest")
        self.seen_ids = set()    # chat message IDs we've shown (stops copy-pasted repeats)
        self.chat_open = False
        self.unread = 0
        self.clear_armed = False
        self.spinning = False
        self.bot = DiscordLink()
        self.updates = deque()           # news from the background sound updater
        self.su_done = load_progress()   # sudoku levels beaten
        self.su_level = 1
        self.su_started = False
        self.su_won = False
        self.su_selected = None
        self.su_mistakes = 0
        self.su_hints = 3
        self.su_puzzle = [0] * 81
        self.su_grid = [0] * 81
        self.su_solution = [0] * 81

        self.hover_sound = load_sound(HOVER_SOUND, 0.5)
        self.click_sound = load_sound(CLICK_SOUND)
        self.jester_sound = load_sound(JESTER_SOUND)
        make_default_sounds()
        self.chat_send_sound = load_sound(CHAT_SEND_SOUND, 0.8)
        self.chat_receive_sound = load_sound(CHAT_RECEIVE_SOUND, 0.8)

        # Things created first are drawn at the back, so order matters here.
        self.buttons = {}
        self.make_particles()
        self.make_jesters()
        self.make_bar()
        self.make_home_page()
        self.make_menu_page()
        self.make_names_page()
        self.refresh_names()
        self.make_sudoku_page()
        self.make_themes_page()
        self.make_chat_panel()

        self.status = self.canvas.create_text(
            WIDTH / 2, 455, text="Welcome to Gester!",
            fill="#8888aa", font=("Helvetica", 12))

        self.canvas.create_text(WIDTH - 10, HEIGHT - 8, anchor="se", text=f"v{VERSION}",
                                fill="#444460", font=("Helvetica", 9))

        threading.Thread(target=sync_sounds, args=(self.updates,), daemon=True).start()
        self.theme_name = load_theme_name()
        self.apply_theme(THEMES["RAINBOW"], THEME)   # items are built in rainbow colors first
        self.update_theme_labels()

        self.show_page("home")
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)
        self.root.bind("<Key>", self.on_key)
        self.tick()  # start the animation loop

    # --- background pieces ---
    def make_particles(self):
        self.particles = []
        for _ in range(NUM_PARTICLES):
            x, y = random.randint(0, WIDTH), random.randint(0, HEIGHT)
            size = random.randint(2, 5)
            dot = self.canvas.create_oval(x, y, x + size, y + size, outline="")
            self.particles.append({"id": dot, "x": x, "y": y, "size": size,
                                   "speed": random.uniform(0.3, 1.5)})

    def make_jesters(self):
        self.jesters = [Jester(self.canvas, random.randint(40, WIDTH - 40),
                               random.randint(60, HEIGHT - 60), self.on_jester_click)
                        for _ in range(NUM_JESTERS)]

    def make_bar(self):
        self.bar = [self.canvas.create_rectangle(i * 12, 0, i * 12 + 12, 10, outline="")
                    for i in range(WIDTH // 12 + 1)]

    # --- the HOME page ---
    def make_home_page(self):
        self.letters = []
        for i, letter in enumerate("GESTER"):
            x = WIDTH / 2 + (i - 2.5) * 72
            item = self.canvas.create_text(x, 110, text=letter, tags="home",
                                           font=("Helvetica", 64, "bold"))
            self.letters.append(item)
        self.canvas.create_text(WIDTH / 2, 175, text="move your mouse. click things.",
                                fill="#6a6a88", font=("Helvetica", 12), tags="home")

        labels = [("PLAY", self.on_play), ("PARTY MODE", self.on_party), ("QUIT", self.quit_app)]
        for i, (label, action) in enumerate(labels):
            y1 = 220 + i * 70
            self.make_button(label, label, 210, y1, 510, y1 + 52, "home", action)

    # --- the TOOL MENU (opens when you click PLAY) ---
    def make_menu_page(self):
        self.options_title = self.canvas.create_text(
            WIDTH / 2, 60, text="CHOOSE A TOOL", tags="menu", font=("Helvetica", 40, "bold"))
        tools = [("NAME CHOOSER", lambda: self.show_page("names")),
                 ("MILLOKU", self.open_sudoku),
                 ("THEMES", lambda: self.show_page("themes"))]
        for i, (label, action) in enumerate(tools):
            y1 = 130 + i * 70
            self.make_button(label, label, 210, y1, 510, y1 + 52, "menu", action)
        self.make_button("BACK", "BACK", 260, 355, 460, 400, "menu", self.on_back, size=14)

    # --- the NAME CHOOSER page ---
    def make_names_page(self):
        c = self.canvas
        self.names_title = c.create_text(WIDTH / 2, 45, text="NAME CHOOSER", tags="names",
                                         font=("Helvetica", 34, "bold"))
        self.entry = tk.Entry(self.root, font=("Helvetica", 13), bg="#161622", fg="white",
                              insertbackground="white", relief="flat")
        self.entry.bind("<Return>", lambda e: self.add_name())
        c.create_window(60, 95, anchor="nw", window=self.entry, width=190, height=34, tags="names")
        self.make_button("ADD", "ADD", 260, 95, 330, 129, "names", self.add_name, size=12)
        c.create_text(60, 142, anchor="nw", text="click a name to remove it", fill="#6a6a88",
                      font=("Helvetica", 10), tags="names")
        self.result_text = c.create_text(525, 190, text="?", fill="white", width=300, justify="center",
                                         font=("Helvetica", 34, "bold"), tags="names")
        self.make_button("SPIN", "SPIN!", 395, 270, 655, 340, "names", self.spin, size=26)
        self.make_button("NAMES_BACK", "BACK", 60, 400, 190, 440, "names",
                         lambda: self.show_page("menu"), size=12)
        self.make_button("CLEAR", "CLEAR ALL", 200, 400, 330, 440, "names", self.clear_names, size=12)

    def refresh_names(self):
        c = self.canvas
        c.delete("chip")
        state = "normal" if self.page == "names" else "hidden"
        for i, name in enumerate(self.names[:9]):
            item = c.create_text(70, 168 + i * 25, anchor="w", text=f"\u2022  {name[:22]}",
                                 fill=THEME["text"], font=("Helvetica", 13), tags=("names", "chip"),
                                 state=state)
            c.tag_bind(item, "<Button-1>", lambda e, n=i: self.remove_name(n))
            c.tag_bind(item, "<Enter>", lambda e: c.config(cursor="hand2"))
            c.tag_bind(item, "<Leave>", lambda e: c.config(cursor=""))
        if len(self.names) > 9:
            c.create_text(70, 168 + 9 * 25, anchor="w", text=f"...and {len(self.names) - 9} more",
                          fill=THEME["muted"], font=("Helvetica", 11), tags=("names", "chip"),
                          state=state)

    def add_name(self):
        name = " ".join(self.entry.get().split())[:30]
        if not name:
            return
        if has_blocked(name):
            self.canvas.itemconfig(self.status, text="That name isn't allowed")
            return
        if name.lower() in [n.lower() for n in self.names]:
            self.canvas.itemconfig(self.status, text=f"{name} is already in the list")
            return
        self.names.append(name)
        save_names(self.names)
        self.entry.delete(0, "end")
        self.refresh_names()
        text = f"Added {name}"
        if not self.bot.post_sync("ADD", name) and SYNC_CHANNEL_ID:
            text += " (not shared: bot isn't connected)"
        self.canvas.itemconfig(self.status, text=text)

    def remove_name(self, index):
        if not self.spinning and index < len(self.names):
            removed = self.names.pop(index)
            save_names(self.names)
            self.bot.post_sync("REMOVE", removed)
            self.canvas.config(cursor="")
            self.refresh_names()
            self.canvas.itemconfig(self.status, text=f"Removed {removed}")

    def clear_names(self):
        if self.spinning:
            return
        if not self.clear_armed:   # ask twice, because this clears the list for EVERYONE
            self.clear_armed = True
            self.canvas.itemconfig(self.status, text="Click CLEAR ALL again to clear the list for EVERYONE")
            self.root.after(3000, self.disarm_clear)
            return
        self.clear_armed = False
        self.names.clear()
        save_names(self.names)
        self.refresh_names()
        self.canvas.itemconfig(self.result_text, text="?")
        self.bot.post_sync("CLEAR")

    def disarm_clear(self):
        self.clear_armed = False

    # --- multiplayer: things from Discord arrive here (checked every tick) ---
    def check_inbox(self):
        while self.updates:      # the sound updater finished downloading something
            kind, count = self.updates.popleft()
            if kind == "sounds":
                self.hover_sound = load_sound(HOVER_SOUND, 0.5)
                self.click_sound = load_sound(CLICK_SOUND)
                self.jester_sound = load_sound(JESTER_SOUND)
                self.chat_send_sound = load_sound(CHAT_SEND_SOUND, 0.8)
                self.chat_receive_sound = load_sound(CHAT_RECEIVE_SOUND, 0.8)
                self.canvas.itemconfig(self.status, text=f"Updated {count} sound file(s)!")
        before = list(self.names)
        while self.bot.inbox:
            kind, data = self.bot.inbox.popleft()
            if kind == "sync_history":
                self.merge_history(data)
            elif kind == "sync":
                event = parse_sync(data)
                if event and event[0] != self.bot.client_id:   # skip our own echoes
                    apply_event(self.names, event[1], event[2])
            elif kind == "chat_history":
                for content in data:
                    self.show_chat(content, quiet=True)
            elif kind == "chat":
                self.show_chat(data)
            elif kind == "error":
                self.canvas.itemconfig(self.status, text=data[:90])
        if self.names != before:
            save_names(self.names)
            self.refresh_names()

    def merge_history(self, events):
        """Rebuild the shared list from the sync channel's history."""
        shared = []
        for content in events:
            event = parse_sync(content)
            if event:
                apply_event(shared, event[1], event[2])
        if not os.path.exists(SEEDED_FILE):
            # First time online: share the names this person already had saved
            sent_all = True
            for name in self.names:
                if name.lower() not in [n.lower() for n in shared]:
                    shared.append(name)
                    sent_all = self.bot.post_sync("ADD", name) and sent_all
            if sent_all:
                try:
                    open(SEEDED_FILE, "w").close()
                except OSError:
                    pass
        self.names = shared

    # --- the CHAT panel (the window grows to the right when it's open) ---
    def make_entry(self):
        return tk.Entry(self.root, font=("Helvetica", 12), bg="#161622", fg="white",
                        insertbackground="white", relief="flat")

    def make_chat_panel(self):
        c = self.canvas
        x0, x1 = WIDTH + 10, WIDTH + CHAT_W - 10
        c.create_rectangle(x0, 45, x1, 450, fill="#10101a", outline="#333344", width=2, tags="chat")
        c.create_text(x0 + 15, 65, anchor="w", text="CHAT", fill="white", tags="chat",
                      font=("Helvetica", 16, "bold"))
        self.make_button("CHATMIN", "-", x1 - 45, 52, x1 - 10, 78, "chat", self.toggle_chat, size=14)
        c.create_text(x0 + 15, 100, anchor="w", text="your name", fill="#6a6a88",
                      font=("Helvetica", 10), tags="chat")
        self.name_entry = self.make_entry()
        self.name_entry.insert(0, self.username if self.my_fp in ROSTER else "(not approved)")
        self.name_entry.config(state="readonly", readonlybackground="#161622")   # names come from ROSTER
        c.create_window(x0 + 80, 88, anchor="nw", window=self.name_entry, width=125, height=24, tags="chat")
        self.make_button("COPYID", "ID", x1 - 55, 88, x1 - 10, 112, "chat", self.copy_id, size=10)
        self.chat_log = tk.Text(self.root, bg="#10101a", fg="white", font=("Helvetica", 11),
                                wrap="word", relief="flat", highlightthickness=0, padx=6, pady=4,
                                state="disabled", cursor="arrow")
        c.create_window(x0 + 8, 122, anchor="nw", window=self.chat_log, width=264, height=250, tags="chat")
        self.chat_entry = self.make_entry()
        self.chat_entry.bind("<Return>", lambda e: self.send_chat())
        c.create_window(x0 + 8, 384, anchor="nw", window=self.chat_entry, width=200, height=30, tags="chat")
        self.make_button("SEND", "SEND", x1 - 62, 384, x1 - 8, 414, "chat", self.send_chat, size=10)
        c.create_text((x0 + x1) / 2, 435, text="suggestions welcome!", fill="#6a6a88",
                      font=("Helvetica", 10), tags="chat")
        # the little tab on the side that opens and closes the chat
        self.make_button("CHATICON", "CHAT", WIDTH - 80, 215, WIDTH - 8, 251, "chaticon",
                         self.toggle_chat, size=10)
        c.itemconfig("chat", state="hidden")

    def toggle_chat(self):
        self.chat_open = not self.chat_open
        width = WIDTH + CHAT_W if self.chat_open else WIDTH
        self.canvas.config(width=width)
        self.root.geometry(f"{width}x{HEIGHT}")
        self.canvas.itemconfig("chat", state="normal" if self.chat_open else "hidden")
        if self.chat_open:
            self.unread = 0
            self.update_chat_icon()
            self.chat_entry.focus_set()
        else:
            self.canvas.focus_set()
        self.clear_hover()

    def update_chat_icon(self):
        label = f"CHAT ({self.unread})" if self.unread else "CHAT"
        self.canvas.itemconfig(self.buttons["CHATICON"]["text"], text=label)

    def copy_id(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.my_fp)
        except tk.TclError:
            pass
        if self.my_fp in ROSTER:
            text = f"You are {ROSTER[self.my_fp]}. Your ID ({self.my_fp}) is copied."
        else:
            text = f"Your ID {self.my_fp} is copied. Send it to the owner to get approved!"
        self.canvas.itemconfig(self.status, text=text)

    def send_chat(self):
        text = " ".join(self.chat_entry.get().split())[:300]
        if not text:
            return
        if not CHAT_CHANNEL_ID:
            self.canvas.itemconfig(self.status, text="Chat isn't set up yet (CHAT_CHANNEL_ID)")
        elif self.my_fp not in ROSTER:
            self.canvas.itemconfig(self.status, text="Not approved to chat yet: click ID and send it to the owner")
        elif has_blocked(text):
            self.canvas.itemconfig(self.status, text="Watch your language! Message not sent.")
        else:
            message_id = "%08x" % _RANDOM.randrange(16 ** 8)
            e, s = sign(self.secret, f"{message_id}|{text}")
            message = f"**{self.username}**: {text} ||{self.public:x}:{e:x}:{s:x}:{message_id}||"
            if self.bot.post(message, CHAT_CHANNEL_ID):
                self.chat_entry.delete(0, "end")   # it appears when Discord sends it back to us
                play(self.chat_send_sound)
            else:
                self.canvas.itemconfig(self.status, text="Can't send: bot isn't connected")

    def show_chat(self, content, quiet=False):
        message = read_chat(content)
        if message is None:
            return    # fake, unsigned, or from someone who isn't approved
        who, name, text, message_id = message
        if message_id in self.seen_ids:
            return    # a repeated copy of a message we already showed
        self.seen_ids.add(message_id)
        if has_blocked(text):
            text = "[hidden by the language filter]"
        hue = sum(ord(ch) for ch in name) % 36    # same name = same color for everyone
        tag = f"hue{hue}"
        log = self.chat_log
        log.config(state="normal")
        log.tag_config(tag, foreground=rainbow(hue / 36, 0.6, 1.0), font=("Helvetica", 11, "bold"))
        log.insert("end", name + ": ", tag)
        log.insert("end", text + "\n")
        log.config(state="disabled")
        log.see("end")
        if not quiet and who != self.my_fp:
            play(self.chat_receive_sound)     # plays even when the chat is minimized
            if not self.chat_open:
                self.unread += 1
                self.update_chat_icon()

    # --- the THEMES page ---
    def make_themes_page(self):
        c = self.canvas
        self.themes_title = c.create_text(WIDTH / 2, 55, text="THEMES", tags="themes",
                                          font=("Helvetica", 40, "bold"))
        for i, name in enumerate(THEMES):
            y1 = 115 + i * 62
            key = f"THEME_{name}"
            self.make_button(key, name, 190, y1, 530, y1 + 52, "themes",
                             lambda n=name: self.set_theme(n))
            colors = THEMES[name]["swatches"]
            for j, color in enumerate(colors):    # little color samples on the button
                x2 = 516 - (len(colors) - 1 - j) * 26
                swatch = c.create_rectangle(x2 - 20, y1 + 16, x2, y1 + 36, fill=color, outline="",
                                            tags="themes")
                self.bind_button(swatch, key)
        self.make_button("THEMES_BACK", "BACK", 260, 385, 460, 430, "themes",
                         lambda: self.show_page("menu"), size=14)

    def update_theme_labels(self):
        for name in THEMES:
            label = f"{name}   (active)" if name == self.theme_name else name
            self.canvas.itemconfig(self.buttons[f"THEME_{name}"]["text"], text=label)

    def set_theme(self, name):
        old = dict(THEME)
        THEME.clear()
        THEME.update(THEMES[name])
        self.theme_name = name
        self.apply_theme(old, THEMES[name])
        save_theme(name)
        self.update_theme_labels()
        self.su_refresh()
        self.canvas.itemconfig(self.status, text=f"Theme: {name}")

    def apply_theme(self, old, new):
        """Swap every themed color on screen from the old theme to the new one."""
        if old is new or all(old[k] == new[k] for k in COLOR_KEYS):
            return
        swap = {old[k]: new[k] for k in COLOR_KEYS}
        c = self.canvas
        c.config(bg=new["bg"])
        for item in c.find_all():
            for option in ("fill", "outline"):
                try:
                    value = c.itemcget(item, option)
                except tk.TclError:
                    continue
                if value in swap:
                    c.itemconfig(item, **{option: swap[value]})
        for entry in (self.entry, self.name_entry, self.chat_entry):
            entry.config(bg=new["panel"], fg=new["text"], insertbackground=new["text"],
                         readonlybackground=new["panel"])
        self.chat_log.config(bg=new["panel_dark"], fg=new["text"])
        for tag in self.chat_log.tag_names():
            if tag.startswith("hue"):
                self.chat_log.tag_config(tag, foreground=rainbow(int(tag[3:]) / 36, 0.6, 1.0))

    # --- the SUDOKU page ---
    def make_sudoku_page(self):
        c = self.canvas
        self.su_title = c.create_text(SU_X, 38, anchor="w", text="MILLOKU", tags="sudoku",
                                      font=("Helvetica", 26, "bold"))
        self.su_cells, self.su_texts = [], []
        for i in range(81):
            row, col = divmod(i, 9)
            x, y = SU_X + col * SU_CELL, SU_Y + row * SU_CELL
            rect = c.create_rectangle(x, y, x + SU_CELL, y + SU_CELL, fill="#161622",
                                      outline="#2a2a3a", tags="sudoku")
            text = c.create_text(x + SU_CELL / 2, y + SU_CELL / 2, fill="white",
                                 font=("Helvetica", 17, "bold"), tags="sudoku")
            for item in (rect, text):
                c.tag_bind(item, "<Button-1>", lambda e, n=i: self.su_select(n))
            self.su_cells.append(rect)
            self.su_texts.append(text)
        size = 9 * SU_CELL
        self.su_lines = []     # the thick lines between the 3x3 boxes
        for k in range(4):
            offset = k * 3 * SU_CELL
            self.su_lines.append(c.create_line(SU_X + offset, SU_Y, SU_X + offset, SU_Y + size,
                                               width=3, tags="sudoku"))
            self.su_lines.append(c.create_line(SU_X, SU_Y + offset, SU_X + size, SU_Y + offset,
                                               width=3, tags="sudoku"))
        cx = 535
        self.su_level_text = c.create_text(cx, 82, fill="white", font=("Helvetica", 18, "bold"), tags="sudoku")
        self.su_info = c.create_text(cx, 106, fill="#8888aa", font=("Helvetica", 10), tags="sudoku")
        self.su_unlocked_text = c.create_text(cx, 138, fill="#6a6a88", font=("Helvetica", 10), tags="sudoku")
        self.make_button("SU_PREV", "<", 420, 122, 470, 154, "sudoku", lambda: self.su_go(-1), size=14)
        self.make_button("SU_NEXT", ">", 600, 122, 650, 154, "sudoku", lambda: self.su_go(1), size=14)
        for d in range(1, 10):
            row, col = divmod(d - 1, 3)
            x1, y1 = 435 + col * 58, 172 + row * 58
            self.make_button(f"SU_N{d}", str(d), x1, y1, x1 + 50, y1 + 50, "sudoku",
                             lambda n=d: self.su_place(n), size=18)
        self.make_button("SU_HINT", "HINT (3)", 435, 352, 601, 386, "sudoku", self.su_hint, size=12)
        self.make_button("SU_BACK", "BACK", 435, 396, 601, 430, "sudoku",
                         lambda: self.show_page("menu"), size=12)

    def open_sudoku(self):
        self.show_page("sudoku")
        if not self.su_started or self.su_won:   # otherwise carry on where you left off
            self.su_load_level(min(self.su_done + 1, 100))
        self.canvas.itemconfig(self.status, text="Click a square, then press a number (or use the pad)")

    def su_load_level(self, level):
        self.su_level = level
        self.su_puzzle, self.su_solution = make_puzzle(level)
        self.su_grid = self.su_puzzle[:]
        self.su_started = True
        self.su_won = False
        self.su_selected = None
        self.su_mistakes = 0
        self.su_hints = 3
        self.su_refresh()

    def su_go(self, step):
        target = self.su_level + step
        if target < 1 or target > 100:
            return
        if target > min(self.su_done + 1, 100):
            self.canvas.itemconfig(self.status, text=f"Beat level {self.su_level} first!")
            return
        self.su_load_level(target)

    def su_select(self, index):
        self.su_selected = index
        self.canvas.focus_set()
        self.su_refresh()

    def su_refresh(self):
        c = self.canvas
        sel = self.su_selected
        sel_value = self.su_grid[sel] if sel is not None else 0
        for i in range(81):
            value = self.su_grid[i]
            if i == sel:
                fill = THEME["sel"]
            elif sel_value and value == sel_value:
                fill = THEME["same"]     # same number as the selected square
            else:
                fill = THEME["panel"]
            c.itemconfig(self.su_cells[i], fill=fill, outline=THEME["grid"], width=1)
            color = THEME["given"] if self.su_puzzle[i] else rainbow(value / 9, 0.7, 1.0)
            c.itemconfig(self.su_texts[i], text=str(value) if value else "", fill=color)
        self.su_update_info()

    def su_update_info(self):
        c = self.canvas
        clues = sum(1 for v in self.su_puzzle if v)
        c.itemconfig(self.su_level_text, text=f"LEVEL {self.su_level} / 100")
        c.itemconfig(self.su_info, text=f"clues {clues}   mistakes {self.su_mistakes}   hints {self.su_hints}")
        c.itemconfig(self.su_unlocked_text, text=f"unlocked: {min(self.su_done + 1, 100)}")
        c.itemconfig(self.buttons["SU_HINT"]["text"], text=f"HINT ({self.su_hints})")

    def su_place(self, digit):
        i = self.su_selected
        if self.su_won or i is None or self.su_grid[i] != 0:
            return
        if digit == self.su_solution[i]:
            self.su_grid[i] = digit
            play(self.click_sound)
            self.su_refresh()
            self.su_check_win()
        else:   # wrong: flash red, count the mistake, don't place it
            self.su_mistakes += 1
            play(self.hover_sound)
            self.canvas.itemconfig(self.su_texts[i], text=str(digit), fill="#ff4d4d")
            self.canvas.itemconfig(self.su_cells[i], fill="#4a1a1a")
            self.su_update_info()
            self.root.after(450, self.su_refresh)

    def su_hint(self):
        if self.su_won:
            return
        if self.su_hints <= 0:
            self.canvas.itemconfig(self.status, text="No hints left on this level")
            return
        i = self.su_selected
        if i is None or self.su_grid[i] != 0:
            empty = [n for n in range(81) if self.su_grid[n] == 0]
            if not empty:
                return
            i = random.choice(empty)
        self.su_hints -= 1
        self.su_grid[i] = self.su_solution[i]
        self.su_selected = i
        self.su_refresh()
        self.su_check_win()

    def su_check_win(self):
        if self.su_grid != self.su_solution:
            return
        self.su_won = True
        level = self.su_level
        if level > self.su_done:
            self.su_done = level
            save_progress(level)
        play(self.jester_sound)
        for _ in range(10 if level < 100 else 25):
            self.ripples.append([random.randint(SU_X, SU_X + 9 * SU_CELL),
                                 random.randint(SU_Y, SU_Y + 9 * SU_CELL), 5])
        if level == 100:
            text = "YOU BEAT ALL 100 LEVELS!!!"
        else:
            text = f"Level {level} complete! Loading level {level + 1}..."
        self.canvas.itemconfig(self.status, text=text)
        self.su_update_info()
        if level % 10 == 0:   # tell the server about milestones
            self.bot.post(f"\U0001F9E9 **{self.username}** just beat Milloku level {level}!",
                          getattr(self.bot, "channel_id", 0))
        if level < 100:
            self.root.after(2500, lambda: self.su_advance(level))

    def su_advance(self, level):
        if self.page == "sudoku" and self.su_level == level and self.su_won:
            self.su_load_level(level + 1)

    def on_key(self, event):
        if self.page != "sudoku":
            return
        try:
            if isinstance(self.root.focus_get(), (tk.Entry, tk.Text)):
                return   # they're typing in the chat
        except KeyError:
            pass
        if event.char and event.char in "123456789":
            self.su_place(int(event.char))
        elif event.keysym in ("Up", "Down", "Left", "Right"):
            if self.su_selected is None:
                self.su_selected = 40
            else:
                row, col = divmod(self.su_selected, 9)
                row += {"Up": -1, "Down": 1}.get(event.keysym, 0)
                col += {"Left": -1, "Right": 1}.get(event.keysym, 0)
                self.su_selected = (row % 9) * 9 + col % 9
            self.su_refresh()

    # --- the SPIN animation ---
    def spin(self):
        if self.spinning:
            return
        if not self.names:
            self.canvas.itemconfig(self.status, text="Add some names first!")
            return
        self.spinning = True
        self.spin_step(0, 25, list(self.names), random.choice(self.names))

    def spin_step(self, i, total, names, winner):
        if i < total:
            self.canvas.itemconfig(self.result_text, text=random.choice(names))
            play(self.hover_sound)
            delay = int(40 + i * i * 0.35)   # starts fast, slows down
            self.root.after(delay, self.spin_step, i + 1, total, names, winner)
        else:
            self.canvas.itemconfig(self.result_text, text=winner)
            play(self.click_sound)
            for _ in range(6):
                self.ripples.append([random.randint(380, 670), random.randint(130, 300), 5])
            self.spinning = False
            self.canvas.itemconfig(self.status, text=f"Winner: {winner}")
            self.send_to_discord(f"\U0001F3B2 The wheel has spoken! **{winner}**")

    def send_to_discord(self, text):
        if self.bot.problem:
            self.canvas.itemconfig(self.status, text=f"Not sent to Discord: {self.bot.problem}"[:90])
        elif not self.bot.ready:
            self.canvas.itemconfig(self.status, text="Bot is still connecting... try again in a moment")
        else:
            future = self.bot.send(text)
            self.root.after(1500, lambda: self.report_send(future))

    def report_send(self, future):
        if not future.done():
            text = "Still sending to Discord..."
        elif future.exception():
            text = f"Discord error: {future.exception()}"[:90]
        else:
            text = "Sent to Discord!"
        self.canvas.itemconfig(self.status, text=text)

    # --- button helpers ---
    def make_button(self, key, label, x1, y1, x2, y2, page, action, size=16, anchor="center"):
        box = self.canvas.create_rectangle(x1, y1, x2, y2, fill="#161622", width=3,
                                           outline="#333344", tags=page)
        if anchor == "w":
            text = self.canvas.create_text(x1 + 25, (y1 + y2) / 2, text=label, anchor="w",
                                           fill="white", font=("Helvetica", size, "bold"), tags=page)
        else:
            text = self.canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=label,
                                           fill="white", font=("Helvetica", size, "bold"), tags=page)
        self.buttons[key] = {"box": box, "action": action, "text": text}
        for item in (box, text):
            self.bind_button(item, key)

    def bind_button(self, item, key):
        self.canvas.tag_bind(item, "<Enter>", lambda e: self.on_hover(key))
        self.canvas.tag_bind(item, "<Leave>", lambda e: self.on_leave())
        self.canvas.tag_bind(item, "<Button-1>", lambda e: self.on_click(e, key))

    def show_page(self, name):
        """Show one page and hide the other."""
        self.page = name
        for page in ("home", "menu", "names", "sudoku", "themes"):
            self.canvas.itemconfig(page, state="normal" if page == name else "hidden")
        self.clear_hover()
        if name == "names":
            self.entry.focus_set()
        else:
            self.canvas.focus_set()   # so the keyboard works for sudoku

    # --- reacting to the mouse ---
    def on_hover(self, key):
        # If we just "left" another piece of this same button, cancel that.
        if self.leave_job is not None:
            self.root.after_cancel(self.leave_job)
            self.leave_job = None
        if self.hovered != key:
            play(self.hover_sound)   # only plays when entering a NEW button
        self.hovered = key
        self.canvas.config(cursor="hand2")

    def on_leave(self):
        # Wait a tiny moment: if the mouse is just moving between the box
        # and the text of the same button, on_hover will cancel this.
        if self.leave_job is None:
            self.leave_job = self.root.after(40, self.clear_hover)

    def clear_hover(self):
        if self.leave_job is not None:
            self.root.after_cancel(self.leave_job)
            self.leave_job = None
        self.hovered = None
        self.canvas.config(cursor="")

    def on_click(self, event, key):
        play(self.click_sound)
        self.ripples.append([event.x, event.y, 5])
        self.buttons[key]["action"]()

    def on_jester_click(self, event, jester):
        play(self.jester_sound)
        self.ripples.append([event.x, event.y, 5])
        jester.poke()
        self.canvas.itemconfig(self.status, text="Hee hee! You poked a jester!")

    # --- what the buttons do ---
    def on_play(self):
        self.show_page("menu")
        self.canvas.itemconfig(self.status, text="Pick a tool!")

    def coming_soon(self):
        self.canvas.itemconfig(self.status, text="Coming soon!")

    def on_back(self):
        self.show_page("home")
        self.canvas.itemconfig(self.status, text="Welcome back!")

    def on_party(self):
        self.party = not self.party
        self.speed = PARTY_SPEED if self.party else NORMAL_SPEED
        if self.party:
            if start_song():
                message = "PARTY MODE ON!"
            elif not SOUND_ON:
                message = "PARTY MODE ON! (install pygame for music)"
            else:
                message = f"PARTY MODE ON! (put {PARTY_SONG} next to gester.py)"
        else:
            stop_song()
            message = "Party mode off"
        self.canvas.itemconfig(self.status, text=message)

    def quit_app(self):
        stop_song()
        self.root.destroy()

    # --- the animation loop: runs about 33 times per second ---
    def tick(self):
        self.frame += 1
        self.hue += self.speed

        # rainbow bar along the top
        for i, rect in enumerate(self.bar):
            self.canvas.itemconfig(rect, fill=rainbow(self.hue + i * 0.012))

        # title letters: each a different color, gently bobbing
        for i, letter in enumerate(self.letters):
            self.canvas.itemconfig(letter, fill=rainbow(self.hue * 2 + i * 0.12))
            bob = math.sin(self.frame * 0.1 + i * 0.8) * (10 if self.party else 4)
            x = WIDTH / 2 + (i - 2.5) * 72
            self.canvas.coords(letter, x, 110 + bob)
        self.canvas.itemconfig(self.options_title, fill=rainbow(self.hue * 2))
        self.canvas.itemconfig(self.names_title, fill=rainbow(self.hue * 2))
        self.canvas.itemconfig(self.themes_title, fill=rainbow(self.hue * 2))
        self.canvas.itemconfig(self.result_text, fill=rainbow(self.hue * 4))

        # buttons glow with the rainbow when hovered
        for key, b in self.buttons.items():
            if key == self.hovered:
                self.canvas.itemconfig(b["box"], outline=rainbow(self.hue * 3), fill=THEME["panel_hi"])
            else:
                self.canvas.itemconfig(b["box"], outline=THEME["border"], fill=THEME["panel"])


        # sudoku page: rainbow title and lines, glowing selected square, victory rainbow
        if self.page == "sudoku":
            self.canvas.itemconfig(self.su_title, fill=rainbow(self.hue * 2))
            for line in self.su_lines:
                self.canvas.itemconfig(line, fill=rainbow(self.hue * 3))
            if self.su_selected is not None and not self.su_won:
                self.canvas.itemconfig(self.su_cells[self.su_selected],
                                       outline=rainbow(self.hue * 3), width=3)
            if self.su_won:
                for i, text in enumerate(self.su_texts):
                    self.canvas.itemconfig(text, fill=rainbow(self.hue * 4 + i * 0.012, 0.7, 1.0))

        # messages and name changes from Discord; a problem here must not stop the animation
        try:
            self.check_inbox()
        except Exception as error:
            print("inbox problem:", error)
        self.canvas.itemconfig(self.buttons["CHATICON"]["text"],
                               fill=rainbow(self.hue * 5) if self.unread else THEME["text"])

        # jesters wander around (faster in Party Mode)
        for jester in self.jesters:
            jester.update(self.hue, 2.5 if self.party else 1, self.frame)

        # floating particles
        for p in self.particles:
            p["y"] -= p["speed"] * (3 if self.party else 1)
            if p["y"] < -10:
                p["y"] = HEIGHT + 10
                p["x"] = random.randint(0, WIDTH)
            self.canvas.coords(p["id"], p["x"], p["y"], p["x"] + p["size"], p["y"] + p["size"])
            self.canvas.itemconfig(p["id"], fill=rainbow(self.hue + p["x"] / WIDTH, 0.6, 0.9))

        # party mode sprinkles random ripples
        if self.party and self.frame % 12 == 0:
            self.ripples.append([random.randint(0, WIDTH), random.randint(200, HEIGHT), 5])

        # click ripples
        self.canvas.delete("ripple")
        for r in self.ripples[:]:
            r[2] += 5
            if r[2] > 110:
                self.ripples.remove(r)
                continue
            x, y, size = r
            self.canvas.create_oval(x - size, y - size, x + size, y + size,
                                    outline=rainbow(self.hue + size / 150), width=2, tags="ripple")

        self.root.after(30, self.tick)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Gester().run()
