"""Generate the toolbar icons of the add-in (pure Python, no Pillow needed).

    python tools/make_icons.py
"""

import os
import struct
import zlib

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'SWMates', 'resources')
SIZES = [16, 32, 64]
SS = 4  # supersampling per axis

BLUE = (38, 120, 210, 255)
GRAY = (150, 156, 166, 255)
DARK = (55, 60, 70, 255)
ORANGE = (240, 140, 30, 255)


def rect(x0, y0, x1, y1, color):
    return lambda x, y: color if x0 <= x <= x1 and y0 <= y <= y1 else None


def circle(cx, cy, r, color):
    return lambda x, y: color if (x - cx) ** 2 + (y - cy) ** 2 <= r * r else None


def ring(cx, cy, r0, r1, color):
    return lambda x, y: color if r0 * r0 <= (x - cx) ** 2 + (y - cy) ** 2 <= r1 * r1 else None


# Shapes in a 0..1 coordinate system, later shapes are drawn on top.
ICONS = {
    'mate': [
        rect(0.06, 0.62, 0.94, 0.94, GRAY),         # fixed part
        rect(0.40, 0.48, 0.60, 0.62, DARK),          # pin
        rect(0.18, 0.08, 0.82, 0.48, BLUE),          # moving part
        ring(0.50, 0.28, 0.08, 0.14, (255, 255, 255, 255)),
        rect(0.47, 0.50, 0.53, 0.60, ORANGE),       # axis
    ],
    'manager': [
        rect(0.06, 0.08, 0.94, 0.92, GRAY),
        rect(0.12, 0.14, 0.88, 0.86, (255, 255, 255, 255)),
        rect(0.18, 0.22, 0.32, 0.34, BLUE), rect(0.38, 0.25, 0.82, 0.31, DARK),
        rect(0.18, 0.44, 0.32, 0.56, BLUE), rect(0.38, 0.47, 0.82, 0.53, DARK),
        rect(0.18, 0.66, 0.32, 0.78, ORANGE), rect(0.38, 0.69, 0.82, 0.75, DARK),
    ],
}


def render(shapes, size):
    rows = []
    n = size * SS
    for py in range(size):
        row = bytearray([0])  # filter type 0
        for px in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(SS):
                for sx in range(SS):
                    x = (px * SS + sx + 0.5) / n
                    y = (py * SS + sy + 0.5) / n
                    color = None
                    for shape in shapes:
                        c = shape(x, y)
                        if c is not None:
                            color = c
                    if color is not None:
                        a = color[3]
                        acc[0] += color[0] * a
                        acc[1] += color[1] * a
                        acc[2] += color[2] * a
                        acc[3] += a
            alpha = acc[3]
            if alpha:
                row += bytes([acc[0] // alpha, acc[1] // alpha, acc[2] // alpha, alpha // (SS * SS)])
            else:
                row += bytes([0, 0, 0, 0])
        rows.append(bytes(row))
    return b''.join(rows)


def write_png(path, size, raw):
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
    with open(path, 'wb') as f:
        f.write(png)


def main():
    for name, shapes in ICONS.items():
        folder = os.path.join(ROOT, name)
        os.makedirs(folder, exist_ok=True)
        for size in SIZES:
            write_png(os.path.join(folder, '{0}x{0}.png'.format(size)), size, render(shapes, size))
            print('wrote', name, size)


if __name__ == '__main__':
    main()
