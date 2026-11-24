#!/usr/bin/env python3
"""
import argparse
import math
import os

W = H = 240
PX = 40
GROUND = 196
GRAVITY = 750.0
JUMP_V = 280.0
RUN_SPEED = 115.0
SKY, FAR, NEAR, GRASS = (120, 190, 240), (110, 150, 170), (90, 160, 90), (70, 140, 60)


class Inputs:
    def __init__(self):
        self.up = self.down = self.a = False
        self._pa = False
        self.a_pressed = False

    def set(self, up, down, a):
        self.up, self.down = up, down
        self.a_pressed = a and not self._pa
        self.a, self._pa = a, a


class Game:
    TITLE, RUN = range(2)

    def __init__(self):
        self.state = self.TITLE
        self.t = 0.0
        self.dist = 0.0
        self.y = 0.0
        self.vy = 0.0
        self.ducking = False

    @property
    def on_ground(self):
        return self.y <= 0.0

    def update(self, dt, inp):
        self.t += dt
        if self.state == self.TITLE:
            self.dist += RUN_SPEED * 0.3 * dt
            if inp.a_pressed:
                self.state = self.RUN
                self.dist = 0.0
            return
        self.dist += RUN_SPEED * dt
        self.ducking = inp.down and self.on_ground
        if inp.up and self.on_ground and not self.ducking:
            self.vy = JUMP_V
            self.y = 0.001
        if not self.on_ground:
            self.vy -= GRAVITY * dt
            self.y += self.vy * dt
            if self.y <= 0:
                self.y, self.vy = 0.0, 0.0


# ------------------------- drawing -------------------------
def txt(pg, s, font, text, cx, cy, color):
    img = font.render(text, False, color)
    s.blit(img, img.get_rect(center=(cx, cy)))


def draw_horse(pg, s, x, gy, t, ducking=False, air=False):
    col, dark = (150, 90, 40), (110, 50, 0)
    pg.draw.rect(s, col, (x, gy - 19, 22, 9))
    pg.draw.polygon(s, col, [(x + 18, gy - 19), (x + 24, gy - 28), (x + 28, gy - 25), (x + 22, gy - 15)])
    pg.draw.rect(s, col, (x + 24, gy - 29, 8, 5))
    pg.draw.rect(s, dark, (x - 5, gy - 19, 5, 3))
    if air:
        legs = [(x + 1, -4, 6), (x + 5, -2, 7), (x + 16, 5, 6), (x + 19, 6, 5)]
    elif int(t * 12) % 2:
        legs = [(x + 1, -3, 10), (x + 5, 1, 10), (x + 16, 3, 10), (x + 19, -1, 10)]
    else:
        legs = [(x + 1, 2, 10), (x + 5, -2, 10), (x + 16, -2, 10), (x + 19, 3, 10)]
    for lx, dx, ln in legs:
        pg.draw.line(s, dark, (lx, gy - 10), (lx + dx, gy - 10 + ln), 2)
    ry = gy - 26 + (5 if ducking else 0)
    pg.draw.rect(s, (30, 90, 200), (x + 8, ry, 6, 8))
    pg.draw.circle(s, (240, 200, 160), (x + 11, ry - 3), 3)
    pg.draw.rect(s, (200, 40, 40), (x + 8, ry - 7, 6, 2))


def render(pg, s, g, font, big):
    dist = g.dist
    s.fill(SKY)
    pg.draw.circle(s, (255, 240, 170), (190, 40), 16)
    for i in range(4):
        cx = (i * 90 - dist * 0.1) % (W + 80) - 40
        pg.draw.ellipse(s, (255, 255, 255), (cx, 30 + (i % 2) * 25, 40, 12))
    off = dist * 0.25
    pts = [(0, 170)] + [(x, 150 - 22 * abs(math.sin((x + off) / 38.0))) for x in range(0, W + 8, 8)] + [(W, 170)]
    pg.draw.polygon(s, FAR, pts)
    off = dist * 0.5
    pts = [(0, 175)] + [(x, 165 - 10 * abs(math.sin((x + off) / 23.0))) for x in range(0, W + 8, 8)] + [(W, 175)]
    pg.draw.polygon(s, NEAR, pts)
    pg.draw.rect(s, GRASS, (0, 172, W, H - 172))
    for i in range(10):
        gx = (i * 30 - dist) % (W + 30) - 15
        gy = 200 + (i % 3) * 12
        pg.draw.line(s, (52, 122, 42), (gx, gy), (gx + 14, gy), 1)

    if g.state == Game.TITLE:
        draw_horse(pg, s, 100, 170, g.t)
        txt(pg, s, big, "NAADAM", W // 2, 40, (255, 255, 255))
        txt(pg, s, big, "GALLOP", W // 2, 66, (255, 220, 80))
        if int(g.t * 2) % 2 == 0:
            txt(pg, s, font, "PRESS A TO START", W // 2, 215, (255, 255, 255))
    else:
        draw_horse(pg, s, PX, GROUND - g.y, g.t, g.ducking, not g.on_ground)
        txt(pg, s, font, "UP=JUMP  DOWN=DUCK", W // 2, 10, (255, 255, 255))


# ------------------------- inputs -------------------------
class GpioInput:
    """Adafruit 1.3in bonnet: UP=17, DOWN=22, A=5 (pressed = LOW)."""
    PINS = dict(up=17, down=22, a=5)

    def __init__(self):
        from gpiozero import InputDevice
        self.dev = {k: InputDevice(p, pull_up=True) for k, p in self.PINS.items()}

    def read(self):
        d = self.dev
        return d["up"].is_active, d["down"].is_active, d["a"].is_active


def keyboard_read(pg):
    k = pg.key.get_pressed()
    return (k[pg.K_UP] or k[pg.K_w], k[pg.K_DOWN] or k[pg.K_s], k[pg.K_SPACE] or k[pg.K_z])


def run(args):
    if args.lcd:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    import pygame as pg
    pg.init()
    surf = pg.Surface((W, H))
    font = pg.font.Font(None, 16)
    big = pg.font.Font(None, 34)

    lcd = screen = None
    size = (W * args.scale, H * args.scale)
    if args.lcd:
        import st7789
        from PIL import Image
        lcd = st7789.ST7789(port=0, cs=0, dc=25, backlight=26, width=240, height=240,
                            rotation=90, spi_speed_hz=40000000, offset_left=0, offset_top=0)
        lcd.begin()
    else:
        screen = pg.display.set_mode(size, pg.FULLSCREEN if args.fullscreen else 0)
        pg.display.set_caption("Naadam Gallop")

    gpio = GpioInput() if (args.gpio or args.lcd) else None
    game, inp, clock = Game(), Inputs(), pg.time.Clock()
    try:
        while True:
            dt = min(clock.tick(30) / 1000.0, 0.05)
            for e in pg.event.get():
                if e.type == pg.QUIT or (e.type == pg.KEYDOWN and e.key == pg.K_ESCAPE):
                    return
            inp.set(*(gpio.read() if gpio else keyboard_read(pg)))
            game.update(dt, inp)
            render(pg, surf, game, font, big)
            if lcd:
                lcd.display(Image.frombytes("RGB", (W, H), pg.image.tobytes(surf, "RGB")))
            else:
                pg.transform.scale(surf, size, screen)
                pg.display.flip()
    except KeyboardInterrupt:
        pass
    finally:
        pg.quit()


def selftest():
    g, inp = Game(), Inputs()
    inp.set(False, False, True)
    g.update(1 / 60, inp)
    assert g.state == Game.RUN
    inp.set(True, False, False)
    peak = 0.0
    for _ in range(120):
        g.update(1 / 60, inp)
        peak = max(peak, g.y)
    assert peak > 20, "horse did not jump"
    inp.set(False, True, False)
    g.update(1 / 60, inp)
    assert g.ducking or not g.on_ground
    print("selftest OK, jump peak = %.1f px" % peak)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpio", action="store_true", help="joystick/buttons via GPIO")
    ap.add_argument("--lcd", action="store_true", help="draw on the Adafruit 1.3in bonnet (implies --gpio)")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--scale", type=int, default=3)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    selftest() if a.selftest else run(a)
