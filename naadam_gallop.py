#!/usr/bin/env python3
"""
Naadam Gallop - Mongolian Naadam horse race (side-scrolling), Python + pygame.

Run on a laptop (keyboard):      python3 naadam_gallop.py
Run on Raspberry Pi 5 (GPIO):    python3 naadam_gallop.py --gpio --fullscreen
Self-test of the game logic:     python3 naadam_gallop.py --selftest

Keyboard:  UP/W = jump   DOWN/S = duck   SPACE/Z = whip (boost)   P/X = pause   ESC = quit
The game always renders on a 240x240 surface and scales it to the window,
so it looks the same on a small joystick display or on a laptop screen.
"""
import argparse
import math
import random
import sys

W = H = 240
PX = 40                      # player's fixed x on screen
PW = 26                      # player hitbox width
GROUND = 196                 # player's ground line (y)
GRAVITY = 750.0
JUMP_V = -280.0

# stage: name, base speed px/s, track length px, rival bonus, gap range, obstacle kinds
STAGES = [
    dict(name="GRASSLAND", speed=115, length=2600, rival=0.00, gap=(170, 270),
         kinds=["rock", "rock", "fence"],
         sky=(120, 190, 240), far=(110, 150, 170), near=(90, 160, 90), ground=(70, 140, 60)),
    dict(name="GOBI DESERT", speed=130, length=3000, rival=0.03, gap=(140, 230),
         kinds=["rock", "fence", "bird"],
         sky=(240, 200, 140), far=(200, 150, 100), near=(215, 175, 105), ground=(205, 165, 95)),
    dict(name="MOUNTAINS", speed=145, length=3400, rival=0.05, gap=(115, 190),
         kinds=["rock", "fence", "bird", "bird"],
         sky=(70, 90, 140), far=(80, 90, 120), near=(70, 100, 80), ground=(55, 85, 60)),
]
N_RIVALS = 3
RIVAL_LANES = [178, 187, 209]    # ground y of rival horses
RIVAL_COLORS = [(150, 90, 40), (60, 40, 30), (210, 210, 200)]

OBST = {                     # w, h, y_bottom_offset (height above ground)
    "rock":  (12, 12, 0),
    "fence": (10, 18, 0),
    "bird":  (12, 8, 22),
}


class Obstacle:
    def __init__(self, kind, x):
        self.kind, self.x = kind, x
        self.w, self.h, self.lift = OBST[kind]

    def rect_screen(self, dist):
        sx = PX + (self.x - dist)
        top = GROUND - self.lift - self.h
        return sx, top, self.w, self.h


class Rival:
    def __init__(self, lane, color, stage):
        self.lane, self.color = lane, color
        self.dist = 0.0
        self.factor = 1.0
        self.timer = 0.0
        self.bonus = stage["rival"]

    def update(self, dt, base):
        self.timer -= dt
        if self.timer <= 0:
            self.factor = 0.96 + self.bonus + random.random() * 0.07
            self.timer = 1.0 + random.random()
        self.dist += base * self.factor * dt


class Inputs:
    """Held state + edge-triggered presses. Filled by keyboard or GPIO."""
    def __init__(self):
        self.up = self.down = self.a = self.b = False
        self._pa = self._pb = False
        self.a_pressed = self.b_pressed = False

    def set(self, up, down, a, b):
        self.up, self.down = up, down
        self.a_pressed = a and not self._pa
        self.b_pressed = b and not self._pb
        self.a, self.b = a, b
        self._pa, self._pb = a, b


class Game:
    TITLE, COUNTDOWN, RACE, FINISH, ALLCLEAR = range(5)

    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.state = self.TITLE
        self.stage_i = 0
        self.total_time = 0.0
        self.paused = False
        self.t = 0.0                 # animation clock
        self.rank = 1
        self.won = False

    # ---------- setup ----------
    def start_stage(self):
        st = STAGES[self.stage_i]
        self.stage = st
        self.dist = 0.0
        self.y = 0.0                 # height above ground
        self.vy = 0.0
        self.ducking = False
        self.stamina = 100.0
        self.exhausted = False
        self.boosting = False
        self.slow_t = 0.0
        self.invul_t = 0.0
        self.race_time = 0.0
        self.rivals = [Rival(RIVAL_LANES[i], RIVAL_COLORS[i], st) for i in range(N_RIVALS)]
        for r in self.rivals:
            r.timer = 0
        self.obstacles = []
        x = 420.0
        while x < st["length"] - 250:
            self.obstacles.append(Obstacle(self.rng.choice(st["kinds"]), x))
            x += self.rng.uniform(*st["gap"])
        self.state = self.COUNTDOWN
        self.cd = 3.0

    @property
    def on_ground(self):
        return self.y <= 0.0

    # ---------- helpers ----------
    def speed(self):
        s = self.stage["speed"]
        if self.boosting:
            s *= 1.35
        if self.slow_t > 0:
            s *= 0.45
        return s

    def player_rect(self):
        h = 16 if self.ducking else 26
        return PX, GROUND - self.y - h, PW, h

    def current_rank(self):
        return 1 + sum(1 for r in self.rivals if r.dist > self.dist)

    # ---------- update ----------
    def update(self, dt, inp):
        self.t += dt
        if self.state == self.TITLE:
            if inp.a_pressed or inp.b_pressed:
                self.stage_i, self.total_time = 0, 0.0
                self.start_stage()
        elif self.state == self.COUNTDOWN:
            self.cd -= dt
            if self.cd <= -0.6:
                self.state = self.RACE
        elif self.state == self.RACE:
            if inp.b_pressed:
                self.paused = not self.paused
            if not self.paused:
                self.update_race(dt, inp)
        elif self.state == self.FINISH:
            self.fin_t -= dt
            self.dist += self.stage["speed"] * 0.5 * dt
            for r in self.rivals:
                r.update(dt, self.stage["speed"])
            if self.fin_t <= 0:
                if self.won:
                    self.stage_i += 1
                    if self.stage_i >= len(STAGES):
                        self.state = self.ALLCLEAR
                    else:
                        self.start_stage()
                else:
                    self.start_stage()      # retry same stage
        elif self.state == self.ALLCLEAR:
            if inp.a_pressed or inp.b_pressed:
                self.state = self.TITLE

    def update_race(self, dt, inp):
        base = self.stage["speed"]
        self.race_time += dt

        # jump / duck
        self.ducking = inp.down and self.on_ground
        if inp.up and self.on_ground and not self.ducking:
            self.vy = -JUMP_V          # upward velocity (positive = up)
            self.y = 0.001
        if not self.on_ground:
            self.vy -= GRAVITY * dt
            self.y += self.vy * dt
            if self.y <= 0:
                self.y, self.vy = 0.0, 0.0

        # stamina / boost
        want = inp.a and not self.exhausted
        self.boosting = want and self.stamina > 0
        if self.boosting:
            self.stamina -= 32 * dt
            if self.stamina <= 0:
                self.stamina, self.exhausted = 0.0, True
        else:
            self.stamina = min(100.0, self.stamina + 11 * dt)
            if self.exhausted and self.stamina >= 25:
                self.exhausted = False

        # timers
        self.slow_t = max(0.0, self.slow_t - dt)
        self.invul_t = max(0.0, self.invul_t - dt)

        # movement
        self.dist += self.speed() * dt
        for r in self.rivals:
            r.update(dt, base)

        # collisions
        if self.invul_t <= 0:
            px, py, pw, ph = self.player_rect()
            for o in self.obstacles:
                ox, oy, ow, oh = o.rect_screen(self.dist)
                if ox > W or ox + ow < 0:
                    continue
                if px < ox + ow and px + pw > ox and py < oy + oh and py + ph > oy:
                    self.slow_t, self.invul_t = 0.8, 1.3
                    break

        # finish
        if self.dist >= self.stage["length"]:
            self.rank = self.current_rank()
            self.won = self.rank == 1
            self.total_time += self.race_time
            self.state = self.FINISH
            self.fin_t = 2.8


# =====================================================================
#  Rendering (pygame) - imported lazily so the logic can be tested without it
# =====================================================================
def draw_horse(pg, s, x, gy, col, t, rider, ducking=False, air=False):
    dark = tuple(max(0, c - 40) for c in col)
    pg.draw.rect(s, col, (x, gy - 19, 22, 9))                      # body
    pg.draw.polygon(s, col, [(x + 18, gy - 19), (x + 24, gy - 28), (x + 28, gy - 25), (x + 22, gy - 15)])  # neck
    pg.draw.rect(s, col, (x + 24, gy - 29, 8, 5))                  # head
    pg.draw.rect(s, dark, (x - 5, gy - 19, 5, 3))                  # tail
    ph = int(t * 12) % 2
    if air:
        legs = [(x + 1, gy - 10, -4, 6), (x + 5, gy - 10, -2, 7), (x + 16, gy - 10, 5, 6), (x + 19, gy - 10, 6, 5)]
    elif ph:
        legs = [(x + 1, gy - 10, -3, 10), (x + 5, gy - 10, 1, 10), (x + 16, gy - 10, 3, 10), (x + 19, gy - 10, -1, 10)]
    else:
        legs = [(x + 1, gy - 10, 2, 10), (x + 5, gy - 10, -2, 10), (x + 16, gy - 10, -2, 10), (x + 19, gy - 10, 3, 10)]
    for lx, ly, dx, ln in legs:
        pg.draw.line(s, dark, (lx, ly), (lx + dx, ly + ln), 2)
    ry = gy - 26 + (5 if ducking else 0)                           # rider
    pg.draw.rect(s, rider, (x + 8, ry, 6, 8))
    pg.draw.circle(s, (240, 200, 160), (x + 11, ry - 3), 3)
    pg.draw.rect(s, (200, 40, 40), (x + 8, ry - 7, 6, 2))          # hat


def render(pg, s, g, font, big):
    if g.state == Game.TITLE or g.state == Game.ALLCLEAR and False:
        st = STAGES[0]
    else:
        st = g.stage if hasattr(g, "stage") else STAGES[0]
    dist = g.dist if hasattr(g, "dist") else g.t * 60
    s.fill(st["sky"])
    pg.draw.circle(s, (255, 240, 170), (190, 40), 16)
    for i in range(4):                                             # clouds
        cx = (i * 90 - dist * 0.1) % (W + 80) - 40
        pg.draw.ellipse(s, (255, 255, 255), (cx, 30 + (i % 2) * 25, 40, 12))
    off = dist * 0.25                                              # far hills
    pts = [(0, 170)] + [(x, 150 - 22 * abs(math.sin((x + off) / 38.0))) for x in range(0, W + 8, 8)] + [(W, 170)]
    pg.draw.polygon(s, st["far"], pts)
    off = dist * 0.5                                               # near hills
    pts = [(0, 175)] + [(x, 165 - 10 * abs(math.sin((x + off) / 23.0))) for x in range(0, W + 8, 8)] + [(W, 175)]
    pg.draw.polygon(s, st["near"], pts)
    pg.draw.rect(s, st["ground"], (0, 172, W, H - 172))
    for i in range(10):                                            # ground stripes
        gx = (i * 30 - dist) % (W + 30) - 15
        pg.draw.line(s, tuple(max(0, c - 18) for c in st["ground"]), (gx, 200 + (i % 3) * 12), (gx + 14, 200 + (i % 3) * 12), 1)

    if g.state == Game.TITLE:
        draw_horse(pg, s, 100, 170, (150, 90, 40), g.t, (30, 90, 200))
        txt(pg, s, big, "NAADAM", W // 2, 40, (255, 255, 255))
        txt(pg, s, big, "GALLOP", W // 2, 66, (255, 220, 80))
        if int(g.t * 2) % 2 == 0:
            txt(pg, s, font, "PRESS A TO START", W // 2, 210, (255, 255, 255))
        return
    if g.state == Game.ALLCLEAR:
        txt(pg, s, big, "ALL CLEAR!", W // 2, 70, (255, 220, 80))
        txt(pg, s, font, "TOTAL TIME %.1f s" % g.total_time, W // 2, 110, (255, 255, 255))
        txt(pg, s, font, "PRESS A", W // 2, 210, (255, 255, 255))
        return

    fx = PX + (st["length"] - dist)                                # finish line
    if -10 < fx < W:
        for i in range(0, 60, 6):
            pg.draw.rect(s, (255, 255, 255) if (i // 6) % 2 else (20, 20, 20), (fx, 172 + i, 6, 6))
    for o in g.obstacles:
        ox, oy, ow, oh = o.rect_screen(dist)
        if ox > W or ox + ow < -4:
            continue
        if o.kind == "rock":
            pg.draw.ellipse(s, (120, 120, 120), (ox, oy, ow, oh))
        elif o.kind == "fence":
            pg.draw.rect(s, (110, 70, 30), (ox, oy, ow, oh))
            pg.draw.rect(s, (150, 100, 50), (ox - 2, oy + 4, ow + 4, 3))
        else:
            wing = 3 if int(g.t * 10) % 2 else -3
            pg.draw.polygon(s, (40, 40, 40), [(ox, oy + 4), (ox + 6, oy + 4 + wing), (ox + 12, oy + 4), (ox + 6, oy + 7)])

    for r in g.rivals:                                             # rivals
        rx = PX + (r.dist - g.dist)
        if -40 < rx < W + 10:
            draw_horse(pg, s, rx, r.lane, r.color, g.t + r.lane, (110, 110, 110))
    if g.invul_t <= 0 or int(g.t * 14) % 2:                        # player (blinks when hit)
        draw_horse(pg, s, PX, GROUND - g.y, (150, 90, 40), g.t, (30, 90, 200), g.ducking, not g.on_ground)

    # HUD
    txt(pg, s, font, "RANK %d/%d" % (g.current_rank(), N_RIVALS + 1), 38, 8, (255, 255, 255))
    txt(pg, s, font, st["name"], W // 2 + 10, 8, (255, 255, 255))
    txt(pg, s, font, "%.1fs" % g.race_time, W - 24, 8, (255, 255, 255))
    pg.draw.rect(s, (30, 30, 30), (8, 20, 224, 4))
    pg.draw.rect(s, (255, 220, 80), (8, 20, 224 * min(1.0, g.dist / st["length"]), 4))
    pg.draw.rect(s, (30, 30, 30), (8, 228, 70, 6))
    pg.draw.rect(s, (200, 60, 60) if g.exhausted else (80, 200, 255), (8, 228, 70 * g.stamina / 100.0, 6))
    txt(pg, s, font, "STAMINA", 94, 231, (255, 255, 255))

    if g.state == Game.COUNTDOWN:
        label = str(int(math.ceil(g.cd))) if g.cd > 0 else "GO!"
        txt(pg, s, big, label, W // 2, 100, (255, 255, 255))
    elif g.state == Game.FINISH:
        txt(pg, s, big, "WINNER!" if g.won else "RETRY", W // 2, 90, (255, 220, 80) if g.won else (255, 120, 120))
        txt(pg, s, font, "RANK %d" % g.rank, W // 2, 120, (255, 255, 255))
    elif g.paused:
        txt(pg, s, big, "PAUSE", W // 2, 100, (255, 255, 255))


def txt(pg, s, font, text, cx, cy, color):
    img = font.render(text, False, color)
    s.blit(img, img.get_rect(center=(cx, cy)))


# =====================================================================
#  Input sources
# =====================================================================
class GpioInput:
    """Raspberry Pi 5: gpiozero (lgpio backend). Change the pin numbers to match your wiring."""
    PINS = dict(up=5, down=6, a=13, b=19)    # BCM numbers, buttons wired to GND (pull-up)

    def __init__(self):
        from gpiozero import Button
        self.btn = {k: Button(p, pull_up=True) for k, p in self.PINS.items()}

    def read(self):
        b = self.btn
        return b["up"].is_pressed, b["down"].is_pressed, b["a"].is_pressed, b["b"].is_pressed


def keyboard_read(pg):
    k = pg.key.get_pressed()
    return (k[pg.K_UP] or k[pg.K_w], k[pg.K_DOWN] or k[pg.K_s],
            k[pg.K_SPACE] or k[pg.K_z], k[pg.K_p] or k[pg.K_x])


def run(args):
    import pygame as pg
    pg.init()
    flags = pg.FULLSCREEN if args.fullscreen else 0
    size = (W * args.scale, H * args.scale)
    screen = pg.display.set_mode(size, flags)
    pg.display.set_caption("Naadam Gallop")
    pg.mouse.set_visible(False)
    surf = pg.Surface((W, H))
    font = pg.font.Font(None, 16)
    big = pg.font.Font(None, 34)
    gpio = GpioInput() if args.gpio else None
    game, inp, clock = Game(), Inputs(), pg.time.Clock()
    while True:
        dt = min(clock.tick(60) / 1000.0, 0.05)
        for e in pg.event.get():
            if e.type == pg.QUIT or (e.type == pg.KEYDOWN and e.key == pg.K_ESCAPE):
                pg.quit()
                return
        inp.set(*(gpio.read() if gpio else keyboard_read(pg)))
        game.update(dt, inp)
        render(pg, surf, game, font, big)
        pg.transform.scale(surf, size, screen)
        pg.display.flip()


# =====================================================================
#  Headless self-test: a bot plays the whole game using only the logic
# =====================================================================
def bot_inputs(g):
    up = down = a = False
    px, _, pw, _ = g.player_rect()
    for o in g.obstacles:
        ox, oy, ow, oh = o.rect_screen(g.dist)
        gap = ox - (PX + PW)
        if o.kind == "bird":
            if gap < 45 and ox + ow > PX - 4:
                down = True
        elif 0 < gap <= 22 and g.on_ground:
            up = True
        if gap > 60:
            break
    a = g.stamina > 40 and g.slow_t <= 0
    return up, down, a


def selftest():
    random.seed(1)
    g, inp = Game(seed=1), Inputs()
    inp.set(False, False, True, False)
    g.update(1 / 60, inp)                    # press A on title
    assert g.state == Game.COUNTDOWN
    log, t = [], 0.0
    logged = False
    while t < 900 and g.state != Game.ALLCLEAR:
        if g.state != Game.FINISH:
            logged = False
        up, down, a = bot_inputs(g)
        inp.set(up, down, a, False)
        g.update(1 / 60, inp)
        t += 1 / 60
        if g.state == Game.FINISH and not logged:
            logged = True
            log.append("stage %d: rank %d at %.1fs -> %s" % (g.stage_i + 1, g.rank, g.race_time, "WIN" if g.won else "retry"))
    for l in log:
        print(l)
    assert g.state == Game.ALLCLEAR, "bot never finished the game"
    print("ALL CLEAR in %.1fs total race time (sim %.0fs)" % (g.total_time, t))

    # rules checks
    g2 = Game(seed=2); g2.stage_i = 0; g2.start_stage(); g2.state = Game.RACE
    g2.obstacles = [Obstacle("rock", g2.dist + 2)]
    i2 = Inputs(); i2.set(False, False, False, False)
    g2.update(1 / 60, i2)
    assert g2.slow_t > 0, "collision not detected"
    g2.start_stage(); g2.state = Game.RACE
    g2.obstacles = [Obstacle("bird", g2.dist + 2)]
    i2.set(False, True, False, False); g2.update(1 / 60, i2)
    assert g2.slow_t == 0, "ducking should avoid a bird"
    print("rule checks OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpio", action="store_true", help="read joystick/buttons through GPIO (Raspberry Pi)")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--scale", type=int, default=3, help="window size = 240 x scale (default 3 = 720px)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    else:
        run(a)
