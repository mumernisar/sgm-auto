package dev.umer.sgmbot;

import android.app.Application;
import android.content.res.AssetManager;

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/** Starts Python once and unpacks the bot's data files (templates, Tesseract data) into app storage. */
public class App extends Application {
    @Override
    public void onCreate() {
        super.onCreate();
        File home = getFilesDir();
        try {
            // refresh on every install/update so new templates always arrive
            copyAssetDir("templates", new File(home, "templates"));
            copyAssetDir("tessdata", new File(home, "tessdata"));
        } catch (IOException e) {
            throw new RuntimeException("couldn't unpack bot files", e);
        }
        Ocr.init(home.getAbsolutePath());
        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }
        Python.getInstance().getModule("app_main").callAttr("init", home.getAbsolutePath());
    }

    private void copyAssetDir(String name, File dest) throws IOException {
        AssetManager assets = getAssets();
        String[] files = assets.list(name);
        if (files == null) {
            return;
        }
        dest.mkdirs();
        for (String f : files) {
            try (InputStream in = assets.open(name + "/" + f); OutputStream out = new FileOutputStream(new File(dest, f))) {
                byte[] buf = new byte[1 << 16];
                for (int n; (n = in.read(buf)) > 0; ) {
                    out.write(buf, 0, n);
                }
            }
        }
    }
}
