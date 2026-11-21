"""Frame sizes. Every coordinate in the bot (templates, regions, tap points) is in *design units*: pixels of the
reference tablet's 2560x1600 screen. Fast mode runs the screen at 1920x1200, so a frame there has k = 0.75 pixels
per design unit; a half-size copy of a full frame has k = 0.5. k is read from the frame's own width, so there's no
setting to keep in step with the screen.

Template matching (`vision`) and the map read (`eventmap`) work on frames of any size and give results in design
units. Everything else (`readers`, `team`) measures pixel sizes on the 2560x1600 frame, so it gets `design(img)`:
the frame itself at full size, else upscaled (a few ms; the readability test showed 1920x1200 frames read the
same after it)."""
import cv2

W, H = 2560, 1600


def k_of(img):
    """Pixels per design unit: 1.0 at 2560x1600, 0.75 at 1920x1200."""
    return img.shape[1] / W


def design(img):
    """The frame at 2560x1600: img itself at full size, else upscaled."""
    if img.shape[1] == W:
        return img
    return cv2.resize(img, (W, H), interpolation=cv2.INTER_CUBIC)
