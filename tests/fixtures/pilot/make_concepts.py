"""Draw the pilot concepts (box house, gable roof, door): `python tests/fixtures/pilot/make_concepts.py`.
The drawing is 128 px and scaled by SCALE, so the files pass the 1024 px rule of check_card.py.
Colour boxes of the material file, in px of the saved image: STONE 160,850,160,40; TIMBER 240,560,160,240;
TEAL 448,380,128,48."""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "_approved" / "pilot-house"
SCALE = 8
STONE, TIMBER, TEAL, DOOR, BG = (128, 128, 128), (160, 110, 60), (40, 140, 140), (90, 55, 30), (255, 255, 255)


def draw(shade: float) -> Image.Image:
    def c(rgb):
        return tuple(int(v * shade) for v in rgb)
    im = Image.new("RGB", (128, 128), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((14, 104, 114, 112), fill=c(STONE))
    d.rectangle((26, 56, 102, 104), fill=c(TIMBER))
    d.polygon([(26, 56), (64, 30), (102, 56)], fill=c(TEAL))
    d.rectangle((54, 66, 74, 104), fill=c(DOOR))
    return im.resize((128 * SCALE, 128 * SCALE), Image.NEAREST).quantize(colors=8)


if __name__ == "__main__":
    draw(1.0).save(OUT / "concept_albedo.png", optimize=True)
    draw(0.6).save(OUT / "concept_shadow.png", optimize=True)
