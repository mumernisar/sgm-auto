"""pytesseract stand-in for the app: the same calls the bot makes, backed by Tesseract4Android (Ocr.java)."""
import json
import re

import cv2
from java import jclass

_ocr = jclass("dev.umer.sgmbot.Ocr")


class Output:
    DICT = "dict"


def _args(config):
    psm = re.search(r"--psm\s+(\d+)", config or "")
    whitelist = re.search(r"tessedit_char_whitelist=(\S+)", config or "")
    return int(psm.group(1)) if psm else 3, whitelist.group(1) if whitelist else ""


def _png(img):
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("couldn't encode image for OCR")
    return buf.tobytes()


def image_to_string(img, config=""):
    psm, whitelist = _args(config)
    return str(_ocr.text(_png(img), psm, whitelist))


def image_to_data(img, config="", output_type=None):
    psm, whitelist = _args(config)
    return json.loads(str(_ocr.data(_png(img), psm, whitelist)))
