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
import colorsys, math, random, os, sys, json, asyncio, threading, wave, hashlib, time
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
    "64ec516005f3": "Flug",
    "2cea0f4f79e0": "Emii",
    "34c65519ed36": "Millana",
}

# YOUR ID: only this person gets the CLEAR button in the chat panel.
# (Click ID in the CHAT tab to copy yours, then paste it between the quotes.)
OWNER_ID = "64ec516005f3"

# Messages containing these words are blocked (whole words only). Add your own!
BLOCKED_WORDS = {"nigger", "nigga"}

# AUTO-UPDATING SOUNDS: your GitHub repo as "yourname/gester" ("" = off).
# Put your sound files in a folder called "sounds" in that repo.
GITHUB_REPO = "susmonkeu/gester"

# MULTIPLAYER: paste your Discord channel IDs here (0 = that feature is off)
SYNC_CHANNEL_ID = 1556072377530458174      # the channel that keeps everyone's name list in sync
CHAT_CHANNEL_ID = 1556072398111903784      # the channel the chat box uses
BOARD_CHANNEL_ID = 1556556283266469928     # the channel the Milloku leaderboard uses
USE_MESSAGE_CONTENT_INTENT = False   # only set True if the chat shows blank messages
CHAT_W = 300             # how much wider the window gets when the chat is open
VERSION = "1.9.1"          # change this each update so you can see it worked

HOVER_SOUND = "hover.wav"
CLICK_SOUND = "click.wav"
JESTER_SOUND = "jester.wav"
PARTY_SONG = "party_song.mp3"
CHAT_SEND_SOUND = "chat_send.wav"          # plays when YOU send a chat message
CHAT_RECEIVE_SOUND = "chat_receive.wav"    # plays when SOMEONE ELSE sends one
INTRO_SOUND = "intro.wav"                  # the sound at the start of the intro
WHOOSH_SOUND = "page_whoosh.wav"           # plays when you change pages
CHAT_OPEN_SOUND = "chat_open.wav"          # plays when the chat slides open
CHAT_CLOSE_SOUND = "chat_close.wav"        # ...and when it closes
MENU_MUSIC = "menu_music.mp3"              # main menu music (a built-in tune plays if this is missing)
MENU_VOLUME = 0.7                          # main menu music volume
MENU_MUFFLED = 0.18                        # how quiet it gets on other pages
INTRO_FRAMES = 84                          # how long the intro lasts (about 2.5 seconds)
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


def write_wave(path, segments, volume=9000):
    """Make a sound file. segments = [(start_hz, end_hz, milliseconds), ...], each one fading out."""
    rate = 22050
    data = bytearray()
    phase = 0.0
    for start_hz, end_hz, milliseconds in segments:
        count = int(rate * milliseconds / 1000)
        for i in range(count):
            phase += 2 * math.pi * (start_hz + (end_hz - start_hz) * i / count) / rate
            data += int(volume * math.sin(phase) * (1 - i / count)).to_bytes(2, "little", signed=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(bytes(data))


def make_default_sounds():
    """Make simple built-in sounds, but only for the ones you haven't provided."""
    defaults = {
        CHAT_SEND_SOUND: [(660, 660, 60), (880, 880, 90)],             # quick rising blip
        CHAT_RECEIVE_SOUND: [(988, 988, 80), (784, 784, 140)],         # soft falling ding-dong
        INTRO_SOUND: [(262, 262, 100), (330, 330, 100), (392, 392, 100), (523, 523, 100), (523, 1568, 500)],
        WHOOSH_SOUND: [(220, 1100, 230)],                              # page change swoosh
        CHAT_OPEN_SOUND: [(500, 1100, 120), (1100, 1400, 90)],         # chat slides open
        CHAT_CLOSE_SOUND: [(1100, 450, 160)],                          # chat slides shut
    }
    for name, segments in defaults.items():
        if find_file(name) is not None:
            continue
        try:
            os.makedirs(DEFAULT_DIR, exist_ok=True)
            write_wave(os.path.join(DEFAULT_DIR, name), segments)
        except Exception:
            pass


def make_menu_music():
    """A calm looping tune made from scratch, used when you haven't added menu_music.mp3."""
    name = "menu_music_default.wav"
    if find_file(MENU_MUSIC) is not None or find_file(name) is not None:
        return
    try:
        os.makedirs(DEFAULT_DIR, exist_ok=True)
        rate, step = 16000, 3.0                  # 4 chords x 3 seconds = a 12 second loop
        chords = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63),
                  (261.63, 329.63, 392.0), (196.0, 246.94, 293.66)]
        total = int(rate * step * len(chords))
        samples = [0.0] * total
        for index, chord in enumerate(chords):
            start = int(index * step * rate)
            for n in range(int(step * rate)):    # a slow, soft pad
                t = n / rate
                fade = max(0.0, min(1.0, t / 0.4, (step - t) / 0.6))
                samples[start + n] += sum(math.sin(2 * math.pi * hz * t) for hz in chord) * 0.07 * fade
            for k in range(8):                   # plus a gentle plucked pattern on top
                hz = chord[(0, 2, 1, 2, 0, 1, 2, 1)[k] % 3] * 2
                begin = start + int(k * 0.375 * rate)
                for n in range(int(0.9 * rate)):
                    t = n / rate
                    samples[(begin + n) % total] += math.sin(2 * math.pi * hz * t) * 0.10 * math.exp(-5 * t)
        data = bytearray()
        for value in samples:
            data += int(max(-1.0, min(1.0, value)) * 28000).to_bytes(2, "little", signed=True)
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
        critter="jester",
        palette=None, swatches=["#ff4d4d", "#ffb84d", "#4dff88", "#4d9dff", "#c04dff"],
        bg="#0d0d14", panel="#161622", panel_hi="#1e1e30", panel_dark="#10101a",
        border="#333344", grid="#2a2a3a", sel="#2b2b44", same="#222240",
        text="white", given="#e8e8ff", muted="#6a6a88", dim="#8888aa", faint="#444460"),
    "EMII": dict(    # minion: yellow, blue and black
        critter="minion",
        palette=["#ffd90f", "#3d8bff"], swatches=["#ffd90f", "#3d8bff"],
        bg="#090b12", panel="#0f1a36", panel_hi="#18285a", panel_dark="#0a1124",
        border="#2a4a9a", grid="#1b2d5c", sel="#27408a", same="#1a2d63",
        text="#fff6c2", given="#fffbe0", muted="#7a8fc7", dim="#9db0e0", faint="#3a4a7a"),
    "MILLANA": dict(    # orange and purple
        critter="cat",
        palette=["#ff8a1f", "#a259ff"], swatches=["#ff8a1f", "#a259ff"],
        bg="#0f0818", panel="#1c1030", panel_hi="#2a1848", panel_dark="#140a22",
        border="#5a2f99", grid="#2d1a4d", sel="#3d2468", same="#2a1a47",
        text="#fff1e0", given="#ffe3c4", muted="#9c7fc4", dim="#b79be0", faint="#4a3470"),
    "FLUG": dict(    # green and white
        critter="alien",
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


SETTINGS_FILE = os.path.join(HERE, "settings.json")


def load_muted():
    try:
        with open(SETTINGS_FILE) as f:
            return bool(json.load(f)["muted"])
    except Exception:
        return False


def save_muted(muted):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump({"muted": muted}, f)
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


# ---------- LOOK: colors, rounded shapes, 3D text ----------
def to_rgb(color):
    if color == "white":
        return (255, 255, 255)
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def mix(a, b, amount):
    """Blend color a toward color b (0 = all a, 1 = all b)."""
    ra, rb = to_rgb(a), to_rgb(b)
    return "#%02x%02x%02x" % tuple(int(ra[k] + (rb[k] - ra[k]) * amount) for k in range(3))


def rounded(x1, y1, x2, y2, r):
    """Points for a rounded rectangle (draw with create_polygon(..., smooth=True))."""
    r = max(1, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r,
            x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]


def bounce(p):
    """Easing for 0..1 that lands and bounces like a ball."""
    if p < 1 / 2.75:
        return 7.5625 * p * p
    if p < 2 / 2.75:
        p -= 1.5 / 2.75
        return 7.5625 * p * p + 0.75
    if p < 2.5 / 2.75:
        p -= 2.25 / 2.75
        return 7.5625 * p * p + 0.9375
    p -= 2.625 / 2.75
    return 7.5625 * p * p + 0.984375


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


def read_clear(content):
    """Is this a genuine, fresh 'clear the chat' message from the owner? Returns its ID or None."""
    try:
        if not (OWNER_ID and content.startswith("GESTER-CLEAR ")):
            return None
        public_hex, e_hex, s_hex, message_id, stamp = content[13:].split(":")
        public = int(public_hex, 16)
        if fingerprint(public) != OWNER_ID or abs(time.time() - int(stamp)) > 300:
            return None      # not the owner, or an old copy someone is replaying
        if not verify(public, f"CLEAR|{message_id}|{stamp}", int(e_hex, 16), int(s_hex, 16)):
            return None
        return message_id
    except Exception:
        return None


def read_board(content):
    """Check a leaderboard message. Returns (id, levels_beaten, time) or None if fake."""
    try:
        if not content.startswith("GESTER-BOARD "):
            return None
        public_hex, e_hex, s_hex, level, stamp = content[13:].split(":")
        public = int(public_hex, 16)
        who = fingerprint(public)
        level, stamp = int(level), int(stamp)
        if who not in ROSTER or not 0 <= level <= 100:
            return None
        if not verify(public, f"BOARD|{level}|{stamp}", int(e_hex, 16), int(s_hex, 16)):
            return None
        return who, level, stamp
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


BOARD_FILE = os.path.join(HERE, "leaderboard.json")


def load_board():
    """Last known scores {id: [levels_beaten, time]}, so the board survives restarts."""
    try:
        with open(BOARD_FILE) as f:
            return {k: [int(v[0]), int(v[1])] for k, v in json.load(f).items()}
    except Exception:
        return {}


def save_board(board):
    try:
        with open(BOARD_FILE, "w") as f:
            json.dump(board, f)
    except OSError:
        pass


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
            elif message.channel.id == BOARD_CHANNEL_ID:
                self.inbox.append(("board", message.content))

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
            if BOARD_CHANNEL_ID:
                channel = await self.find_channel(BOARD_CHANNEL_ID)
                found = [m.content async for m in channel.history(limit=300)]
                self.inbox.append(("board_history", found[::-1]))
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

    def clear_chat_channel(self, marker):
        """Post the signed 'clear' message, wait a moment, then delete everything in the chat channel."""
        if self.problem or not self.ready or not CHAT_CHANNEL_ID:
            return False

        async def go():
            channel = await self.find_channel(CHAT_CHANNEL_ID)
            await channel.send(marker, allowed_mentions=discord.AllowedMentions.none())
            await asyncio.sleep(1.5)     # let everyone's Gester see the message first
            try:
                await channel.purge(limit=None, bulk=True)
            except discord.Forbidden:    # no "Manage Messages": delete the bot's own messages one by one
                await channel.purge(limit=None, bulk=False)
        asyncio.run_coroutine_threadsafe(go(), self.loop).add_done_callback(self.report_failure)
        return True

    def post_sync(self, kind, name=""):
        return self.post(f"GESTER-SYNC {self.client_id} {kind} {name}".strip(), SYNC_CHANNEL_ID)


# The part of the canvas you can currently see (it changes when the window is resized).
VIEW = {"x0": 0.0, "y0": 0.0, "x1": float(WIDTH), "y1": float(HEIGHT)}
BAR_W, BAR_PAD = 12, 1800     # the rainbow bar is built from 12px pieces that reach far past the window


# ---------- THE BACKGROUND CHARACTERS (jesters, minions, cats, aliens) ----------
CRITTER_SAYS = {"jester": "Hee hee! You poked a jester!", "minion": "Bello! You poked a minion!",
                "cat": "Meow! You poked a cat!", "alien": "Greetings, human! You poked an alien!"}


class Jester:
    """One wandering background character. Its look changes with the theme."""

    def __init__(self, canvas, x, y, on_click, style="jester", above=None):
        self.canvas = canvas
        self.x, self.y = x, y
        self.on_click = on_click
        self.above = above                     # stays just above this item, so it sits behind the buttons
        self.dx = random.choice([-1, 1]) * random.uniform(0.6, 1.5)
        self.dy = random.choice([-1, 1]) * random.uniform(0.4, 1.0)
        self.offset = random.random()          # gives each character its own color
        self.phase = random.random() * 6       # makes them wiggle at different times
        self.boost = 0                         # extra speed after being clicked
        self.parts = []
        self.set_style(style)

    def set_style(self, style):
        """Draw this character as a jester, minion, cat or alien (replacing the old drawing)."""
        for part in self.parts:
            self.canvas.delete(part)
        self.style = style
        c, x, y = self.canvas, self.x, self.y
        dim = lambda color: mix(color, THEME["bg"], 0.3)    # slightly faded so they stay in the background

        def at(points):  # shift shape coordinates to where the character is
            return [v + (x if i % 2 == 0 else y) for i, v in enumerate(points)]

        def oval(box, color):
            return c.create_oval(at(box), fill=color, outline="")

        def poly(points, color, smooth=False):
            return c.create_polygon(at(points), fill=color, outline="", smooth=smooth)

        def blob(x1, y1, x2, y2, r, color):
            return c.create_polygon(rounded(x + x1, y + y1, x + x2, y + y2, r), smooth=True, fill=color, outline="")

        def line(points, color, width=2, smooth=False):
            return c.create_line(at(points), fill=color, width=width, capstyle="round", smooth=smooth)

        if style == "minion":
            yellow, blue, dark = dim("#f5c800"), dim("#2f5fb3"), dim("#4a3320")
            parts = [blob(-13, -24, 13, 28, 12, yellow),                     # body
                     blob(-13, 8, 13, 28, 10, blue),                         # overalls
                     poly([-8, 2, 8, 2, 8, 12, -8, 12], blue),               # bib
                     oval([-18, 4, -12, 16], yellow), oval([12, 4, 18, 16], yellow),    # arms
                     poly([-13, -12, 13, -12, 13, -6, -13, -6], dim("#3a3a44")),        # goggle strap
                     oval([-8, -15, 8, 1], dim("#b8bcc8")),                  # goggle
                     oval([-5.5, -12.5, 5.5, -1.5], dim("#ffffff")),         # eye
                     oval([-2.5, -9.5, 2.5, -4.5], dark),                    # pupil
                     line([-5, 5, 0, 8, 5, 5], dark, 2, True),               # smile
                     line([0, -24, -3, -30], dark, 1), line([0, -24, 0, -31], dark, 1),
                     line([0, -24, 3, -30], dark, 1)]                        # hair
        elif style == "cat":
            palette = THEME["palette"] or ["#ff8a1f", "#a259ff"]
            fur = dim(palette[int(self.offset * len(palette)) % len(palette)])
            light, pink, eye = mix(fur, "#ffffff", 0.35), dim("#ff9ec4"), dim("#ffe46b")
            parts = [line([10, 26, 24, 24, 28, 12, 22, 2], fur, 5, True),    # tail
                     oval([-11, 4, 11, 34], fur),                            # body
                     oval([-10, 28, -2, 36], light), oval([2, 28, 10, 36], light),      # paws
                     poly([-14, -4, -13, -26, -3, -13], fur), poly([14, -4, 13, -26, 3, -13], fur),   # ears
                     poly([-11, -8, -11, -20, -5, -12], pink), poly([11, -8, 11, -20, 5, -12], pink),
                     oval([-14, -14, 14, 12], fur),                          # head
                     oval([-9, -6, -2, 3], eye), oval([2, -6, 9, 3], eye),   # eyes
                     oval([-6.5, -5, -4.5, 2], "#101018"), oval([4.5, -5, 6.5, 2], "#101018"),
                     poly([-2, 4, 2, 4, 0, 7], pink)]                        # nose
            for side in (-1, 1):                                             # whiskers
                for tilt in (-3, 1, 5):
                    parts.append(line([side * 9, 6, side * 24, 6 + tilt], light, 1))
        elif style == "alien":
            green = dim(THEME["palette"][0] if THEME["palette"] else "#2ee66b")
            dark, glint = mix(green, "#000000", 0.35), dim("#d8ffe6")
            parts = [line([-6, -22, -12, -34], green, 2), line([6, -22, 12, -34], green, 2),   # antennae
                     oval([-15, -38, -9, -32], glint), oval([9, -38, 15, -32], glint),
                     oval([-8, 8, 8, 34], dark),                             # body
                     line([-8, 14, -17, 26], green, 3), line([8, 14, 17, 26], green, 3),   # arms
                     oval([-9, 31, -1, 37], green), oval([1, 31, 9, 37], green),           # feet
                     oval([-16, -26, 16, 12], green),                        # big head
                     poly([-14, -11, -4, -4, -6, 3, -14, -3], "#101018", True),            # eyes
                     poly([14, -11, 4, -4, 6, 3, 14, -3], "#101018", True),
                     oval([-11, -7, -9, -5], glint), oval([9, -7, 11, -5], glint),
                     line([-3, 7, 3, 7], dark, 2)]                           # mouth
        else:                                                                # the jester
            self.body = poly([-8, 10, 8, 10, 13, 34, -13, 34], rainbow(self.offset + 0.5, 0.7, 0.5))
            head = oval([-10, -10, 10, 10], "#e8d2b4")
            self.hat = poly([-12, -6, -19, -24, -8, -13, 0, -27, 8, -13, 19, -24, 12, -6],
                            rainbow(self.offset, 0.7, 0.6))
            bells = [oval([bx - 3, by - 3, bx + 3, by + 3], "#f2c94c")
                     for bx, by in [(-19, -24), (0, -27), (19, -24)]]
            eyes = [oval([ex - 1.5, -3, ex + 1.5, 0], "#222222") for ex in (-4, 4)]
            parts = [self.body, head, self.hat] + bells + eyes

        ref = self.above
        for part in parts:       # keep them just above the floating dots, behind everything else
            if ref is not None:
                c.tag_raise(part, ref)
            ref = part
        self.parts = parts
        for part in parts:       # every piece is clickable
            c.tag_bind(part, "<Button-1>", lambda e: self.on_click(e, self))
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
        if (self.x < VIEW["x0"] + 25 and self.dx < 0) or (self.x > VIEW["x1"] - 25 and self.dx > 0):
            self.dx *= -1
        if (self.y < VIEW["y0"] + 40 and self.dy < 0) or (self.y > VIEW["y1"] - 45 and self.dy > 0):
            self.dy *= -1

        for part in self.parts:
            self.canvas.move(part, dx, dy)

        if self.style == "jester":    # jesters shimmer with the theme colors
            self.canvas.itemconfig(self.hat, fill=rainbow(hue + self.offset, 0.7, 0.6))
            self.canvas.itemconfig(self.body, fill=rainbow(hue + self.offset + 0.5, 0.7, 0.5))


class FancyText:
    """Text that looks 3D: darker copies stacked behind it, a soft shadow and a bright bevel edge."""

    def __init__(self, canvas, x, y, text, size, tags, depth=2, shadow=False, **options):
        self.canvas, self.shown = canvas, int(size)
        roles = []
        if shadow:
            roles.append((depth * 0.85 + 3, depth * 1.05 + 4, "shadow"))
        roles += [(d * 0.85, d * 1.05, "layer") for d in range(depth, 0, -1)]   # deepest first
        roles += [(-1, -1, "hl"), (0, 0, "face")]
        self.ids, self.offsets, self.roles = [], [], []
        for ox, oy, role in roles:
            item = canvas.create_text(x + ox, y + oy, text=text, fill="white", tags=tags,
                                      font=("Helvetica", int(size), "bold"), **options)
            self.ids.append(item)
            self.offsets.append((ox, oy))
            self.roles.append(role)

    def set_text(self, text):
        for item in self.ids:
            self.canvas.itemconfig(item, text=text)

    def move(self, x, y):
        for item, (ox, oy) in zip(self.ids, self.offsets):
            self.canvas.coords(item, x + ox, y + oy)

    def set_size(self, size):
        size = max(6, int(round(size)))
        if size != self.shown:
            self.shown = size
            for item in self.ids:
                self.canvas.itemconfig(item, font=("Helvetica", size, "bold"))

    def paint(self, face):
        layers = [i for i, r in zip(self.ids, self.roles) if r == "layer"]
        for n, item in enumerate(layers):      # the deeper the layer, the darker it gets
            self.canvas.itemconfig(item, fill=mix(face, "#000000", 0.8 - 0.35 * n / max(1, len(layers) - 1)))
        for item, role in zip(self.ids, self.roles):
            if role == "hl":
                self.canvas.itemconfig(item, fill=mix(face, "#ffffff", 0.6))
            elif role == "shadow":
                self.canvas.itemconfig(item, fill=mix(THEME["bg"], "#000000", 0.6))
            elif role == "face":
                self.canvas.itemconfig(item, fill=face)


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
        self.root.resizable(True, True)
        self.root.minsize(WIDTH, HEIGHT)      # you can make it bigger, but not smaller than this
        self.chat_frac = 0.0                  # 0 = chat closed, 1 = chat fully open (animates between)
        self.chat_extra = 0                   # how many pixels the chat widened the window

        self.canvas = tk.Canvas(self.root, width=WIDTH, height=HEIGHT,
                                bg=THEME["bg"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self.on_resize)

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
        self.muted = load_muted()
        self.music_mode = None       # None, "menu" or "party"
        self.music_vol = 0.0
        self.intro_frame = 0
        self.intro_done = False
        self.transition = None       # a page-change wipe in progress
        self.chat_anim = None        # the chat sliding open or closed
        self.clear_chat_armed = False
        self.chat_open = False
        self.unread = 0
        self.clear_armed = False
        self.spinning = False
        self.bot = DiscordLink()
        self.updates = deque()           # news from the background sound updater
        self.board = load_board()        # Milloku leaderboard: {id: [levels beaten, time]}
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

        make_default_sounds()
        make_menu_music()
        self.load_all_sounds()

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
        self.make_board_page()
        self.make_chat_panel()
        self.make_wipe_bars()
        self.page_titles = {"menu": [self.options_title], "names": [self.names_title],
                            "sudoku": [self.su_title], "themes": [self.themes_title],
                            "board": [self.board_title]}

        self.status = self.canvas.create_text(
            WIDTH / 2, 455, text="Welcome to Gester!",
            fill="#8888aa", font=("Helvetica", 12))

        self.canvas.create_text(WIDTH - 10, HEIGHT - 8, anchor="se", text=f"v{VERSION}",
                                fill="#444460", font=("Helvetica", 9))

        threading.Thread(target=sync_sounds, args=(self.updates,), daemon=True).start()
        self.theme_name = load_theme_name()
        self.apply_theme(THEMES["RAINBOW"], THEME)   # items are built in rainbow colors first
        self.update_theme_labels()

        self._apply_page("home")
        self.begin_intro()
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)
        self.root.bind("<Key>", self.on_key)
        self.root.bind("<Button-1>", lambda e: self.skip_intro(), add="+")   # click to skip the intro
        self.tick()  # start the animation loop

    def load_all_sounds(self):
        self.hover_sound = load_sound(HOVER_SOUND, 0.5)
        self.click_sound = load_sound(CLICK_SOUND)
        self.jester_sound = load_sound(JESTER_SOUND)
        self.chat_send_sound = load_sound(CHAT_SEND_SOUND, 0.8)
        self.chat_receive_sound = load_sound(CHAT_RECEIVE_SOUND, 0.8)
        self.intro_sound = load_sound(INTRO_SOUND, 0.9)
        self.whoosh_sound = load_sound(WHOOSH_SOUND, 0.6)
        self.chat_open_sound = load_sound(CHAT_OPEN_SOUND, 0.7)
        self.chat_close_sound = load_sound(CHAT_CLOSE_SOUND, 0.7)

    # --- music: loud on the main menu, quiet in the background on other pages ---
    def start_menu_music(self):
        path = find_file(MENU_MUSIC) or find_file("menu_music_default.wav")
        if SOUND_ON and path:
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(0.0)
                pygame.mixer.music.play(-1)
                self.music_mode, self.music_vol = "menu", 0.0
            except Exception:
                pass

    def update_music(self):
        if not SOUND_ON or self.music_mode is None:
            return
        if self.muted:
            target = 0.0
        elif self.music_mode == "party":
            target = 0.7
        else:
            target = MENU_VOLUME if self.page == "home" else MENU_MUFFLED
        if abs(target - self.music_vol) > 0.003:      # glide to the new volume
            self.music_vol += (target - self.music_vol) * 0.07
            pygame.mixer.music.set_volume(max(0.0, min(1.0, self.music_vol)))

    def toggle_mute(self):
        self.muted = not self.muted
        save_muted(self.muted)
        self.canvas.itemconfig(self.status, text="Music muted" if self.muted else "Music on")

    # --- the intro: the bar sweeps in, GESTER drops and bounces, the buttons pop up ---
    def begin_intro(self):
        c = self.canvas
        for rect in self.bar:
            c.itemconfig(rect, state="hidden")
        c.itemconfig(self.tagline, state="hidden")
        for key in ("PLAY", "PARTY MODE", "QUIT"):
            for item in self.buttons[key]["items"]:
                c.itemconfig(item, state="hidden")

    def step_intro(self):
        c, f = self.canvas, self.intro_frame
        if f == 0:
            play(self.intro_sound)
        shown = min(1.0, f / 28)                      # the rainbow bar sweeps in from the left
        reach = VIEW["x0"] + shown * (VIEW["x1"] - VIEW["x0"])
        for rect, x in zip(self.bar, self.bar_x):
            c.itemconfig(rect, state="normal" if x <= reach else "hidden")
        for i in range(len(self.letters)):            # each letter thumps down
            if f == i * 5 + 24:
                play(self.hover_sound)
                self.ripples.append([WIDTH / 2 + (i - 2.5) * 72, 150, 5])
        flash = max(0.0, 1 - (f - 49) / 10) if f >= 49 else 0.0   # a flash when the last letter lands
        c.config(bg=mix(THEME["bg"], rainbow(self.hue * 3), 0.35 * flash))
        if f == 52:
            c.itemconfig(self.tagline, state="normal")
        for n, key in enumerate(("PLAY", "PARTY MODE", "QUIT")):
            if f == 54 + n * 8:                       # the buttons pop up one by one
                b = self.buttons[key]
                for item in b["items"]:
                    c.itemconfig(item, state="normal")
                b["scale"], b["kick"] = 0.3, 0.12
                play(self.hover_sound)
        if f == 56:
            self.start_menu_music()
        self.intro_frame += 1
        if self.intro_frame >= INTRO_FRAMES:
            self.finish_intro()

    def finish_intro(self):
        c = self.canvas
        self.intro_done = True
        for rect in self.bar:
            c.itemconfig(rect, state="normal")
        c.itemconfig(self.tagline, state="normal")
        for key in ("PLAY", "PARTY MODE", "QUIT"):
            for item in self.buttons[key]["items"]:
                c.itemconfig(item, state="normal")
        c.config(bg=THEME["bg"])
        if self.music_mode is None:
            self.start_menu_music()

    def skip_intro(self):
        if not self.intro_done:
            if self.intro_sound:
                self.intro_sound.stop()
            self.finish_intro()

    # --- page change wipe: colored bars zip across, the page swaps behind them, then they zip away ---
    def make_wipe_bars(self):
        self.wipe_bars = [self.canvas.create_rectangle(0, 0, 0, 0, fill="", outline="", width=2,
                                                       state="hidden", tags="wipe") for _ in range(10)]

    def step_transition(self):
        tr, c = self.transition, self.canvas
        tr["t"] += 1
        t, n, length = tr["t"], len(self.wipe_bars), 7
        cover_done = length + n
        if t >= cover_done and not tr["applied"]:
            tr["applied"] = True
            self._apply_page(tr["page"])             # swap pages while the screen is covered
        vx0, vy0, vx1, vy1 = VIEW["x0"], VIEW["y0"], VIEW["x1"], VIEW["y1"]
        vh, width = vy1 - vy0, (vx1 - vx0) / n
        for i, bar in enumerate(self.wipe_bars):
            order = i if tr["forward"] else n - 1 - i
            covering = t <= cover_done
            p = (t - order) / length if covering else (t - cover_done - order) / length
            p = min(1.0, max(0.0, p))
            ease = p * p * (3 - 2 * p)
            from_top = i % 2 == 0                    # every other bar comes from the bottom
            if covering:
                ya, yb = (vy0, vy0 + vh * ease) if from_top else (vy0 + vh * (1 - ease), vy1)
                visible = p > 0
            else:
                ya, yb = (vy0 + vh * ease, vy1) if from_top else (vy0, vy0 + vh * (1 - ease))
                visible = p < 1
            if visible:
                c.coords(bar, vx0 + i * width, ya, vx0 + (i + 1) * width + 1, yb)
                c.itemconfig(bar, state="normal", fill=mix(THEME["bg"], rainbow(self.hue * 2 + i * 0.1), 0.75),
                             outline=rainbow(self.hue * 3 + i * 0.1))
            else:
                c.itemconfig(bar, state="hidden")
        if t >= 2 * cover_done:
            self.transition = None

    def step_chat_anim(self):
        a = self.chat_anim
        a["t"] += 1
        p = min(1.0, a["t"] / 12)
        e = 1 - (1 - p) ** 3
        self.chat_frac = a["from"] + (a["to"] - a["from"]) * e
        cw = self.canvas.winfo_width()
        if a["dw"]:                                  # the window only widens/narrows if it needs to
            cw = int(a["w0"] + a["dw"] * e)
            self.chat_extra = int(a["extra0"] + a["dw"] * e)
            self.root.geometry(f"{cw}x{self.root.winfo_height()}")
        self.layout(cw, self.canvas.winfo_height())
        if p >= 1.0:
            self.chat_anim = None
            self.chat_frac = a["to"]
            self.layout()
            if self.chat_open:
                self.root.minsize(WIDTH + CHAT_W, HEIGHT)
            else:
                self.canvas.itemconfig("chat", state="hidden")

    # --- resizing: the pages stay centered, the background fills the whole window ---
    def on_resize(self, event=None):
        self.layout(event.width if event else None, event.height if event else None)

    def layout(self, cw=None, ch=None):
        c = self.canvas
        cw, ch = cw or c.winfo_width(), ch or c.winfo_height()
        if cw < 100 or ch < 100 or not hasattr(self, "bar"):
            return
        content = WIDTH + CHAT_W * self.chat_frac          # the pages, plus the chat panel as it opens
        ox = int(max(0, (cw - content) / 2))
        oy = int(max(0, (ch - HEIGHT) / 2))
        c.config(scrollregion=(-ox, -oy, -ox + cw, -oy + ch))
        c.xview_moveto(0)
        c.yview_moveto(0)
        VIEW.update(x0=float(-ox), y0=float(-oy), x1=float(-ox + cw), y1=float(-oy + ch))
        if self.bar_top != VIEW["y0"]:                      # keep the rainbow bar on the very top edge
            self.bar_top = VIEW["y0"]
            for rect, x in zip(self.bar, self.bar_x):
                c.coords(rect, x, self.bar_top, x + BAR_W, self.bar_top + 10)
        want = min(220, int(NUM_PARTICLES * (cw * ch) / (WIDTH * HEIGHT)))   # more dots in a bigger window
        want = max(want, NUM_PARTICLES)
        while len(self.particles) < want:
            self.add_particle(random.uniform(VIEW["x0"], VIEW["x1"]), random.uniform(VIEW["y0"], VIEW["y1"]))
        while len(self.particles) > want:                   # smaller window again: drop the extras
            c.delete(self.particles.pop()["id"])

    # --- background pieces ---
    def add_particle(self, x, y):
        size = random.randint(2, 5)
        dot = self.canvas.create_oval(x, y, x + size, y + size, outline="")
        if self.particles:                  # keep it with the other dots, behind the pages
            self.canvas.tag_raise(dot, self.particles[-1]["id"])
        self.particles.append({"id": dot, "x": x, "y": y, "size": size, "speed": random.uniform(0.3, 1.5)})

    def make_particles(self):
        self.particles = []
        for _ in range(NUM_PARTICLES):
            self.add_particle(random.randint(0, WIDTH), random.randint(0, HEIGHT))

    def make_jesters(self):
        above = self.particles[-1]["id"] if self.particles else None
        self.jesters = [Jester(self.canvas, random.randint(40, WIDTH - 40),
                               random.randint(60, HEIGHT - 60), self.on_jester_click,
                               THEME["critter"], above)
                        for _ in range(NUM_JESTERS)]

    def make_bar(self):
        count = (WIDTH + CHAT_W + 2 * BAR_PAD) // BAR_W + 1
        self.bar_x = [-BAR_PAD + i * BAR_W for i in range(count)]
        self.bar_top = VIEW["y0"]
        self.bar = [self.canvas.create_rectangle(x, self.bar_top, x + BAR_W, self.bar_top + 10, outline="")
                    for x in self.bar_x]

    # --- the HOME page ---
    def make_home_page(self):
        self.letters = []
        for i, letter in enumerate("GESTER"):
            x = WIDTH / 2 + (i - 2.5) * 72
            item = FancyText(self.canvas, x, 110, letter, 64, "home", depth=8, shadow=True)
            self.letters.append(item)
        self.tagline = self.canvas.create_text(WIDTH / 2, 175, text="move your mouse. click things.",
                                               fill="#6a6a88", font=("Helvetica", 12), tags="home")

        labels = [("PLAY", self.on_play), ("PARTY MODE", self.on_party), ("QUIT", self.quit_app)]
        for i, (label, action) in enumerate(labels):
            y1 = 220 + i * 70
            self.make_button(label, label, 210, y1, 510, y1 + 52, "home", action)

    # --- the TOOL MENU (opens when you click PLAY) ---
    def make_menu_page(self):
        self.options_title = FancyText(self.canvas, WIDTH / 2, 60, "CHOOSE A TOOL", 40, "menu",
                                       depth=5, shadow=True)
        tools = [("NAME CHOOSER", lambda: self.show_page("names")),
                 ("MILLOKU", self.open_sudoku),
                 ("LEADERBOARD", self.open_board),
                 ("THEMES", lambda: self.show_page("themes"))]
        for i, (label, action) in enumerate(tools):
            y1 = 118 + i * 62
            self.make_button(label, label, 210, y1, 510, y1 + 52, "menu", action)
        self.make_button("BACK", "BACK", 260, 385, 460, 430, "menu", self.on_back, size=14)

    # --- the NAME CHOOSER page ---
    def make_names_page(self):
        c = self.canvas
        self.names_title = FancyText(c, WIDTH / 2, 45, "NAME CHOOSER", 34, "names", depth=5, shadow=True)
        self.entry = tk.Entry(self.root, font=("Helvetica", 13), bg="#161622", fg="white",
                              insertbackground="white", relief="flat")
        self.entry.bind("<Return>", lambda e: self.add_name())
        c.create_window(60, 95, anchor="nw", window=self.entry, width=190, height=34, tags="names")
        self.make_button("ADD", "ADD", 260, 95, 330, 129, "names", self.add_name, size=12)
        c.create_text(60, 142, anchor="nw", text="click a name to remove it", fill="#6a6a88",
                      font=("Helvetica", 10), tags="names")
        self.result_text = FancyText(c, 525, 190, "?", 34, "names", depth=4, shadow=True,
                                     width=300, justify="center")
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
        self.result_text.set_text("?")
        self.bot.post_sync("CLEAR")

    def disarm_clear(self):
        self.clear_armed = False

    # --- multiplayer: things from Discord arrive here (checked every tick) ---
    def check_inbox(self):
        while self.updates:      # the sound updater finished downloading something
            kind, count = self.updates.popleft()
            if kind == "sounds":
                self.load_all_sounds()
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
            elif kind == "board_history":
                for content in data:
                    result = read_board(content)
                    if result:
                        self.board_update(*result)
                self.after_board_history()
            elif kind == "board":
                result = read_board(data)
                if result and self.board_update(*result):
                    save_board(self.board)
                    if self.page == "board":
                        self.refresh_board()
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
                        insertbackground="white", relief="flat", highlightthickness=0)

    def make_chat_panel(self):
        c = self.canvas
        x0, x1 = WIDTH + 10, WIDTH + CHAT_W - 10
        self.chat_rect = c.create_polygon(rounded(x0, 45, x1, 450, 20), smooth=True, fill="#10101a",
                                          outline="#333344", width=2, tags="chat")
        c.create_text(x0 + 15, 65, anchor="w", text="CHAT", fill="white", tags="chat",
                      font=("Helvetica", 16, "bold"))
        self.make_button("CHATMIN", "-", x1 - 45, 52, x1 - 10, 78, "chat", self.toggle_chat, size=14)
        if OWNER_ID and self.my_fp == OWNER_ID:      # only the owner gets this button
            self.make_button("CHATCLEAR", "CLEAR", x1 - 120, 52, x1 - 55, 78, "chat", self.clear_chat, size=10)
        c.create_text(x0 + 15, 100, anchor="w", text="your name", fill="#6a6a88",
                      font=("Helvetica", 10), tags="chat")
        self.name_entry = self.make_entry()
        self.name_entry.insert(0, self.username if self.my_fp in ROSTER else "(not approved)")
        self.name_entry.config(state="readonly", readonlybackground="#161622")   # names come from ROSTER
        c.create_polygon(rounded(x0 + 76, 86, x0 + 209, 114, 12), smooth=True, fill="#161622",
                         outline="#333344", width=1, tags="chat")
        c.create_window(x0 + 84, 90, anchor="nw", window=self.name_entry, width=117, height=20, tags="chat")
        self.make_button("COPYID", "ID", x1 - 55, 88, x1 - 10, 112, "chat", self.copy_id, size=10)
        self.chat_log = tk.Text(self.root, bg="#10101a", fg="white", font=("Helvetica", 11),
                                wrap="word", relief="flat", highlightthickness=0, padx=6, pady=4,
                                state="disabled", cursor="arrow")
        c.create_window(x0 + 8, 122, anchor="nw", window=self.chat_log, width=264, height=250, tags="chat")
        self.chat_entry = self.make_entry()
        self.chat_entry.bind("<Return>", lambda e: self.send_chat())
        c.create_polygon(rounded(x0 + 8, 382, x0 + 212, 416, 14), smooth=True, fill="#161622",
                         outline="#333344", width=1, tags="chat")
        c.create_window(x0 + 18, 387, anchor="nw", window=self.chat_entry, width=184, height=24, tags="chat")
        self.make_button("SEND", "SEND", x1 - 62, 384, x1 - 8, 414, "chat", self.send_chat, size=10)
        c.create_text((x0 + x1) / 2, 435, text="suggestions welcome!", fill="#6a6a88",
                      font=("Helvetica", 10), tags="chat")
        # the little tab on the side that opens and closes the chat
        self.make_button("CHATICON", "CHAT", WIDTH - 80, 215, WIDTH - 8, 251, "chaticon",
                         self.toggle_chat, size=10)
        self.make_button("MUTE", "", 10, 442, 48, 474, "chaticon", self.toggle_mute)   # music on/off
        icon = {"body": c.create_polygon(0, 0, 0, 0, 0, 0, fill="", outline="", tags="chaticon"),
                "wave1": c.create_arc(0, 0, 1, 1, start=-50, extent=100, style="arc", outline="", tags="chaticon"),
                "wave2": c.create_arc(0, 0, 1, 1, start=-50, extent=100, style="arc", outline="", tags="chaticon"),
                "x1": c.create_line(0, 0, 0, 0, fill="", capstyle="round", tags="chaticon"),
                "x2": c.create_line(0, 0, 0, 0, fill="", capstyle="round", tags="chaticon")}
        self.buttons["MUTE"]["icon"] = icon
        for item in icon.values():
            self.bind_button(item, "MUTE")
        c.itemconfig("chat", state="hidden")

    def toggle_chat(self):
        self.chat_open = not self.chat_open
        cw = self.canvas.winfo_width()
        if self.chat_open:
            dw = max(0, WIDTH + CHAT_W - cw)           # widen the window only if it is too narrow
        else:
            dw = -min(self.chat_extra, max(0, cw - WIDTH))
            self.root.minsize(WIDTH, HEIGHT)           # let it shrink back
        self.chat_anim = {"t": 0, "from": self.chat_frac, "to": 1.0 if self.chat_open else 0.0,
                          "w0": cw, "dw": dw, "extra0": self.chat_extra}
        play(self.chat_open_sound if self.chat_open else self.chat_close_sound)
        if self.chat_open:
            self.canvas.itemconfig("chat", state="normal")     # it slides out as the window widens
        if self.chat_open:
            self.unread = 0
            self.update_chat_icon()
            self.chat_entry.focus_set()
        else:
            self.canvas.focus_set()
        self.clear_hover()

    def update_chat_icon(self):
        label = f"CHAT ({self.unread})" if self.unread else "CHAT"
        self.buttons["CHATICON"]["text"].set_text(label)

    def wipe_chat_log(self):
        log = self.chat_log
        log.config(state="normal")
        log.delete("1.0", "end")
        log.tag_config("note", foreground=THEME["muted"])
        log.insert("end", "chat cleared\n", "note")
        log.config(state="disabled")

    def clear_chat(self):
        if not (OWNER_ID and self.my_fp == OWNER_ID):
            return
        if not self.clear_chat_armed:    # ask twice, because this can't be undone
            self.clear_chat_armed = True
            self.canvas.itemconfig(self.status, text="Click CLEAR again to delete the ENTIRE chat for everyone")
            self.root.after(3000, self.disarm_clear_chat)
            return
        self.clear_chat_armed = False
        message_id = "%08x" % _RANDOM.randrange(16 ** 8)
        stamp = int(time.time())
        e, s = sign(self.secret, f"CLEAR|{message_id}|{stamp}")
        marker = f"GESTER-CLEAR {self.public:x}:{e:x}:{s:x}:{message_id}:{stamp}"
        if self.bot.clear_chat_channel(marker):
            self.seen_ids.add(message_id)
            self.wipe_chat_log()
            self.canvas.itemconfig(self.status, text="Clearing the chat for everyone...")
        else:
            self.canvas.itemconfig(self.status, text="Can't clear: bot isn't connected")

    def disarm_clear_chat(self):
        self.clear_chat_armed = False

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
        if content.startswith("GESTER-CLEAR "):
            marker_id = None if quiet else read_clear(content)   # old ones in history are ignored
            if marker_id and marker_id not in self.seen_ids:
                self.seen_ids.add(marker_id)
                self.wipe_chat_log()
                self.unread = 0
                self.update_chat_icon()
            return
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

    # --- the LEADERBOARD page ---
    def make_board_page(self):
        c = self.canvas
        self.board_title = FancyText(c, WIDTH / 2, 45, "MILLOKU LEADERBOARD", 30, "board",
                                     depth=4, shadow=True)
        self.board_note = c.create_text(WIDTH / 2, 82, text="", fill="#8888aa",
                                        font=("Helvetica", 11), tags="board")
        self.board_rows = []
        for i in range(10):
            y = 118 + i * 26
            self.board_rows.append({
                "rank": c.create_text(210, y, anchor="e", text="", fill="#8888aa",
                                      font=("Helvetica", 14, "bold"), tags="board"),
                "name": c.create_text(232, y, anchor="w", text="", fill="white",
                                      font=("Helvetica", 14, "bold"), tags="board"),
                "level": c.create_text(515, y, anchor="e", text="", fill="#8888aa",
                                       font=("Helvetica", 13), tags="board")})
        self.make_button("BOARD_BACK", "BACK", 260, 385, 460, 430, "board",
                         lambda: self.show_page("menu"), size=14)

    def open_board(self):
        self.show_page("board")
        self.refresh_board()
        if not BOARD_CHANNEL_ID:
            self.canvas.itemconfig(self.status, text="Leaderboard isn't shared yet (BOARD_CHANNEL_ID)")

    def board_update(self, who, level, stamp):
        """Keep each player's best result. Returns True if the board changed."""
        old = self.board.get(who)
        if old is None or level > old[0] or (level == old[0] and stamp < old[1]):
            self.board[who] = [level, stamp]
            return True
        return False

    def refresh_board(self):
        c = self.canvas
        # most levels first; if tied, whoever got there first
        entries = sorted(((level, stamp, who) for who, (level, stamp) in self.board.items()
                          if who in ROSTER and level > 0), key=lambda t: (-t[0], t[1]))
        c.itemconfig(self.board_note, text="" if entries else "No scores yet. Beat a Milloku level to get on the board!")
        for i, row in enumerate(self.board_rows):
            if i < len(entries):
                level, stamp, who = entries[i]
                c.itemconfig(row["rank"], text=str(i + 1))
                c.itemconfig(row["name"], text=ROSTER[who] + ("  (you)" if who == self.my_fp else ""))
                c.itemconfig(row["level"], text="ALL 100 DONE!" if level >= 100 else f"level {level} / 100")
            else:
                for part in row.values():
                    c.itemconfig(part, text="")

    def after_board_history(self):
        save_board(self.board)
        if self.page == "board":
            self.refresh_board()
        if self.su_done > self.board.get(self.my_fp, [0, 0])[0]:
            self.post_score()      # share progress the board doesn't know about yet

    def post_score(self):
        if self.my_fp not in ROSTER or not BOARD_CHANNEL_ID or self.su_done <= 0:
            return
        stamp = int(time.time())
        e, s = sign(self.secret, f"BOARD|{self.su_done}|{stamp}")
        if self.bot.post(f"GESTER-BOARD {self.public:x}:{e:x}:{s:x}:{self.su_done}:{stamp}", BOARD_CHANNEL_ID):
            self.board_update(self.my_fp, self.su_done, stamp)
            save_board(self.board)
            if self.page == "board":
                self.refresh_board()

    # --- the THEMES page ---
    def make_themes_page(self):
        c = self.canvas
        self.themes_title = FancyText(c, WIDTH / 2, 55, "THEMES", 40, "themes", depth=5, shadow=True)
        for i, name in enumerate(THEMES):
            y1 = 115 + i * 62
            key = f"THEME_{name}"
            self.make_button(key, name, 190, y1, 530, y1 + 52, "themes",
                             lambda n=name: self.set_theme(n))
            colors = THEMES[name]["swatches"]
            size, sx, sy = 30, 480, y1 + 11      # ONE small square, striped with all of the theme's colors
            parts = [c.create_rectangle(sx + round(j * size / len(colors)), sy,
                                        sx + round((j + 1) * size / len(colors)), sy + size,
                                        fill=color, outline="", tags="themes")
                     for j, color in enumerate(colors)]
            parts.append(c.create_rectangle(sx, sy, sx + size, sy + size, fill="", outline="#d0d0e0",
                                            width=2, tags="themes"))
            for part in parts:
                self.bind_button(part, key)
        self.make_button("THEMES_BACK", "BACK", 260, 385, 460, 430, "themes",
                         lambda: self.show_page("menu"), size=14)

    def update_theme_labels(self):
        for name in THEMES:
            label = f"{name}   (active)" if name == self.theme_name else name
            self.buttons[f"THEME_{name}"]["text"].set_text(label)

    def set_theme(self, name):
        old = dict(THEME)
        THEME.clear()
        THEME.update(THEMES[name])
        self.theme_name = name
        self.apply_theme(old, THEMES[name])
        for jester in self.jesters:      # jesters, minions, cats or aliens
            jester.set_style(THEME["critter"])
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
        self.su_title = FancyText(c, SU_X, 38, "MILLOKU", 26, "sudoku", depth=4, shadow=True, anchor="w")
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
        self.buttons["SU_HINT"]["text"].set_text(f"HINT ({self.su_hints})")

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
            self.post_score()
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
            self.result_text.set_text(random.choice(names))
            play(self.hover_sound)
            delay = int(40 + i * i * 0.35)   # starts fast, slows down
            self.root.after(delay, self.spin_step, i + 1, total, names, winner)
        else:
            self.result_text.set_text(winner)
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
        """A rounded, glossy button: shadow, glow rings, body, shine, edge light, sweep and 3D label."""
        c = self.canvas
        radius = min(18, (y2 - y1) / 2.2)
        base = rounded(x1, y1, x2, y2, radius)
        shadow = c.create_polygon(base, smooth=True, fill="#000000", outline="", tags=page)
        glow = [c.create_polygon(base, smooth=True, fill="", outline="", width=2, tags=page) for _ in range(2)]
        box = c.create_polygon(base, smooth=True, fill="#161622", outline="#333344", width=3, tags=page)
        gloss = c.create_polygon(base, smooth=True, fill="#1e1e30", outline="", tags=page)
        edge = c.create_line(x1 + radius, y1 + 4, x2 - radius, y1 + 4, fill="#444460", width=2,
                             capstyle="round", tags=page)
        sweep = c.create_polygon(0, 0, 0, 0, 0, 0, fill="", outline="", tags=page)
        text = FancyText(c, (x1 + x2) / 2, (y1 + y2) / 2, label, size, page, depth=2)
        items = [shadow, *glow, box, gloss, edge, sweep] + text.ids
        self.buttons[key] = {"box": box, "action": action, "text": text, "page": page,
                             "shadow": shadow, "glow": glow, "gloss": gloss, "edge": edge,
                             "sweep": sweep, "geom": (x1, y1, x2, y2, radius, size),
                             "scale": 1.0, "kick": 0.0, "flash": 0.0, "shown": 0.0,
                             "sig": None, "since": 0, "items": items}
        for item in items:
            self.bind_button(item, key)

    def animate_buttons(self):
        """Hover = grow, glow and shine. Click = pop bigger and flash. Only redraws what changed."""
        for key, b in self.buttons.items():
            page = b["page"]
            if not (page == self.page or page == "chaticon" or (page == "chat" and self.chat_open)):
                continue
            hovered = key == self.hovered
            b["kick"] *= 0.8
            b["flash"] = b["flash"] * 0.82 if b["flash"] > 0.03 else 0.0
            b["scale"] += ((1.05 if hovered else 1.0) - b["scale"]) * 0.3
            scale = b["scale"] + b["kick"]
            signature = (hovered, self.theme_name, self.unread if key == "CHATICON" else 0,
                         self.muted if key == "MUTE" else 0)
            if hovered or b["flash"] or signature != b["sig"] or abs(scale - b["shown"]) > 0.002:
                self.paint_button(key, b, hovered, scale)
                b["sig"], b["shown"] = signature, scale

    def paint_button(self, key, b, hovered, scale):
        c = self.canvas
        x1, y1, x2, y2, radius, size = b["geom"]
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        half_w, half_h, r = (x2 - x1) / 2 * scale, (y2 - y1) / 2 * scale, radius * scale
        left, top, right, bottom = cx - half_w, cy - half_h, cx + half_w, cy + half_h
        accent = rainbow(self.hue * 3)
        fill = THEME["panel_hi"] if hovered else THEME["panel"]
        if b["flash"]:
            fill = mix(fill, accent, b["flash"] * 0.5)
        c.coords(b["shadow"], *rounded(left + 2, top + 5, right + 2, bottom + 5, r))
        c.itemconfig(b["shadow"], fill=mix(THEME["bg"], "#000000", 0.55))
        for n, ring in enumerate(b["glow"]):          # soft glow rings, only while hovered
            if hovered:
                grow = 3 + n * 3
                c.coords(ring, *rounded(left - grow, top - grow, right + grow, bottom + grow, r + grow))
                c.itemconfig(ring, outline=mix(THEME["bg"], accent, 0.6 - 0.3 * n))
            else:
                c.itemconfig(ring, outline="")
        c.coords(b["box"], *rounded(left, top, right, bottom, r))
        c.itemconfig(b["box"], fill=fill, outline=accent if hovered else THEME["border"])
        c.coords(b["gloss"], *rounded(left + 5, top + 4, right - 5, top + (bottom - top) * 0.5, r * 0.7))
        c.itemconfig(b["gloss"], fill=mix(fill, "#ffffff", 0.16 if hovered else 0.09))
        c.coords(b["edge"], left + r, top + 4, right - r, top + 4)
        c.itemconfig(b["edge"], fill=mix(fill, "#ffffff", 0.4))
        if hovered:                                   # a bright band sweeps across the button
            t = ((self.frame - b["since"]) % 40) / 40
            band, slant = (right - left) * 0.16, (bottom - top) * 0.45
            start = left - band + t * ((right - left) + 2 * band)
            low, high = left + r * 0.6, right - r * 0.6
            xs = [min(high, max(low, v)) for v in (start, start + band, start + band - slant, start - slant)]
            c.coords(b["sweep"], xs[0], top + 3, xs[1], top + 3, xs[2], bottom - 3, xs[3], bottom - 3)
            c.itemconfig(b["sweep"], fill=mix(fill, "#ffffff", 0.28))
        else:
            c.itemconfig(b["sweep"], fill="")
        text = b["text"]
        text.set_size(size * scale)
        text.move(cx, cy)
        if key == "CHATICON" and self.unread:
            face = rainbow(self.hue * 5)
        elif hovered:
            face = mix(THEME["text"], accent, 0.35)
        else:
            face = THEME["text"]
        text.paint(face)
        if b.get("icon"):
            self.paint_icon(b["icon"], cx, cy, scale, face)

    def paint_icon(self, icon, cx, cy, scale, face):
        """The speaker: sound waves when music is on, a red X when it is muted."""
        c = self.canvas

        def pt(x, y):
            return cx + (x - 1) * scale, cy + y * scale
        body = [v for p in ((-9, -4), (-5, -4), (1, -9), (1, 9), (-5, 4), (-9, 4)) for v in pt(*p)]
        c.coords(icon["body"], *body)
        if self.muted:
            c.itemconfig(icon["body"], fill=THEME["muted"])
            for wave in ("wave1", "wave2"):
                c.itemconfig(icon[wave], outline="")
            c.coords(icon["x1"], *pt(5, -5), *pt(13, 3))
            c.coords(icon["x2"], *pt(13, -5), *pt(5, 3))
            for line in ("x1", "x2"):
                c.itemconfig(icon[line], fill="#ff5a5a", width=max(2, 2.4 * scale))
        else:
            c.itemconfig(icon["body"], fill=face)
            for wave, radius in (("wave1", 6), ("wave2", 10)):
                x1, y1 = pt(1 - radius, -radius)
                x2, y2 = pt(1 + radius, radius)
                c.coords(icon[wave], x1, y1, x2, y2)
                c.itemconfig(icon[wave], outline=face if radius == 6 else mix(face, THEME["bg"], 0.35),
                             width=max(2, 2 * scale))
            for line in ("x1", "x2"):
                c.itemconfig(icon[line], fill="")

    def bind_button(self, item, key):
        self.canvas.tag_bind(item, "<Enter>", lambda e: self.on_hover(key))
        self.canvas.tag_bind(item, "<Leave>", lambda e: self.on_leave())
        self.canvas.tag_bind(item, "<Button-1>", lambda e: self.on_click(e, key))

    def show_page(self, name, animate=True):
        """Change pages with a zipper wipe (or instantly with animate=False)."""
        if self.transition:                       # already wiping: just aim at the newest page
            self.transition["page"] = name
            if self.transition["applied"]:
                self._apply_page(name)
            return
        if not animate or name == self.page:
            self._apply_page(name)
            return
        depth = {"home": 0, "menu": 1}
        self.transition = {"t": 0, "page": name, "applied": False,
                           "forward": depth.get(name, 2) > depth.get(self.page, 2)}
        self.canvas.tag_raise("wipe")
        play(self.whoosh_sound)

    def _apply_page(self, name):
        """Show one page and hide the others."""
        self.page = name
        for page in ("home", "menu", "names", "sudoku", "themes", "board"):
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
            self.buttons[key]["since"] = self.frame
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
        self.ripples.append([self.canvas.canvasx(event.x), self.canvas.canvasy(event.y), 5])
        self.buttons[key]["kick"] = 0.16     # pops bigger
        self.buttons[key]["flash"] = 1.0     # and flashes
        self.buttons[key]["action"]()

    def on_jester_click(self, event, jester):
        play(self.jester_sound)
        self.ripples.append([self.canvas.canvasx(event.x), self.canvas.canvasy(event.y), 5])
        jester.poke()
        self.canvas.itemconfig(self.status, text=CRITTER_SAYS[THEME["critter"]])

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
                self.music_mode, self.music_vol = "party", 0.7
                message = "PARTY MODE ON!"
            elif not SOUND_ON:
                message = "PARTY MODE ON! (install pygame for music)"
            else:
                message = f"PARTY MODE ON! (put {PARTY_SONG} next to gester.py)"
        else:
            stop_song()
            self.start_menu_music()
            message = "Party mode off"
        self.canvas.itemconfig(self.status, text=message)

    def quit_app(self):
        stop_song()
        self.root.destroy()

    # --- the animation loop: runs about 33 times per second ---
    def tick(self):
        self.frame += 1
        self.hue += self.speed
        if not self.intro_done:
            self.step_intro()
        if self.transition:
            self.step_transition()
        if self.chat_anim:
            self.step_chat_anim()
        self.update_music()

        # rainbow bar along the top
        first = max(0, int((VIEW["x0"] + BAR_PAD) // BAR_W))        # only color the pieces you can see
        last = min(len(self.bar), int((VIEW["x1"] + BAR_PAD) // BAR_W) + 2)
        for i in range(first, last):
            self.canvas.itemconfig(self.bar[i], fill=rainbow(self.hue + i * 0.012))

        # 3D titles: rainbow faces, with a shine that sweeps across the big GESTER letters
        if self.page == "home":
            sweep = (self.frame * 0.09) % (len(self.letters) + 5) - 2.5
            for i, letter in enumerate(self.letters):
                shine = max(0.0, 1 - abs(i - sweep) / 1.4)
                face = mix(rainbow(self.hue * 2 + i * 0.12), "#ffffff", 0.75 * shine)
                bob = math.sin(self.frame * 0.1 + i * 0.8) * (10 if self.party else 4)
                drop = 0
                if not self.intro_done:     # intro: the letters fall in and bounce
                    drop = -330 * (1 - bounce(min(1.0, max(0.0, (self.intro_frame - i * 5) / 24))))
                letter.move(WIDTH / 2 + (i - 2.5) * 72, 110 + bob + drop)
                letter.paint(face)
        else:
            for title in self.page_titles.get(self.page, []):
                title.paint(rainbow(self.hue * 2))
        if self.page == "names":
            self.result_text.paint(rainbow(self.hue * 4))
        if self.page == "board":      # the top three glow
            for i, row in enumerate(self.board_rows[:3]):
                if self.canvas.itemcget(row["name"], "text"):
                    for part in ("rank", "name"):
                        self.canvas.itemconfig(row[part], fill=rainbow(self.hue * 2 + i * 0.15))

        self.animate_buttons()

        # sudoku page: rainbow title and lines, glowing selected square, victory rainbow
        if self.page == "sudoku":
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

        # jesters wander around (faster in Party Mode)
        for jester in self.jesters:
            jester.update(self.hue, 2.5 if self.party else 1, self.frame)

        # floating particles
        for p in self.particles:
            p["y"] -= p["speed"] * (3 if self.party else 1)
            if (p["y"] < VIEW["y0"] - 10 or p["y"] > VIEW["y1"] + 10
                    or p["x"] > VIEW["x1"] or p["x"] < VIEW["x0"] - 10):
                p["y"] = VIEW["y1"] + 10
                p["x"] = random.uniform(VIEW["x0"], VIEW["x1"])
            self.canvas.coords(p["id"], p["x"], p["y"], p["x"] + p["size"], p["y"] + p["size"])
            self.canvas.itemconfig(p["id"], fill=rainbow(self.hue + p["x"] / WIDTH, 0.6, 0.9))

        # party mode sprinkles random ripples
        if self.party and self.frame % 12 == 0:
            self.ripples.append([random.randint(int(VIEW["x0"]), int(VIEW["x1"])),
                                 random.randint(int(VIEW["y0"]) + 200, int(VIEW["y1"])), 5])

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
