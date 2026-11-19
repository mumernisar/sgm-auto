package dev.umer.sgmbot;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

/**
 * One long-lived root shell for the whole app. Magisk asks for root once, shows no toast per command, and
 * screenshots stream straight out of {@code screencap} without spawning a process each time.
 */
public final class RootShell {
    private static RootShell instance;

    private final Process process;
    private final OutputStream stdin;
    private final InputStream stdout;
    private int width;
    private int height;

    public static synchronized RootShell get() throws IOException {
        if (instance == null) {
            instance = new RootShell();
        }
        return instance;
    }

    private RootShell() throws IOException {
        process = Runtime.getRuntime().exec("su");
        stdin = process.getOutputStream();
        stdout = new BufferedInputStream(process.getInputStream(), 1 << 20);
        // stderr is never read: send it nowhere so a chatty command can't fill the pipe and block
        exec("exec 2>/dev/null");
    }

    /** Runs a command (or a multi-line script) and returns its output. */
    public synchronized String exec(String command) throws IOException {
        String marker = "__SGM_DONE_" + System.nanoTime() + "__";
        stdin.write((command + "\necho " + marker + "\n").getBytes(StandardCharsets.UTF_8));
        stdin.flush();
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ByteArrayOutputStream line = new ByteArrayOutputStream();
        while (true) {
            int b = stdout.read();
            if (b < 0) {
                throw new EOFException("root shell closed");
            }
            if (b == '\n') {
                String text = line.toString(StandardCharsets.UTF_8.name());
                if (text.equals(marker)) {
                    return out.toString(StandardCharsets.UTF_8.name());
                }
                out.write(line.toByteArray());
                out.write('\n');
                line.reset();
            } else {
                line.write(b);
            }
        }
    }

    /** Raw RGBA pixels of the current screen; size via {@link #width()} / {@link #height()}. */
    public synchronized byte[] screencap() throws IOException {
        stdin.write("screencap\n".getBytes(StandardCharsets.UTF_8));
        stdin.flush();
        byte[] header = readFully(16); // width, height, format, colour space (Android 12+)
        width = littleEndianInt(header, 0);
        height = littleEndianInt(header, 4);
        return readFully(width * height * 4);
    }

    public int width() {
        return width;
    }

    public int height() {
        return height;
    }

    private byte[] readFully(int n) throws IOException {
        byte[] buf = new byte[n];
        int off = 0;
        while (off < n) {
            int got = stdout.read(buf, off, n - off);
            if (got < 0) {
                throw new EOFException("root shell closed during screencap");
            }
            off += got;
        }
        return buf;
    }

    private static int littleEndianInt(byte[] b, int at) {
        return (b[at] & 0xff) | (b[at + 1] & 0xff) << 8 | (b[at + 2] & 0xff) << 16 | (b[at + 3] & 0xff) << 24;
    }
}
