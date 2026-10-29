"""Create an illustrative dataset in a new, empty directory."""

from pathlib import Path
import shutil

from PIL import Image


def main() -> None:
    target = Path("demo_images")
    target.mkdir(exist_ok=False)
    Image.new("RGB", (800, 600), "steelblue").save(target / "01_valid.png")
    Image.new("RGB", (320, 240), "coral").save(target / "02_small.png")
    shutil.copyfile(target / "01_valid.png", target / "03_duplicate.png")
    (target / "04_corrupt.jpg").write_bytes(b"This is not an image.")
    print(f"Demo dataset created: {target.resolve()}")


if __name__ == "__main__":
    main()
