package dev.umer.sgmbot;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Rect;

import com.googlecode.tesseract.android.ResultIterator;
import com.googlecode.tesseract.android.TessBaseAPI;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/**
 * Tesseract for the Python side (see python/pytesseract.py): the same engine and English data the bot was
 * tuned with on the Mac. Images arrive PNG-encoded from OpenCV.
 */
public final class Ocr {
    private static TessBaseAPI api;

    /** dataDir must contain tessdata/eng.traineddata. */
    public static synchronized void init(String dataDir) {
        if (api == null) {
            api = new TessBaseAPI();
            if (!api.init(dataDir, "eng")) {
                api = null;
                throw new IllegalStateException("Tesseract init failed for " + dataDir);
            }
        }
    }

    private static void prepare(byte[] png, int psm, String whitelist) {
        Bitmap bitmap = BitmapFactory.decodeByteArray(png, 0, png.length);
        api.setPageSegMode(psm);
        api.setVariable("tessedit_char_whitelist", whitelist == null ? "" : whitelist);
        api.setImage(bitmap);
    }

    public static synchronized String text(byte[] png, int psm, String whitelist) {
        prepare(png, psm, whitelist);
        String out = api.getUTF8Text();
        api.clear();
        return out == null ? "" : out;
    }

    /** Words with boxes, shaped like pytesseract.image_to_data(output_type=DICT). */
    public static synchronized String data(byte[] png, int psm, String whitelist) throws JSONException {
        prepare(png, psm, whitelist);
        api.getUTF8Text(); // runs recognition
        JSONArray text = new JSONArray(), left = new JSONArray(), top = new JSONArray(),
                width = new JSONArray(), height = new JSONArray();
        ResultIterator it = api.getResultIterator();
        int level = TessBaseAPI.PageIteratorLevel.RIL_WORD;
        if (it != null) {
            it.begin();
            do {
                String word = it.getUTF8Text(level);
                Rect r = it.getBoundingRect(level);
                if (word == null || r == null) {
                    continue;
                }
                text.put(word);
                left.put(r.left);
                top.put(r.top);
                width.put(r.width());
                height.put(r.height());
            } while (it.next(level));
            it.delete();
        }
        api.clear();
        JSONObject out = new JSONObject();
        out.put("text", text);
        out.put("left", left);
        out.put("top", top);
        out.put("width", width);
        out.put("height", height);
        return out.toString();
    }
}
