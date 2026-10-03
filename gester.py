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
import colorsys, math, random, os, sys, json, asyncio, threading

# ---------- SETTINGS (change these to experiment!) ----------
WIDTH, HEIGHT = 720, 480
BACKGROUND = "#0d0d14"
NORMAL_SPEED = 0.004      # how fast the rainbow cycles
PARTY_SPEED = 0.02        # rainbow speed in Party Mode
NUM_PARTICLES = 40
NUM_JESTERS = 6
VERSION = "1.0.0"          # change this each update so you can see it worked

HOVER_SOUND = "hover.wav"
CLICK_SOUND = "click.wav"
JESTER_SOUND = "jester.wav"
PARTY_SONG = "party_song.mp3"
# -------------------------------------------------------------

# The folder Gester lives in (works for both gester.py and the packaged .exe)
if getattr(sys, "frozen", False):
    HERE = os.path.dirname(sys.executable)
else:
    HERE = os.path.dirname(os.path.abspath(__file__))

# Files bundled inside the .exe get unpacked here
BUNDLE = getattr(sys, "_MEIPASS", HERE)


def find_file(filename):
    """Look next to the program first, then inside the bundled .exe."""
    for folder in (HERE, BUNDLE):
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            return path
    return None

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


def rainbow(hue, saturation=0.8, brightness=1.0):
    """Turn a number (0 to 1) into a rainbow color like '#ff00aa'."""
    r, g, b = colorsys.hsv_to_rgb(hue % 1.0, saturation, brightness)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


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
        if discord is None:
            self.problem = "discord.py not found by this Python (see terminal)"
            return
        try:
            with open(find_file("config.json")) as f:
                config = json.load(f)
            self.token = config["token"]
            self.channel_id = int(config["channel_id"])
        except Exception:
            self.problem = "config.json is missing or wrong (see top of gester.py)"
            return
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.client = discord.Client(intents=discord.Intents.default())

        @self.client.event
        async def on_ready():
            self.ready = True

        try:
            self.loop.run_until_complete(self.client.start(self.token))
        except Exception as error:
            self.ready = False
            self.problem = f"bot error: {error}"

    def send(self, text):
        """Send a message to the channel. Returns a 'future' we can check later."""
        async def go():
            channel = self.client.get_channel(self.channel_id)
            if channel is None:
                channel = await self.client.fetch_channel(self.channel_id)
            await channel.send(text)
        return asyncio.run_coroutine_threadsafe(go(), self.loop)


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
                                bg=BACKGROUND, highlightthickness=0)
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
        self.spinning = False
        self.bot = DiscordLink()

        self.hover_sound = load_sound(HOVER_SOUND, 0.5)
        self.click_sound = load_sound(CLICK_SOUND)
        self.jester_sound = load_sound(JESTER_SOUND)

        # Things created first are drawn at the back, so order matters here.
        self.buttons = {}
        self.make_particles()
        self.make_jesters()
        self.make_bar()
        self.make_home_page()
        self.make_menu_page()
        self.make_names_page()
        self.refresh_names()

        self.status = self.canvas.create_text(
            WIDTH / 2, 455, text="Welcome to Gester!",
            fill="#8888aa", font=("Helvetica", 12))

        self.canvas.create_text(WIDTH - 10, HEIGHT - 8, anchor="se", text=f"v{VERSION}",
                                fill="#444460", font=("Helvetica", 9))

        self.show_page("home")
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)
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
                 ("TEAM SPLITTER (soon)", self.coming_soon),
                 ("GAME NIGHT PING (soon)", self.coming_soon)]
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
        for i, name in enumerate(self.names[:9]):
            item = c.create_text(70, 168 + i * 25, anchor="w", text=f"\u2022  {name[:22]}",
                                 fill="white", font=("Helvetica", 13), tags=("names", "chip"))
            c.tag_bind(item, "<Button-1>", lambda e, n=i: self.remove_name(n))
            c.tag_bind(item, "<Enter>", lambda e: c.config(cursor="hand2"))
            c.tag_bind(item, "<Leave>", lambda e: c.config(cursor=""))
        if len(self.names) > 9:
            c.create_text(70, 168 + 9 * 25, anchor="w", text=f"...and {len(self.names) - 9} more",
                          fill="#6a6a88", font=("Helvetica", 11), tags=("names", "chip"))

    def add_name(self):
        name = self.entry.get().strip()
        if name:
            self.names.append(name)
            save_names(self.names)
            self.entry.delete(0, "end")
            self.refresh_names()
            self.canvas.itemconfig(self.status, text=f"Added {name}")

    def remove_name(self, index):
        if not self.spinning and index < len(self.names):
            removed = self.names.pop(index)
            save_names(self.names)
            self.canvas.config(cursor="")
            self.refresh_names()
            self.canvas.itemconfig(self.status, text=f"Removed {removed}")

    def clear_names(self):
        if not self.spinning:
            self.names.clear()
            save_names(self.names)
            self.refresh_names()
            self.canvas.itemconfig(self.result_text, text="?")

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
        self.buttons[key] = {"box": box, "action": action}
        for item in (box, text):
            self.bind_button(item, key)

    def bind_button(self, item, key):
        self.canvas.tag_bind(item, "<Enter>", lambda e: self.on_hover(key))
        self.canvas.tag_bind(item, "<Leave>", lambda e: self.on_leave())
        self.canvas.tag_bind(item, "<Button-1>", lambda e: self.on_click(e, key))

    def show_page(self, name):
        """Show one page and hide the other."""
        self.page = name
        for page in ("home", "menu", "names"):
            self.canvas.itemconfig(page, state="normal" if page == name else "hidden")
        self.clear_hover()
        if name == "names":
            self.entry.focus_set()

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
        self.canvas.itemconfig(self.result_text, fill=rainbow(self.hue * 4))

        # buttons glow with the rainbow when hovered
        for key, b in self.buttons.items():
            if key == self.hovered:
                self.canvas.itemconfig(b["box"], outline=rainbow(self.hue * 3), fill="#1e1e30")
            else:
                self.canvas.itemconfig(b["box"], outline="#333344", fill="#161622")


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