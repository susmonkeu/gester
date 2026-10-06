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
VERSION = "1.13.0"          # change this each update so you can see it worked

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
    pygame.mixer.set_num_channels(24)
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


def read_leaf_score(content):
    """Check a Leaf Sweep leaderboard message. Returns (id, level, tenths_of_a_second) or None if fake."""
    try:
        if not content.startswith("GESTER-LEAF "):
            return None
        public_hex, e_hex, s_hex, level, tenths, stamp = content[12:].split(":")
        public = int(public_hex, 16)
        who = fingerprint(public)
        level, tenths, stamp = int(level), int(tenths), int(stamp)
        if who not in ROSTER or not 1 <= level <= LEAF_LEVELS or not 30 <= tenths <= 36000:
            return None
        if not verify(public, f"LEAF|{level}|{tenths}|{stamp}", int(e_hex, 16), int(s_hex, 16)):
            return None
        return who, level, tenths
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


LEAF_BOARD_FILE = os.path.join(HERE, "leafboard.json")


def load_leaf_board():
    """Best Leaf Sweep times {id: {level: tenths of a second}}."""
    try:
        with open(LEAF_BOARD_FILE) as f:
            return {who: {int(k): int(v) for k, v in times.items()} for who, times in json.load(f).items()}
    except Exception:
        return {}


def save_leaf_board(board):
    try:
        with open(LEAF_BOARD_FILE, "w") as f:
            json.dump({who: {str(k): v for k, v in times.items()} for who, times in board.items()}, f)
    except OSError:
        pass


def save_board(board):
    try:
        with open(BOARD_FILE, "w") as f:
            json.dump(board, f)
    except OSError:
        pass


# ---------- LEAF SWEEP: levels, saving and sounds ----------
LEAF_FILE = os.path.join(HERE, "leafsweep.json")
LEAF_LEVELS = 50
PORTAL_COLORS = ["#39d0ff", "#ff5fd2"]
# every 10 levels is a new place: (name, color of its light, the floating specks it has)
LEAF_WORLDS = [("MEADOW", "#5fb34a", "dust"), ("SUNSET GROVE", "#e07a2e", "petal"),
               ("MOONLIT WOODS", "#5468d8", "firefly"), ("FROZEN HOLLOW", "#8fd3f0", "snow"),
               ("EMBER RIDGE", "#e0442a", "ember")]
LF_X0, LF_Y0, LF_X1, LF_Y1 = 20, 70, 628, 434      # the playing field
LEAF_COLORS = ["#d9381e", "#e8641b", "#f2a31b", "#c8b22a", "#a8531f", "#b5302a", "#e87f24", "#8f6a1e"]
GOLD_LEAF = "#ffd23f"
# the outline of one leaf (tip on the right); the tip is listed twice to keep it pointy
LEAF_SHAPE = [(1.0, 0), (1.0, 0), (0.5, 0.42), (-0.1, 0.55), (-0.75, 0.32), (-1.0, 0),
              (-0.75, -0.32), (-0.1, -0.55), (0.5, -0.42)]
LEAF_HINTS = {1: "Move your mouse to sweep the leaves into the bin!",
              2: "Golden leaves are worth bonus points. Sweep leaves fast in a row for combos!",
              4: "Rocks! Leaves bounce off them.",
              6: "Wind! Watch for the warning at the top.",
              10: "The bin is on the move!",
              31: "Mud puddles! Leaves get stuck, so sweep them out slowly.",
              35: "Bouncy mushrooms! They kick leaves away.",
              39: "Air vents! They blow leaves along the arrows.",
              43: "Portals! A leaf that goes in one comes out the other.",
              50: "The final level. Good luck!"}


def load_leaf_progress():
    """(levels cleared, {level: best stars}) from the save file."""
    try:
        with open(LEAF_FILE) as f:
            data = json.load(f)
        done = max(0, min(LEAF_LEVELS, int(data["completed"])))
        stars = {int(k): max(1, min(3, int(v))) for k, v in data.get("stars", {}).items()}
        return done, stars
    except Exception:
        return 0, {}


def save_leaf_progress(done, stars):
    try:
        with open(LEAF_FILE, "w") as f:
            json.dump({"completed": done, "stars": {str(k): v for k, v in stars.items()}}, f)
    except OSError:
        pass


def leaf_level(level):
    """Everything about a level. The same level number always gives the same level."""
    rng = random.Random(level * 7331 + 11)
    count = min(80, 10 + int(level * 2.4))
    if level > 30:                         # the bonus levels have fewer leaves but more obstacles
        count = 50 + int((level - 30) * 1.5)
    golden = min(6, 1 + level // 6)
    bw = max(76, int(114 - level * 1.3))
    bh = 84
    moving = level >= 10
    bx, by = LF_X1 - bw - 8, LF_Y1 - bh - 8
    # the part of the field that must stay clear (the bin, or the whole bottom strip when it moves)
    keep_x, keep_y = (LF_X0 if moving else bx - 30), by - 28
    rocks = []
    for _ in range(max(0, min(4 if level > 30 else 7, (level - 1) // 3))):
        for _try in range(80):
            rr = rng.randint(14, 22)
            x, y = rng.uniform(LF_X0 + 60, LF_X1 - 60), rng.uniform(LF_Y0 + 60, LF_Y1 - 60)
            if x + rr > keep_x and y + rr > keep_y:
                continue
            if all(math.hypot(x - ox, y - oy) > rr + orr + 50 for ox, oy, orr in rocks):
                rocks.append((x, y, rr))
                break
    mud, bumpers, vents, portals = [], [], [], []
    if level > 30:
        want = (0 if level < 43 else (1 if level < 47 else 2),      # portal pairs
                0 if level < 39 else min(4, 1 + (level - 39) // 3),  # vents
                0 if level < 35 else min(5, 1 + (level - 35) // 4),  # mushrooms
                min(5, 2 + (level - 31) // 5))                       # mud puddles
        for attempt in range(60):          # keep rolling until everything fits (its own dice, so levels 1-30 never change)
            orng = random.Random(level * 9173 + 5 + attempt * 101)
            solids = list(rocks)
            mud, bumpers, vents, portals = [], [], [], []

            def place(rad, gap=14, far_from=None):
                for _try in range(300):
                    x, y = orng.uniform(LF_X0 + 45, LF_X1 - 45), orng.uniform(LF_Y0 + 45, LF_Y1 - 45)
                    if x + rad > keep_x and y + rad > keep_y:
                        continue
                    if far_from and math.hypot(x - far_from[0], y - far_from[1]) < 190:
                        continue
                    if all(math.hypot(x - ox, y - oy) > rad + orad + gap for ox, oy, orad in solids):
                        solids.append((x, y, rad))
                        return x, y
                return None
            for _ in range(want[0]):
                first = place(20)
                second = place(20, far_from=first) if first else None
                if first and second:
                    portals.append((first, second, len(portals)))
            for _ in range(want[1]):
                dx, dy = orng.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
                w, h = (118, 48) if dx else (48, 118)
                spot = place(50)
                if spot:
                    vents.append((spot[0] - w / 2, spot[1] - h / 2, spot[0] + w / 2, spot[1] + h / 2, dx, dy))
            for _ in range(want[2]):
                rr = orng.randint(15, 19)
                spot = place(rr)
                if spot:
                    bumpers.append((spot[0], spot[1], rr))
            for _ in range(want[3]):
                rx, ry = orng.randint(32, 50), orng.randint(24, 34)
                spot = place(max(rx, ry) * 0.75, gap=4)
                if spot:
                    mud.append((spot[0], spot[1], rx, ry))
            if (len(portals), len(vents), len(bumpers), len(mud)) == want:
                break
    avoid = rocks + bumpers + [(p[0][0], p[0][1], 20) for p in portals] + [(p[1][0], p[1][1], 20) for p in portals]
    gold_ids = set(rng.sample(range(count), min(golden, count)))
    leaves = []
    for i in range(count):
        for _try in range(100):
            x, y = rng.uniform(LF_X0 + 22, LF_X1 - 22), rng.uniform(LF_Y0 + 22, LF_Y1 - 22)
            if x > keep_x - 10 and y > keep_y - 10:
                continue
            if any(math.hypot(x - rx, y - ry) < rr + 22 for rx, ry, rr in avoid):
                continue
            break
        leaves.append((x, y, rng.uniform(9.0, 13.0), rng.randrange(len(LEAF_COLORS)),
                       i in gold_ids, rng.uniform(0, math.tau)))
    wind = None
    if level >= 6:
        wind = {"power": min(1.0, 0.45 + (level - 6) * 0.025),          # push per frame at the peak of a gust
                "wait": int(max(5.0, 12 - (level - 6) * 0.25) * 30)}    # frames between gusts
    return {"count": count, "leaves": leaves, "rocks": rocks, "bin": (bx, by, bw, bh),
            "moving": moving, "bin_speed": 0.8 + max(0, level - 10) * 0.07, "wind": wind,
            "mud": mud, "bumpers": bumpers, "vents": vents, "portals": portals,
            "par": (10 + count * 1.1) * (1.3 if level > 30 else 1.0)}


def format_tenths(tenths):
    return f"{tenths // 600}:{tenths % 600 / 10:04.1f}"


def leaf_stars(par, seconds):
    return 3 if seconds <= par else (2 if seconds <= par * 1.8 else 1)


def star_points(cx, cy, r):
    pts = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        radius = r if i % 2 == 0 else r * 0.45
        pts += [cx + math.cos(angle) * radius, cy + math.sin(angle) * radius]
    return pts


def play_at(sound, volume):
    """Play a sound at a chosen volume (so quick sweeps sound stronger than slow ones)."""
    if sound:
        channel = sound.play()
        if channel:
            channel.set_volume(max(0.0, min(1.0, volume)))


def write_samples(path, samples, peak=0.85, rate=22050):
    top = max(1e-9, max(abs(v) for v in samples))
    scale = peak / top if peak else 1.0
    data = bytearray()
    for v in samples:
        data += int(max(-1.0, min(1.0, v * scale)) * 32000).to_bytes(2, "little", signed=True)
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(bytes(data))


def noise_band(ms, low, high, seed, power=1.2, crackle=0.0):
    """A swish of filtered noise (the sound of leaves and wind)."""
    rate = 22050
    rnd = random.Random(seed)
    count = int(rate * ms / 1000)
    a_hi = 1 - math.exp(-2 * math.pi * high / rate)
    a_lo = 1 - math.exp(-2 * math.pi * low / rate)
    lp_hi = lp_lo = 0.0
    gain = 1.0
    out = []
    for i in range(count):
        if i % 110 == 0:
            gain = 1.0 - crackle * rnd.random()      # crunchy flutter
        x = rnd.uniform(-1, 1)
        lp_hi += a_hi * (x - lp_hi)
        lp_lo += a_lo * (x - lp_lo)
        out.append((lp_hi - lp_lo) * math.sin(math.pi * i / count) ** power * gain)
    return out


def tone_events(events, ms):
    """Soft bell-like notes. An event is (start_ms, hz, length_ms, volume, decay)."""
    rate = 22050
    out = [0.0] * int(rate * ms / 1000)
    for start_ms, hz, length_ms, vol, decay in events:
        first = int(rate * start_ms / 1000)
        for i in range(int(rate * length_ms / 1000)):
            if first + i >= len(out):
                break
            t = i / rate
            out[first + i] += vol * (math.sin(2 * math.pi * hz * t) * math.exp(-t * decay)
                                     + 0.3 * math.sin(4 * math.pi * hz * t) * math.exp(-t * decay * 1.7))
    return out


def leaf_pop(hz):
    """The 'plop' of a leaf landing in the bin: a soft thud and a bright note."""
    notes = tone_events([(0, hz, 220, 0.6, 16)], 220)
    for i in range(len(notes)):
        t = i / 22050
        notes[i] += 0.55 * math.sin(2 * math.pi * 150 * t) * math.exp(-t * 42)
    return notes


LEAF_SWEEP_SOUND = "leaf_sweep.wav"        # your own sweeping sound (optional)
LEAF_COLLECT_SOUND = "leaf_collect.wav"    # your own "leaf in the bin" sound (optional)
LEAF_GOLD_SOUND = "leaf_gold.wav"
LEAF_WIN_SOUND = "leaf_win.wav"
LEAF_GUST_SOUND = "leaf_gust.wav"
LEAF_BUMP_SOUND = "leaf_bump.wav"
LEAF_PORTAL_SOUND = "leaf_portal.wav"
LEAF_MUD_SOUND = "leaf_mud.wav"


def tone_sweep(f0, f1, ms, decay=6.0):
    """A note that glides from one pitch to another (boing, whoosh)."""
    rate = 22050
    count = int(rate * ms / 1000)
    out, phase = [], 0.0
    for i in range(count):
        t = i / rate
        hz = f0 + (f1 - f0) * i / count
        phase += 2 * math.pi * hz / rate
        out.append(math.sin(phase) * math.exp(-t * decay) * min(1.0, i / 120))
    return out


def make_leaf_sounds():
    """Make built-in leaf sounds for any you haven't provided."""
    jobs = {}
    for i, (ms, lo, hi, seed) in enumerate([(170, 500, 3400, 1), (200, 700, 4300, 2), (150, 400, 2900, 3)], 1):
        jobs[f"leaf_sweep_{i}.wav"] = lambda ms=ms, lo=lo, hi=hi, seed=seed: noise_band(ms, lo, hi, seed, 1.2, 0.7)
    for i, hz in enumerate([523, 587, 659, 784, 880, 1047], 1):     # each combo step is a higher note
        jobs[f"leaf_collect_{i}.wav"] = lambda hz=hz: leaf_pop(hz)
    jobs[LEAF_GOLD_SOUND] = lambda: tone_events([(0, 1568, 300, 0.5, 9), (70, 2093, 330, 0.5, 9),
                                                  (140, 2637, 360, 0.4, 9)], 520)
    jobs[LEAF_WIN_SOUND] = lambda: tone_events([(0, 523, 300, 0.45, 8), (110, 659, 300, 0.45, 8),
                                                (220, 784, 300, 0.45, 8), (330, 1047, 1000, 0.5, 4),
                                                (330, 1319, 1000, 0.3, 4), (330, 1568, 1000, 0.25, 4)], 1400)
    jobs[LEAF_GUST_SOUND] = lambda: noise_band(1000, 80, 700, 9, 1.0, 0.2)
    jobs[LEAF_BUMP_SOUND] = lambda: tone_sweep(160, 620, 190, 9)
    jobs[LEAF_PORTAL_SOUND] = lambda: [a + b * 0.5 for a, b in zip(tone_sweep(1100, 260, 300, 7),
                                                                   noise_band(300, 600, 3000, 4, 1.0, 0.1))]
    jobs[LEAF_MUD_SOUND] = lambda: noise_band(200, 60, 520, 5, 1.0, 0.6)
    for name, make in jobs.items():
        if find_file(name) is None:
            try:
                os.makedirs(DEFAULT_DIR, exist_ok=True)
                write_samples(os.path.join(DEFAULT_DIR, name), make())
            except Exception:
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
                found = [m.content async for m in channel.history(limit=600)]
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
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<Leave>", lambda e: setattr(self, "pointer", None))

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
        self.lboard = load_leaf_board()   # Leaf Sweep leaderboard: {id: {level: best time}}
        self.lboard_server = {}           # what Discord has told us (so we can re-share offline wins)
        self.board_tab = "milloku"
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
        self.lf_done, self.lf_stars = load_leaf_progress()    # Leaf Sweep progress
        self.lf_level = 1
        self.lf = None                   # the level being played
        self.lf_overlay = False
        self.lf_cursor_hidden = False
        self.leaf_win_center = (LF_X0 + LF_X1) / 2
        self.pointer = None              # where the mouse is, in page coordinates

        make_default_sounds()
        make_menu_music()
        make_leaf_sounds()
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
        self.make_leaf_page()
        self.make_chat_panel()
        self.make_wipe_bars()
        self.page_titles = {"menu": [self.options_title], "names": [self.names_title],
                            "sudoku": [self.su_title], "themes": [self.themes_title],
                            "board": [self.board_title], "leaves": [self.leaf_title]}

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
        custom = load_sound(LEAF_SWEEP_SOUND, 0.8)             # your own file wins over the built-in ones
        self.leaf_sweeps = [custom] if custom else [load_sound(f"leaf_sweep_{i}.wav", 0.8) for i in (1, 2, 3)]
        custom = load_sound(LEAF_COLLECT_SOUND, 0.9)
        self.leaf_collects = [custom] if custom else [load_sound(f"leaf_collect_{i}.wav", 0.9) for i in range(1, 7)]
        self.leaf_gold_sound = load_sound(LEAF_GOLD_SOUND, 0.8)
        self.leaf_win_sound = load_sound(LEAF_WIN_SOUND, 0.9)
        self.leaf_gust_sound = load_sound(LEAF_GUST_SOUND, 0.7)
        self.leaf_bump_sound = load_sound(LEAF_BUMP_SOUND, 0.8)
        self.leaf_portal_sound = load_sound(LEAF_PORTAL_SOUND, 0.7)
        self.leaf_mud_sound = load_sound(LEAF_MUD_SOUND, 0.7)

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
    def on_motion(self, event):
        self.pointer = (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))

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
                 ("LEAF SWEEP", self.open_leaves),
                 ("THEMES", lambda: self.show_page("themes"))]
        for i, (label, action) in enumerate(tools):
            y1 = 102 + i * 56
            self.make_button(label, label, 210, y1, 510, y1 + 46, "menu", action)
        self.make_button("BACK", "BACK", 260, 392, 460, 436, "menu", self.on_back, size=14)

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
                    leaf = read_leaf_score(content)
                    if leaf:
                        self.leaf_board_update(*leaf, server=True)
                self.after_board_history()
            elif kind == "board":
                result = read_board(data)
                leaf = read_leaf_score(data)
                if leaf and self.leaf_board_update(*leaf, server=True):
                    save_leaf_board(self.lboard)
                    if self.page == "board":
                        self.refresh_board()
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
        self.board_note = c.create_text(WIDTH / 2, 366, text="", fill="#8888aa",
                                        font=("Helvetica", 11), tags="board")
        self.make_button("BOARD_TAB_MILLOKU", "MILLOKU", 150, 66, 350, 96, "board",
                         lambda: self.set_board_tab("milloku"), size=12)
        self.make_button("BOARD_TAB_LEAF", "LEAF SWEEP", 370, 66, 570, 96, "board",
                         lambda: self.set_board_tab("leaf"), size=12)
        self.board_rows = []
        for i in range(10):
            y = 118 + i * 26
            self.board_rows.append({
                "rank": c.create_text(210, y, anchor="e", text="", fill="#8888aa",
                                      font=("Helvetica", 14, "bold"), tags="board"),
                "name": c.create_text(232, y, anchor="w", text="", fill="white",
                                      font=("Helvetica", 14, "bold"), tags="board"),
                "level": c.create_text(515, y, anchor="e", text="", fill="#8888aa",
                                       font=("Helvetica", 13), tags="board"),
                "time": c.create_text(590, y, anchor="e", text="", fill="#8888aa",
                                      font=("Helvetica", 13), tags="board")})
        self.make_button("BOARD_BACK", "BACK", 260, 385, 460, 430, "board",
                         lambda: self.show_page("menu"), size=14)

    def set_board_tab(self, tab):
        self.board_tab = tab
        self.refresh_board()

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
        leaf = self.board_tab == "leaf"
        self.board_title.set_text("LEAF SWEEP BOARD" if leaf else "MILLOKU LEADERBOARD")
        self.buttons["BOARD_TAB_MILLOKU"]["text"].set_text("MILLOKU" if leaf else "> MILLOKU <")
        self.buttons["BOARD_TAB_LEAF"]["text"].set_text("> LEAF SWEEP <" if leaf else "LEAF SWEEP")
        if leaf:
            # highest level first; if tied, the quickest time on that level
            entries = []
            for who, times in self.lboard.items():
                if who in ROSTER and times:
                    top = max(times)
                    entries.append((top, times[top], who))
            entries.sort(key=lambda t: (-t[0], t[1]))
            empty = "No scores yet. Clear a Leaf Sweep level to get on the board!"
        else:
            # most levels first; if tied, whoever got there first
            entries = sorted(((level, stamp, who) for who, (level, stamp) in self.board.items()
                              if who in ROSTER and level > 0), key=lambda t: (-t[0], t[1]))
            empty = "No scores yet. Beat a Milloku level to get on the board!"
        c.itemconfig(self.board_note, text="" if entries else empty)
        for i, row in enumerate(self.board_rows):
            if i < len(entries):
                level, extra, who = entries[i]
                c.itemconfig(row["rank"], text=str(i + 1))
                c.itemconfig(row["name"], text=ROSTER[who] + ("  (you)" if who == self.my_fp else ""))
                if leaf:
                    c.itemconfig(row["level"], text=f"ALL {LEAF_LEVELS} CLEAR!" if level >= LEAF_LEVELS else f"level {level}")
                    c.itemconfig(row["time"], text=format_tenths(extra))
                else:
                    c.itemconfig(row["level"], text="ALL 100 DONE!" if level >= 100 else f"level {level} / 100")
                    c.itemconfig(row["time"], text="")
            else:
                for part in row.values():
                    c.itemconfig(part, text="")

    def leaf_board_update(self, who, level, tenths, server=False):
        """Keep each player's quickest time per level. Returns True if the board changed."""
        if server:
            old = self.lboard_server.setdefault(who, {}).get(level)
            if old is None or tenths < old:
                self.lboard_server[who][level] = tenths
        times = self.lboard.setdefault(who, {})
        if level not in times or tenths < times[level]:
            times[level] = tenths
            return True
        return False

    def post_leaf_score(self, level, tenths):
        if self.my_fp not in ROSTER or not BOARD_CHANNEL_ID:
            return
        stamp = int(time.time())
        e, s = sign(self.secret, f"LEAF|{level}|{tenths}|{stamp}")
        if self.bot.post(f"GESTER-LEAF {self.public:x}:{e:x}:{s:x}:{level}:{tenths}:{stamp}", BOARD_CHANNEL_ID):
            self.lboard_server.setdefault(self.my_fp, {})[level] = tenths

    def after_board_history(self):
        save_board(self.board)
        save_leaf_board(self.lboard)
        if self.page == "board":
            self.refresh_board()
        mine = self.lboard.get(self.my_fp, {})                   # share Leaf Sweep times the board doesn't know about
        known = self.lboard_server.get(self.my_fp, {})
        for level, tenths in sorted(mine.items()):
            if level not in known or tenths < known[level]:
                self.post_leaf_score(level, tenths)
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
        if self.page == "leaves":
            try:
                typing = isinstance(self.root.focus_get(), (tk.Entry, tk.Text))
            except KeyError:
                typing = False
            if event.keysym in ("r", "R") and not typing:
                self.leaf_restart()
            elif event.keysym in ("n", "N") and not typing:
                self.leaf_skip()                 # (does nothing unless you are the owner)
            return
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

    # --- the LEAF SWEEP page ---
    def make_leaf_page(self):
        c, T = self.canvas, "leaves"
        c.create_polygon(rounded(LF_X0 - 8, LF_Y0 - 8, LF_X1 + 8, LF_Y1 + 8, 16), smooth=True,
                         fill="#10101a", outline="#333344", width=3, tags=T)
        stripe = (LF_X1 - LF_X0) / 8
        self.leaf_stripes = []
        for i in range(8):                                   # mown-lawn stripes
            self.leaf_stripes.append(c.create_rectangle(LF_X0 + i * stripe, LF_Y0, LF_X0 + (i + 1) * stripe, LF_Y1,
                                     fill="#161622" if i % 2 else "#10101a", outline="", tags=T))
        self.make_button("LEAF_BACK", "BACK", 20, 12, 92, 44, T, lambda: self.show_page("menu"), size=11)
        self.leaf_title = FancyText(c, 102, 28, "LEAF SWEEP", 16, T, depth=3, shadow=True, anchor="w")
        self.make_button("LEAF_PREV", "<", 268, 12, 300, 44, T, lambda: self.leaf_go(-1), size=14)
        self.make_button("LEAF_NEXT_LEVEL", ">", 420, 12, 452, 44, T, lambda: self.leaf_go(1), size=14)
        self.leaf_label = c.create_text(360, 22, text="", fill="white", font=("Helvetica", 11, "bold"), tags=T)
        self.leaf_info = c.create_text(360, 38, text="", fill="#8888aa", font=("Helvetica", 9), tags=T)
        self.make_button("LEAF_RESTART", "RETRY", 460, 12, 518, 44, T, self.leaf_restart, size=10)
        if OWNER_ID and self.my_fp == OWNER_ID:           # a testing tool only the owner gets
            self.make_button("LEAF_SKIP", "SKIP", 552, 442, 628, 468, T, self.leaf_skip, size=10)
        self.leaf_score = c.create_text(LF_X1, 22, anchor="e", text="", fill="white",
                                        font=("Helvetica", 13, "bold"), tags=T)
        self.leaf_best = c.create_text(LF_X1, 38, anchor="e", text="", fill="#6a6a88",
                                       font=("Helvetica", 9), tags=T)
        c.create_rectangle(LF_X0, 50, LF_X1, 60, fill="#10101a", outline="#333344", tags=T)
        self.leaf_bar = c.create_rectangle(LF_X0 + 1, 51, LF_X0 + 1, 59, fill="#ffffff", outline="", tags=T)
        self.leaf_streaks = [c.create_line(0, 0, 0, 0, fill="#ffffff", width=2, capstyle="round", tags=T)
                             for _ in range(9)]
        self.leaf_msg = c.create_text((LF_X0 + LF_X1) / 2, LF_Y0 + 28, text="", fill="#ffffff",
                                      font=("Helvetica", 22, "bold"), tags=T)
        # the broom (everything that moves during a level sits just under it)
        handle = c.create_line(0, 0, 0, 0, fill="#8a5a2b", width=5, capstyle="round", tags=T)
        head = c.create_polygon(0, 0, 0, 0, 0, 0, fill="#e0b64a", outline="#a8802a", width=2, tags=T)
        band = c.create_line(0, 0, 0, 0, fill="#6b4a1c", width=3, capstyle="round", tags=T)
        self.leaf_broom = [handle, head, band]
        self.leaf_anchor = c.create_rectangle(0, 0, 0, 0, outline="", tags=T)

        # the "level clear" panel
        W, cx = "leafwin", (LF_X0 + LF_X1) / 2
        c.create_polygon(rounded(cx - 175, 140, cx + 175, 372, 22), smooth=True, fill="#161622",
                         outline="#333344", width=3, tags=W)
        self.leaf_win_title = FancyText(c, cx, 180, "LEVEL CLEAR!", 26, W, depth=4, shadow=True)
        self.leaf_win_stars = [c.create_polygon(star_points(cx + (i - 1) * 56, 232, 20), fill="#3a3a4a",
                                                outline="#555570", width=2, tags=W) for i in range(3)]
        self.leaf_win_info = c.create_text(cx, 274, text="", fill="white", font=("Helvetica", 12, "bold"), tags=W)
        self.leaf_win_best = c.create_text(cx, 294, text="", fill="#8888aa", font=("Helvetica", 10), tags=W)
        for i, (key, label, action) in enumerate([("LEAF_WIN_NEXT", "NEXT", self.leaf_next),
                                                  ("LEAF_WIN_REPLAY", "REPLAY", self.leaf_restart),
                                                  ("LEAF_WIN_MENU", "MENU", lambda: self.show_page("menu"))]):
            x1 = cx - 165 + i * 113
            self.make_button(key, label, x1, 318, x1 + 104, 354, W, action, size=11)
        c.itemconfig(W, state="hidden")

    def open_leaves(self):
        self.lf_level = min(self.lf_done + 1, LEAF_LEVELS)
        self.show_page("leaves")

    def leaf_enter(self):
        """The page just appeared: tidy the extras and start the level."""
        for item in self.leaf_streaks + [self.leaf_msg]:
            self.canvas.itemconfig(item, state="hidden")
        self.leaf_load(self.lf_level)

    def leaf_leave(self):
        self.canvas.delete("lfdyn")
        self.canvas.itemconfig("leafwin", state="hidden")
        self.canvas.config(cursor="")
        self.lf, self.lf_overlay, self.lf_cursor_hidden = None, False, False

    def lf_item(self, kind, *args, **options):
        """Make something that belongs to the current level (tidied up when the level ends)."""
        c = self.canvas
        item = getattr(c, "create_" + kind)(*args, tags=("leaves", "lfdyn"), **options)
        c.tag_lower(item, self.leaf_broom[0])        # under the broom, over the lawn
        return item

    def leaf_load(self, level):
        c = self.canvas
        c.delete("lfdyn")
        c.itemconfig("leafwin", state="hidden")
        self.lf_overlay = False
        p = leaf_level(level)
        self.lf_level = level
        bx, by, bw, bh = p["bin"]
        world = LEAF_WORLDS[min(len(LEAF_WORLDS) - 1, (level - 1) // 10)]
        for i, stripe in enumerate(self.leaf_stripes):          # each world lights the lawn differently
            c.itemconfig(stripe, fill=mix(THEME["panel"] if i % 2 else THEME["panel_dark"], world[1], 0.17))
        c.itemconfig(self.leaf_broom[1], outline="#a8802a", width=2)
        bin_items = [
            self.lf_item("polygon", rounded(bx + 4, by + 6, bx + bw + 4, by + bh + 6, 12), smooth=True,
                         fill="#05050a", outline=""),
            self.lf_item("polygon", rounded(bx, by, bx + bw, by + bh, 12), smooth=True,
                         fill="#7a4f27", outline="#c28a4a", width=3),
            self.lf_item("polygon", rounded(bx + 10, by + 10, bx + bw - 10, by + bh - 10, 8), smooth=True,
                         fill="#24160a", outline="")]
        fx = {"bumps": [], "vents": [], "portals": []}
        specks = []                                             # floating specks that belong to the world
        dark = THEME["panel_dark"]
        for i in range(16):
            r = random.uniform(1.4, 3.0)
            x, y = random.uniform(LF_X0, LF_X1), random.uniform(LF_Y0, LF_Y1)
            color = {"dust": mix(dark, "#e6f0a0", 0.45), "petal": mix(dark, "#ffb070", 0.55),
                     "firefly": "#d8ff6a", "snow": mix(dark, "#ffffff", 0.75),
                     "ember": "#ff8a30"}[world[2]]
            specks.append({"item": self.lf_item("oval", x - r, y - r, x + r, y + r, fill=color, outline=""),
                           "x": x, "y": y, "r": r, "ph": random.uniform(0, math.tau), "color": color})
        for mx, my, mrx, mry in p["mud"]:
            self.lf_item("oval", mx - mrx - 4, my - mry - 4, mx + mrx + 4, my + mry + 4, fill="#3a2614", outline="")
            self.lf_item("oval", mx - mrx, my - mry, mx + mrx, my + mry, fill="#5b3d22", outline="#2f1d0e", width=2)
            for k in range(4):
                ang = k * 1.7 + mx
                px, py = mx + math.cos(ang) * mrx * 0.45, my + math.sin(ang) * mry * 0.45
                self.lf_item("oval", px - 7, py - 4, px + 7, py + 4, fill="#46301a", outline="")
            self.lf_item("oval", mx - mrx * 0.4, my - mry * 0.55, mx - mrx * 0.05, my - mry * 0.2, fill="#7a5632", outline="")
        for x0, y0, x1, y1, dx, dy in p["vents"]:
            self.lf_item("polygon", rounded(x0 + 3, y0 + 5, x1 + 3, y1 + 5, 10), smooth=True, fill="#05050a", outline="")
            self.lf_item("polygon", rounded(x0, y0, x1, y1, 10), smooth=True, fill="#26384a", outline="#6f93b5", width=2)
            chev = [self.lf_item("line", 0, 0, 0, 0, 0, 0, fill="#bfe3ff", width=3, capstyle="round", joinstyle="round")
                    for _ in range(3)]
            fx["vents"].append({"rect": (x0, y0, x1, y1), "d": (dx, dy), "chev": chev})
        for rx, ry, rr in p["rocks"]:
            self.lf_item("oval", rx - rr, ry - rr, rx + rr, ry + rr, fill="#6d6d78", outline="#4a4a54", width=2)
            self.lf_item("oval", rx - rr * 0.6, ry - rr * 0.72, rx + rr * 0.1, ry - rr * 0.1,
                         fill="#8c8c98", outline="")
        for bx0, by0, br in p["bumpers"]:
            ring = self.lf_item("oval", bx0 - br - 5, by0 - br - 5, bx0 + br + 5, by0 + br + 5, fill="", outline="#ffb3c8", width=2)
            cap = self.lf_item("oval", bx0 - br, by0 - br, bx0 + br, by0 + br, fill="#d63b5c", outline="#8f1f3a", width=3)
            spots = []
            for k in range(3):
                ang = k * 2.1 + 0.6
                sx, sy = bx0 + math.cos(ang) * br * 0.5, by0 + math.sin(ang) * br * 0.5
                spots.append(self.lf_item("oval", sx - 3.5, sy - 3.5, sx + 3.5, sy + 3.5, fill="#fff3f6", outline=""))
            fx["bumps"].append({"x": bx0, "y": by0, "r": br, "ring": ring, "cap": cap, "spots": spots, "pulse": 0.0})
        for (ax, ay), (bx2, by2), pi in p["portals"]:
            color = PORTAL_COLORS[pi % len(PORTAL_COLORS)]
            ends = []
            for qx, qy in ((ax, ay), (bx2, by2)):
                outer = self.lf_item("oval", qx - 24, qy - 24, qx + 24, qy + 24, fill="", outline=mix(color, "#000000", 0.35), width=3)
                inner = self.lf_item("oval", qx - 19, qy - 19, qx + 19, qy + 19, fill=mix(color, "#000000", 0.78), outline=color, width=3)
                swirl = self.lf_item("arc", qx - 12, qy - 12, qx + 12, qy + 12, start=0, extent=110, style="arc",
                                     outline="#ffffff", width=3)
                ends.append({"x": qx, "y": qy, "outer": outer, "inner": inner, "swirl": swirl})
            fx["portals"].append({"ends": ends, "r": 19, "color": color, "pulse": 0.0})
        leaves = []
        for x, y, s, color_index, gold, angle in p["leaves"]:
            color = GOLD_LEAF if gold else LEAF_COLORS[color_index]
            leaf = {"x": x, "y": y, "vx": 0.0, "vy": 0.0, "a": angle, "w": 0.0, "s": s, "gold": gold,
                    "color": color, "state": "on", "t": 0, "sd": random.choice((-1, 1)), "cd": 0, "mud": False,
                    "body": self.lf_item("polygon", *([0, 0] * len(LEAF_SHAPE)), smooth=True, fill=color, outline=""),
                    "rib": self.lf_item("line", 0, 0, 0, 0, fill=mix(color, "#000000", 0.4), width=1.5,
                                        capstyle="round")}
            self.leaf_draw(leaf)
            leaves.append(leaf)
        self.lf = {"p": p, "level": level, "frame": 0, "t0": time.time(), "state": "play", "score": 0,
                   "combo": 0, "last_collect": -999, "collected": 0, "leaves": leaves, "bin": [bx, by, bw, bh],
                   "bin_dir": 1, "bin_items": bin_items, "bin_flash": 0.0, "on": False, "bx": 0.0, "by": 0.0,
                   "bvx": 0.0, "bvy": 0.0, "hx": 1.0, "hy": 0.0, "speed": 0.0, "samples": [], "last_sweep": -99,
                   "wind": "idle", "wind_t": 0, "wind_dir": (1, 0), "floats": [], "bits": [], "win_t": 0,
                   "ov_t": 0, "elapsed": 0.0, "stars": 0, "fx": fx, "specks": specks, "world": world,
                   "pile": 0, "hot": False}
        cx, cy = (LF_X0 + LF_X1) / 2, (LF_Y0 + LF_Y1) / 2 - 30     # the level banner
        banner = [self.lf_item("text", cx + 2, cy + 2, text=f"LEVEL {level}", fill="#000000",
                               font=("Helvetica", 38, "bold")),
                  self.lf_item("text", cx, cy, text=f"LEVEL {level}", fill="#ffffff", font=("Helvetica", 38, "bold")),
                  self.lf_item("text", cx, cy + 40, text=world[0] if (level - 1) % 10 == 0 else "",
                               fill=world[1], font=("Helvetica", 16, "bold"))]
        self.lf["banner"] = {"items": banner, "t": 0, "y": cy}
        self.leaf_update_texts()
        c.coords(self.leaf_bar, LF_X0 + 1, 51, LF_X0 + 1, 59)
        c.itemconfig(self.leaf_msg, state="hidden")
        for item in self.leaf_streaks:
            c.itemconfig(item, state="hidden")
        if level in LEAF_HINTS:
            c.itemconfig(self.status, text=LEAF_HINTS[level])
        else:
            c.itemconfig(self.status, text=f"Level {level}: sweep all {p['count']} leaves into the bin")

    def leaf_draw(self, leaf, scale=1.0):
        c = self.canvas
        s, x, y = leaf["s"] * scale, leaf["x"], leaf["y"]
        cs, sn = math.cos(leaf["a"]), math.sin(leaf["a"])
        pts = []
        for px, py in LEAF_SHAPE:
            pts.append(x + (px * cs - py * sn) * s)
            pts.append(y + (px * sn + py * cs) * s)
        c.coords(leaf["body"], *pts)
        c.coords(leaf["rib"], x - cs * s * 0.85, y - sn * s * 0.85, x + cs * s * 0.7, y + sn * s * 0.7)
        leaf["drawn"] = (x, y, leaf["a"], scale)

    def leaf_update_texts(self):
        lf, c = self.lf, self.canvas
        seconds = int(lf["elapsed"] if lf["state"] == "won" else time.time() - lf["t0"])
        c.itemconfig(self.leaf_label, text=f"LEVEL {lf['level']} / {LEAF_LEVELS}")
        c.itemconfig(self.leaf_info, text=f"leaves {lf['collected']}/{len(lf['p']['leaves'])}   "
                                          f"{seconds // 60}:{seconds % 60:02d}")
        c.itemconfig(self.leaf_score, text=f"SCORE {lf['score']}")
        best = self.lf_stars.get(lf["level"])
        c.itemconfig(self.leaf_best, text=f"best: {best}/3 stars" if best else "not cleared yet")

    def leaf_skip(self):
        """OWNER ONLY (for testing): count this level as cleared and go to the next one."""
        if not (OWNER_ID and self.my_fp == OWNER_ID) or self.page != "leaves" or not self.lf:
            return
        level = self.lf_level
        self.lf_done = max(self.lf_done, level)
        save_leaf_progress(self.lf_done, self.lf_stars)      # no stars and no leaderboard time for a skip
        play(self.leaf_gold_sound)
        if level < LEAF_LEVELS:
            self.leaf_load(level + 1)
            self.canvas.itemconfig(self.status, text=f"Skipped level {level} (owner)")
        else:
            self.canvas.itemconfig(self.status, text="That was the last level (owner skip)")

    def leaf_go(self, step):
        target = self.lf_level + step
        if target < 1 or target > LEAF_LEVELS:
            return
        owner = bool(OWNER_ID and self.my_fp == OWNER_ID)       # the owner can jump to any level
        if target > min(self.lf_done + 1, LEAF_LEVELS) and not owner:
            self.canvas.itemconfig(self.status, text=f"Clear level {self.lf_level} first!")
            return
        self.leaf_load(target)

    def leaf_restart(self):
        if self.page == "leaves":
            self.leaf_load(self.lf_level)

    def leaf_next(self):
        if self.page == "leaves" and self.lf_level < LEAF_LEVELS:
            self.leaf_load(self.lf_level + 1)

    # --- the broom: follows the mouse, and pushes leaves ahead of it ---
    def leaf_broom_update(self):
        lf, c, ptr = self.lf, self.canvas, self.pointer
        inside = (ptr is not None and not self.lf_overlay and LF_X0 - 14 <= ptr[0] <= LF_X1 + 14
                  and LF_Y0 - 14 <= ptr[1] <= LF_Y1 + 14)
        lf["samples"] = []
        if not inside:                          # the broom is lifted off the lawn
            lf["on"], lf["speed"], lf["bvx"], lf["bvy"] = False, 0.0, 0.0, 0.0
            for item in self.leaf_broom:
                c.itemconfig(item, state="hidden")
            return
        tx, ty = min(max(ptr[0], LF_X0 + 4), LF_X1 - 4), min(max(ptr[1], LF_Y0 + 4), LF_Y1 - 4)
        px, py = lf["bx"], lf["by"]
        if not lf["on"]:
            lf["bx"], lf["by"], lf["on"] = tx, ty, True
            px, py = tx, ty
        else:
            lf["bx"] += (tx - lf["bx"]) * 0.65
            lf["by"] += (ty - lf["by"]) * 0.65
        lf["bvx"], lf["bvy"] = lf["bx"] - px, lf["by"] - py
        speed = math.hypot(lf["bvx"], lf["bvy"])
        lf["speed"] = speed
        if speed > 2:                           # the bristles turn to face where the broom is heading
            lf["hx"] += (lf["bvx"] / speed - lf["hx"]) * 0.4
            lf["hy"] += (lf["bvy"] / speed - lf["hy"]) * 0.4
            size = math.hypot(lf["hx"], lf["hy"]) or 1.0
            lf["hx"], lf["hy"] = lf["hx"] / size, lf["hy"] / size
        steps = max(1, min(4, int(speed / 12) + 1))      # check along the path so fast flicks don't skip leaves
        lf["samples"] = [(px + (lf["bx"] - px) * (k + 1) / steps, py + (lf["by"] - py) * (k + 1) / steps)
                         for k in range(steps)]
        hx, hy, bx, by = lf["hx"], lf["hy"], lf["bx"], lf["by"]
        nx, ny = -hy, hx
        c.coords(self.leaf_broom[0], bx + 8, by - 4, bx + 46, by - 76)
        c.coords(self.leaf_broom[1],
                 bx + nx * 24 + hx * 4, by + ny * 24 + hy * 4, bx - nx * 24 + hx * 4, by - ny * 24 + hy * 4,
                 bx - nx * 24 - hx * 9, by - ny * 24 - hy * 9, bx + nx * 24 - hx * 9, by + ny * 24 - hy * 9)
        c.coords(self.leaf_broom[2], bx + nx * 22 - hx * 3, by + ny * 22 - hy * 3,
                 bx - nx * 22 - hx * 3, by - ny * 22 - hy * 3)
        for item in self.leaf_broom:
            c.itemconfig(item, state="normal")

    # --- wind ---
    def leaf_atmosphere(self, f):
        """The world's floating specks (fireflies, snow, embers...) and the level banner."""
        lf, c = self.lf, self.canvas
        kind = lf["world"][2]
        if f % 2 == 0:
            for sp in lf["specks"]:
                x, y, ph, r = sp["x"], sp["y"], sp["ph"], sp["r"]
                if kind == "dust":
                    x += math.sin(f * 0.03 + ph) * 0.5
                    y -= 0.25
                elif kind == "petal":
                    x += 0.9 + math.sin(f * 0.05 + ph) * 0.4
                    y += math.sin(f * 0.04 + ph) * 0.5
                elif kind == "firefly":
                    x += math.cos(ph + f * 0.021) * 0.9
                    y += math.sin(ph * 1.3 + f * 0.017) * 0.8
                    glow = 0.5 + 0.5 * math.sin(f * 0.07 + ph)
                    c.itemconfig(sp["item"], fill=mix(THEME["panel_dark"], sp["color"], 0.15 + 0.85 * glow))
                elif kind == "snow":
                    x += math.sin(f * 0.04 + ph) * 0.6
                    y += 0.7 + r * 0.2
                else:                                         # embers rise and flicker
                    x += math.sin(f * 0.06 + ph) * 0.7
                    y -= 0.9 + r * 0.15
                    c.itemconfig(sp["item"], fill=mix("#ff5a1c", "#ffd27a", 0.5 + 0.5 * math.sin(f * 0.2 + ph)))
                if x > LF_X1:
                    x = LF_X0
                elif x < LF_X0:
                    x = LF_X1
                if y > LF_Y1:
                    y = LF_Y0
                elif y < LF_Y0:
                    y = LF_Y1
                sp["x"], sp["y"] = x, y
                c.coords(sp["item"], x - r, y - r, x + r, y + r)
        b = lf.get("banner")
        if b:
            b["t"] += 1
            t = b["t"]
            if t > 78:
                for item in b["items"]:
                    c.delete(item)
                lf["banner"] = None
            else:
                fade = min(1.0, t / 10) * (1.0 if t < 52 else max(0.0, 1 - (t - 52) / 26))
                bg = THEME["panel_dark"]
                y = b["y"] - t * 0.12
                c.coords(b["items"][0], (LF_X0 + LF_X1) / 2 + 2, y + 2)
                c.coords(b["items"][1], (LF_X0 + LF_X1) / 2, y)
                c.coords(b["items"][2], (LF_X0 + LF_X1) / 2, y + 40)
                c.itemconfig(b["items"][0], fill=mix(bg, "#000000", fade))
                c.itemconfig(b["items"][1], fill=mix(bg, "#ffffff", fade))
                c.itemconfig(b["items"][2], fill=mix(bg, lf["world"][1], fade))

    def leaf_fx_tick(self, f):
        """Animate the obstacles: pulsing mushrooms, flowing vent arrows, swirling portals."""
        c, fx = self.canvas, self.lf["fx"]
        for b in fx["bumps"]:
            if b["pulse"] > 0:
                b["pulse"] = b["pulse"] * 0.8 if b["pulse"] > 0.03 else 0.0
                grow = 1 + 0.3 * b["pulse"]
                r = b["r"] * grow
                c.coords(b["cap"], b["x"] - r, b["y"] - r, b["x"] + r, b["y"] + r)
                c.itemconfig(b["cap"], fill=mix("#d63b5c", "#ffd0dc", b["pulse"] * 0.6))
                c.itemconfig(b["ring"], outline=mix("#ffb3c8", "#ffffff", b["pulse"]))
        if f % 2 == 0:
            for v in fx["vents"]:
                x0, y0, x1, y1 = v["rect"]
                dx, dy = v["d"]
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                length = (x1 - x0 if dx else y1 - y0) - 24
                for i, item in enumerate(v["chev"]):
                    t = ((f * 1.6 + i * length / 3) % length) - length / 2
                    px, py = cx + dx * t, cy + dy * t
                    qx, qy = -dy, dx
                    c.coords(item, px - dx * 7 + qx * 12, py - dy * 7 + qy * 12, px + dx * 7, py + dy * 7,
                             px - dx * 7 - qx * 12, py - dy * 7 - qy * 12)
            for portal in fx["portals"]:
                pulse = portal["pulse"] = portal["pulse"] * 0.85 if portal["pulse"] > 0.03 else 0.0
                for k, end in enumerate(portal["ends"]):
                    grow = 3 * math.sin(f * 0.18 + k * 2) + 8 * pulse
                    x, y = end["x"], end["y"]
                    c.coords(end["outer"], x - 24 - grow, y - 24 - grow, x + 24 + grow, y + 24 + grow)
                    c.itemconfig(end["swirl"], start=(f * 11 + k * 180) % 360)
                    c.itemconfig(end["inner"], outline=mix(portal["color"], "#ffffff", pulse * 0.8))

    def leaf_wind(self):
        """Returns the push (ax, ay) the wind is giving the leaves this frame."""
        lf, c = self.lf, self.canvas
        w = lf["p"]["wind"]
        if not w or lf["state"] != "play":
            return 0.0, 0.0
        lf["wind_t"] += 1
        dx, dy = lf["wind_dir"]
        if lf["wind"] == "idle":
            if lf["wind_t"] >= w["wait"]:
                lf["wind"], lf["wind_t"] = "warn", 0
                lf["wind_dir"] = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
                arrows = {(1, 0): ">>>  WIND  >>>", (-1, 0): "<<<  WIND  <<<",
                          (0, 1): "vvv  WIND  vvv", (0, -1): "^^^  WIND  ^^^"}[lf["wind_dir"]]
                c.itemconfig(self.leaf_msg, text=arrows, state="normal")
            return 0.0, 0.0
        if lf["wind"] == "warn":
            c.itemconfig(self.leaf_msg, fill=rainbow(self.hue * 6) if lf["wind_t"] % 8 < 5 else "#ffffff")
            if lf["wind_t"] >= 34:
                lf["wind"], lf["wind_t"] = "gust", 0
                play(self.leaf_gust_sound)
            return 0.0, 0.0
        t = lf["wind_t"]                          # a gust: builds, peaks, fades
        profile = math.sin(math.pi * min(1.0, t / 50))
        color = mix(THEME["panel_dark"], "#ffffff", 0.5)
        span = (LF_X1 - LF_X0, LF_Y1 - LF_Y0)
        for k, streak in enumerate(self.leaf_streaks):
            if dx:
                lane = LF_Y0 + 24 + (k + 0.5) * (span[1] - 48) / len(self.leaf_streaks)
                u = (t * 24 + k * 83) % (span[0] + 120) - 60
                head = LF_X0 + u if dx > 0 else LF_X1 - u
                tail = head - dx * 55
                x1, x2 = min(max(head, LF_X0), LF_X1), min(max(tail, LF_X0), LF_X1)
                coords, length = (x1, lane, x2, lane), abs(x1 - x2)
            else:
                lane = LF_X0 + 24 + (k + 0.5) * (span[0] - 48) / len(self.leaf_streaks)
                u = (t * 24 + k * 83) % (span[1] + 120) - 60
                head = LF_Y0 + u if dy > 0 else LF_Y1 - u
                tail = head - dy * 55
                y1, y2 = min(max(head, LF_Y0), LF_Y1), min(max(tail, LF_Y0), LF_Y1)
                coords, length = (lane, y1, lane, y2), abs(y1 - y2)
            c.coords(streak, *coords)
            c.itemconfig(streak, fill=color, state="normal" if length > 3 else "hidden")
        if t >= 50:
            lf["wind"], lf["wind_t"] = "idle", 0
            c.itemconfig(self.leaf_msg, state="hidden")
            for streak in self.leaf_streaks:
                c.itemconfig(streak, state="hidden")
        power = lf["p"]["wind"]["power"] * profile
        return dx * power, dy * power

    # --- one frame of the game ---
    def leaf_tick(self):
        lf, c = self.lf, self.canvas
        lf["frame"] += 1
        f, state = lf["frame"], lf["state"]
        self.leaf_broom_update()

        # the cursor hides while you are sweeping (the broom replaces it)
        want_hidden = bool(self.pointer and not self.lf_overlay and self.hovered is None
                           and LF_X0 - 6 <= self.pointer[0] <= LF_X1 + 6 and LF_Y0 - 6 <= self.pointer[1] <= LF_Y1 + 6)
        if want_hidden != self.lf_cursor_hidden:
            self.lf_cursor_hidden = want_hidden
            c.config(cursor="none" if want_hidden else "")

        # the bin slides along the bottom on later levels
        bx, by, bw, bh = lf["bin"]
        if lf["p"]["moving"] and state == "play":
            nxt = bx + lf["bin_dir"] * lf["p"]["bin_speed"]
            lo, hi = LF_X0 + 6, LF_X1 - bw - 6
            if nxt < lo or nxt > hi:
                lf["bin_dir"] *= -1
                nxt = min(max(nxt, lo), hi)
            for item in lf["bin_items"]:
                c.move(item, nxt - bx, 0)
            lf["bin"][0] = bx = nxt
        zone = (bx + 9, by + 9, bx + bw - 9, by + bh - 9)
        flash = lf["bin_flash"]
        lf["bin_flash"] = flash * 0.8 if flash > 0.03 else 0.0
        if flash or lf["bin_flash"]:
            c.itemconfig(lf["bin_items"][2], fill=mix("#24160a", "#ffcf6e", flash * 0.55))
            c.itemconfig(lf["bin_items"][1], outline=mix("#c28a4a", "#ffffff", flash * 0.6))

        self.leaf_atmosphere(f)
        ax, ay = self.leaf_wind()
        p_mud, p_vents, fx = lf["p"]["mud"], lf["p"]["vents"], lf["fx"]
        self.leaf_fx_tick(f)
        samples = lf["samples"] if (lf["on"] and state == "play") else []
        speed = lf["speed"]
        hx, hy = lf["hx"], lf["hy"]
        nx, ny = -hy, hx
        bvx, bvy = lf["bvx"], lf["bvy"]
        if speed > 38:                           # cap the broom's push (a huge flick shouldn't launch leaves)
            bvx, bvy = bvx * 38 / speed, bvy * 38 / speed
        pushed = 0
        finished = []
        for leaf in lf["leaves"]:
            if leaf["state"] == "in":            # sinking into the bin
                leaf["t"] += 1
                leaf["x"] += ((zone[0] + zone[2]) / 2 - leaf["x"]) * 0.35
                leaf["y"] += ((zone[1] + zone[3]) / 2 - leaf["y"]) * 0.35
                self.leaf_draw(leaf, max(0.05, 1 - leaf["t"] / 8))
                if leaf["t"] >= 8:
                    finished.append(leaf)
                continue
            if leaf["cd"] > 0:
                leaf["cd"] -= 1
            in_mud = False
            for mx, my, mrx, mry in p_mud:
                if ((leaf["x"] - mx) / mrx) ** 2 + ((leaf["y"] - my) / mry) ** 2 < 1:
                    in_mud = True
                    break
            if in_mud != leaf["mud"]:
                leaf["mud"] = in_mud
                if in_mud and math.hypot(leaf["vx"], leaf["vy"]) > 3:       # squelch as it lands in the mud
                    play_at(self.leaf_mud_sound, 0.35 + math.hypot(leaf["vx"], leaf["vy"]) / 40)
                    self.leaf_burst(leaf["x"], leaf["y"], "#6b4a28", 3, 2.0)
            for x0, y0, x1, y1, vdx, vdy in p_vents:                         # air vents blow along their arrows
                if x0 <= leaf["x"] <= x1 and y0 <= leaf["y"] <= y1:
                    leaf["vx"] += vdx * 0.6
                    leaf["vy"] += vdy * 0.6
            if ax or ay:
                leaf["vx"] += ax * (0.5 + 0.5 * math.sin(leaf["a"] * 3 + leaf["x"] * 0.01) ** 2)
                leaf["vy"] += ay * (0.5 + 0.5 * math.sin(leaf["a"] * 3 + leaf["y"] * 0.01) ** 2)
            for sx, sy in samples:
                lx, ly = leaf["x"] - sx, leaf["y"] - sy
                if abs(lx) > 60 or abs(ly) > 60:
                    continue
                along, across = lx * nx + ly * ny, lx * hx + ly * hy      # where the leaf is, relative to the blade
                off = along - max(-24, min(24, along))
                dist = math.hypot(off, across)
                reach = 15 + leaf["s"] * 0.55
                if dist >= reach:
                    continue
                if dist < 0.001:
                    ox, oy = hx, hy
                else:
                    ox, oy = (off * nx + across * hx) / dist, (off * ny + across * hy) / dist
                k = 1.0 - dist / reach
                if speed > 1.5:
                    if across > -9:              # only what is in front of the bristles gets swept
                        pull = (0.55 + 0.4 * k) * (0.45 if in_mud else 1.0)
                        leaf["vx"] += (bvx * 1.12 - leaf["vx"]) * pull + ox * speed * 0.07
                        leaf["vy"] += (bvy * 1.12 - leaf["vy"]) * pull + oy * speed * 0.07
                        leaf["w"] += (random.random() - 0.5) * 0.5
                        pushed += 1
                        if speed > 12 and random.random() < 0.05:
                            self.leaf_burst(leaf["x"], leaf["y"], leaf["color"], 1, 2.0)
                        break
                else:                            # the broom is resting on it: just ease the leaf aside
                    leaf["vx"] += ox * 0.8 * k
                    leaf["vy"] += oy * 0.8 * k
                    break
            drag = 0.8 if in_mud else 0.915
            leaf["vx"] *= drag
            leaf["vy"] *= drag
            sp = math.hypot(leaf["vx"], leaf["vy"])
            if sp > 26:
                leaf["vx"], leaf["vy"], sp = leaf["vx"] * 26 / sp, leaf["vy"] * 26 / sp, 26.0
            if sp > 0.15:
                leaf["x"] += leaf["vx"]
                leaf["y"] += leaf["vy"]
                leaf["a"] += leaf["w"] + sp * 0.025 * leaf["sd"]
                leaf["w"] *= 0.9
                r = leaf["s"] * 0.6
                if leaf["x"] < LF_X0 + r:
                    leaf["x"], leaf["vx"] = LF_X0 + r, abs(leaf["vx"]) * 0.5
                elif leaf["x"] > LF_X1 - r:
                    leaf["x"], leaf["vx"] = LF_X1 - r, -abs(leaf["vx"]) * 0.5
                if leaf["y"] < LF_Y0 + r:
                    leaf["y"], leaf["vy"] = LF_Y0 + r, abs(leaf["vy"]) * 0.5
                elif leaf["y"] > LF_Y1 - r:
                    leaf["y"], leaf["vy"] = LF_Y1 - r, -abs(leaf["vy"]) * 0.5
                for rx, ry, rr in lf["p"]["rocks"]:       # bounce off the rocks
                    dx, dy = leaf["x"] - rx, leaf["y"] - ry
                    d = math.hypot(dx, dy)
                    if d < rr + r:
                        d = d or 1.0
                        ox, oy = dx / d, dy / d
                        leaf["x"], leaf["y"] = rx + ox * (rr + r), ry + oy * (rr + r)
                        dot = leaf["vx"] * ox + leaf["vy"] * oy
                        if dot < 0:
                            leaf["vx"] -= 1.5 * dot * ox
                            leaf["vy"] -= 1.5 * dot * oy
                            leaf["w"] += (random.random() - 0.5) * 0.4
                for bump in fx["bumps"]:                  # bouncy mushrooms kick leaves away
                    dx, dy = leaf["x"] - bump["x"], leaf["y"] - bump["y"]
                    d = math.hypot(dx, dy)
                    if d < bump["r"] + r:
                        d = d or 1.0
                        ox, oy = dx / d, dy / d
                        leaf["x"], leaf["y"] = bump["x"] + ox * (bump["r"] + r), bump["y"] + oy * (bump["r"] + r)
                        dot = leaf["vx"] * ox + leaf["vy"] * oy
                        if dot < 0:
                            leaf["vx"] -= 2.0 * dot * ox
                            leaf["vy"] -= 2.0 * dot * oy
                        out = leaf["vx"] * ox + leaf["vy"] * oy
                        if out < 9:
                            leaf["vx"] += (9 - out) * ox
                            leaf["vy"] += (9 - out) * oy
                        leaf["w"] += (random.random() - 0.5) * 0.8
                        if bump["pulse"] < 0.4:
                            bump["pulse"] = 1.0
                            play_at(self.leaf_bump_sound, min(1.0, 0.45 + abs(dot) / 16))
                            self.leaf_burst(leaf["x"], leaf["y"], "#ff9fb8", 3, 3.0)
                if leaf["cd"] <= 0:                       # portals: in one, out the other
                    for portal in fx["portals"]:
                        for i, end in enumerate(portal["ends"]):
                            if math.hypot(leaf["x"] - end["x"], leaf["y"] - end["y"]) < portal["r"] * 0.8:
                                other = portal["ends"][1 - i]
                                sp2 = math.hypot(leaf["vx"], leaf["vy"]) or 1.0
                                ux, uy = leaf["vx"] / sp2, leaf["vy"] / sp2
                                if sp2 < 5:
                                    leaf["vx"], leaf["vy"] = ux * 5, uy * 5
                                self.leaf_burst(end["x"], end["y"], portal["color"], 5, 3.0)
                                leaf["x"], leaf["y"] = other["x"] + ux * (portal["r"] + 8), other["y"] + uy * (portal["r"] + 8)
                                leaf["cd"] = 24
                                portal["pulse"] = 1.0
                                play_at(self.leaf_portal_sound, 0.7)
                                self.leaf_burst(other["x"], other["y"], portal["color"], 5, 3.0)
                                break
                        if leaf["cd"] > 0:
                            break
            else:
                leaf["vx"] = leaf["vy"] = 0.0
            if (state == "play" and leaf["state"] == "on"          # in the bin (even if it was resting there)
                    and zone[0] <= leaf["x"] <= zone[2] and zone[1] <= leaf["y"] <= zone[3]):
                self.leaf_collect(leaf)
            drawn = leaf.get("drawn")
            if leaf["state"] == "on" and (drawn is None or abs(drawn[0] - leaf["x"]) > 0.04
                                          or abs(drawn[1] - leaf["y"]) > 0.04 or abs(drawn[2] - leaf["a"]) > 0.002):
                self.leaf_draw(leaf)
            if leaf["gold"] and leaf["state"] == "on" and random.random() < 0.035:
                self.leaf_burst(leaf["x"], leaf["y"], "#fff3a0", 1, 1.0)          # golden sparkles
            if leaf["gold"] and leaf["state"] == "on" and f % 3 == 0:     # golden leaves glitter
                c.itemconfig(leaf["body"], fill=mix(GOLD_LEAF, "#ffffff", 0.55 * (0.5 + 0.5 * math.sin(f * 0.4 + leaf["a"]))))

        for leaf in finished:
            c.delete(leaf["body"], leaf["rib"])
            lf["leaves"].remove(leaf)
            lf["collected"] += 1
            self.leaf_update_texts()
            if lf["collected"] >= len(lf["p"]["leaves"]) and lf["state"] == "play":
                self.leaf_win()

        if lf["on"] and speed > 16 and f % 3 == 0 and state == "play":      # dust puffs behind a fast broom
            self.leaf_burst(lf["bx"] - lf["hx"] * 10, lf["by"] - lf["hy"] * 10, mix("#9a8a64", THEME["panel_dark"], 0.4), 1, 1.0)
        hot = lf["combo"] >= 3 and f - lf["last_collect"] <= 22              # the broom glows on a combo
        if hot or lf["hot"]:
            c.itemconfig(self.leaf_broom[1], outline=rainbow(self.hue * 6) if hot else "#a8802a", width=3 if hot else 2)
            lf["hot"] = hot
        if pushed and speed > 4 and f - lf["last_sweep"] >= 5:        # the rustle of sweeping
            lf["last_sweep"] = f
            play_at(random.choice(self.leaf_sweeps), min(1.0, 0.25 + speed / 28) * min(1.0, 0.45 + pushed * 0.12))

        for fl in lf["floats"][:]:                                    # "+20 x3" pop-ups
            fl["life"] -= 1
            fl["y"] -= 1.5
            c.coords(fl["item"], fl["x"], fl["y"])
            c.itemconfig(fl["item"], fill=mix(fl["color"], THEME["panel_dark"], 1 - fl["life"] / 30))
            if fl["life"] <= 0:
                c.delete(fl["item"])
                lf["floats"].remove(fl)
        for bit in lf["bits"][:]:                                     # flying specks
            bit["life"] -= 1
            bit["x"] += bit["vx"]
            bit["y"] += bit["vy"]
            bit["vy"] += 0.18
            bit["vx"] *= 0.97
            size = max(0.5, bit["size"] * bit["life"] / bit["max"])
            c.coords(bit["item"], bit["x"] - size, bit["y"] - size, bit["x"] + size, bit["y"] + size)
            if bit["life"] <= 0 or bit["y"] > LF_Y1 + 20:
                c.delete(bit["item"])
                lf["bits"].remove(bit)

        total = max(1, len(lf["p"]["leaves"]))
        c.coords(self.leaf_bar, LF_X0 + 1, 51, LF_X0 + 1 + (LF_X1 - LF_X0 - 2) * lf["collected"] / total, 59)
        c.itemconfig(self.leaf_bar, fill=rainbow(self.hue * 2))
        if f % 6 == 0 and state == "play":
            self.leaf_update_texts()

        if state == "won":
            lf["win_t"] += 1
            if lf["win_t"] == 26:
                self.leaf_show_overlay()
        if self.lf_overlay:
            lf["ov_t"] += 1
            self.leaf_win_title.paint(rainbow(self.hue * 3))
            for i in range(lf["stars"]):          # the stars pop in one by one
                if lf["ov_t"] == 6 + i * 8:
                    c.itemconfig(self.leaf_win_stars[i], fill="#ffcc33", outline="#fff2b0")
                    play(self.leaf_collects[min(i * 2 + 1, len(self.leaf_collects) - 1)])
                    self.ripples.append([self.leaf_win_center + (i - 1) * 56, 232, 5])

    # --- scoring ---
    def leaf_collect(self, leaf):
        lf, c = self.lf, self.canvas
        leaf["state"], leaf["t"] = "in", 0
        lf["combo"] = lf["combo"] + 1 if lf["frame"] - lf["last_collect"] <= 22 else 1
        lf["last_collect"] = lf["frame"]
        combo = lf["combo"]
        points = 10 * min(combo, 8) + (50 if leaf["gold"] else 0)
        lf["score"] += points
        lf["bin_flash"] = 1.0
        play(self.leaf_collects[min(combo - 1, len(self.leaf_collects) - 1)])
        if leaf["gold"]:
            play(self.leaf_gold_sound)
        bx, by, bw, bh = lf["bin"]
        text = f"+{points}" + (f"  x{combo}" if combo >= 3 else "")
        item = self.lf_item("text", bx + bw / 2, by - 6, text=text, fill="#ffffff",
                            font=("Helvetica", 12 + min(combo, 6), "bold"))
        lf["floats"].append({"item": item, "x": bx + bw / 2, "y": by - 6, "life": 30,
                             "color": GOLD_LEAF if (leaf["gold"] or combo >= 3) else "#ffffff"})
        self.leaf_burst(bx + bw / 2, by + bh / 2, leaf["color"], 6 if not leaf["gold"] else 12, 3.2)
        if lf["pile"] < 40:                      # the bin slowly fills up with leaves
            lf["pile"] += 1
            px, py = random.uniform(bx + 18, bx + bw - 18), random.uniform(by + 18, by + bh - 18)
            ang, sz = random.uniform(0, math.tau), random.uniform(5.5, 7.5)
            pts = []
            for qx, qy in LEAF_SHAPE:
                pts += [px + (qx * math.cos(ang) - qy * math.sin(ang)) * sz, py + (qx * math.sin(ang) + qy * math.cos(ang)) * sz]
            lf["bin_items"].append(self.lf_item("polygon", *pts, smooth=True, fill=mix(leaf["color"], "#000000", 0.2), outline=""))

    def leaf_burst(self, x, y, color, count, power):
        lf = self.lf
        for _ in range(count):
            if len(lf["bits"]) >= 80:
                return
            angle, speed = random.uniform(0, math.tau), random.uniform(0.4, 1.0) * power
            size = random.uniform(2.0, 3.6)
            life = random.randint(14, 24)
            item = self.lf_item("oval", x, y, x + 1, y + 1, fill=color, outline="")
            lf["bits"].append({"item": item, "x": x, "y": y, "vx": math.cos(angle) * speed,
                               "vy": math.sin(angle) * speed - 1.2, "life": life, "max": life, "size": size})

    def leaf_win(self):
        lf = self.lf
        lf["state"], lf["win_t"] = "won", 0
        lf["elapsed"] = time.time() - lf["t0"]
        lf["stars"] = leaf_stars(lf["p"]["par"], lf["elapsed"])
        level = lf["level"]
        self.lf_stars[level] = max(self.lf_stars.get(level, 0), lf["stars"])
        self.lf_done = max(self.lf_done, level)
        save_leaf_progress(self.lf_done, self.lf_stars)
        tenths = max(30, int(lf["elapsed"] * 10))
        lf["new_best"] = self.leaf_board_update(self.my_fp, level, tenths) if self.my_fp in ROSTER else False
        if lf["new_best"]:
            save_leaf_board(self.lboard)
            self.post_leaf_score(level, tenths)
        play(self.leaf_win_sound)
        for _ in range(8):
            self.ripples.append([random.randint(LF_X0, LF_X1), random.randint(LF_Y0, LF_Y1), 5])
        for _ in range(34):                       # leaves rain down
            x = random.uniform(LF_X0, LF_X1)
            self.leaf_burst(x, LF_Y0 + 4, random.choice(LEAF_COLORS + [GOLD_LEAF]), 1, 1.0)
        self.canvas.itemconfig(self.status, text=f"Level {level} clear! {lf['stars']} star{'s' if lf['stars'] != 1 else ''}")
        if level % 10 == 0:                       # tell the server about milestones
            self.bot.post(f"\U0001F342 **{self.username}** just cleared Leaf Sweep level {level}!",
                          getattr(self.bot, "channel_id", 0))

    def leaf_show_overlay(self):
        lf, c = self.lf, self.canvas
        self.lf_overlay = True
        self.leaf_win_center = (LF_X0 + LF_X1) / 2
        c.itemconfig("leafwin", state="normal")
        last = lf["level"] >= LEAF_LEVELS
        self.leaf_win_title.set_text("ALL CLEAR!!!" if last else "LEVEL CLEAR!")
        for item in self.buttons["LEAF_WIN_NEXT"]["items"]:
            c.itemconfig(item, state="hidden" if last else "normal")
        for item in self.leaf_win_stars:
            c.itemconfig(item, fill="#3a3a4a", outline="#555570")
        seconds = int(lf["elapsed"])
        c.itemconfig(self.leaf_win_info, text=f"time {seconds // 60}:{seconds % 60:02d}   •   score {lf['score']}")
        par = int(lf["p"]["par"])
        c.itemconfig(self.leaf_win_best, text=f"3 stars if under {par // 60}:{par % 60:02d}")
        for key in ("LEAF_WIN_NEXT", "LEAF_WIN_REPLAY", "LEAF_WIN_MENU"):    # the buttons pop in
            b = self.buttons[key]
            b["scale"], b["kick"], b["sig"] = 0.5, 0.0, None
        lf["ov_t"] = 0

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
            if not (page == self.page or page == "chaticon" or (page == "chat" and self.chat_open)
                    or (page == "leafwin" and self.lf_overlay)):
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
        was_leaves = self.page == "leaves"
        self.page = name
        for page in ("home", "menu", "names", "sudoku", "themes", "board", "leaves"):
            self.canvas.itemconfig(page, state="normal" if page == name else "hidden")
        self.clear_hover()
        if was_leaves and name != "leaves":
            self.leaf_leave()
        if name == "leaves":
            self.leaf_enter()
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
        if self.page == "leaves" and self.lf:
            self.leaf_tick()

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
