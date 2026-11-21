package dev.umer.sgmbot;

import android.content.ComponentName;
import android.content.ServiceConnection;
import android.content.pm.PackageManager;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
import android.os.RemoteException;

import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.EOFException;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import rikka.shizuku.Shizuku;

/**
 * One long-lived shell for the whole app: `su` when the device is rooted, otherwise an `sh` that Shizuku runs as
 * adb's shell user ({@link ShellService}). Magisk asks for root once, shows no toast per command, and
 * screenshots stream straight out of {@code screencap} without spawning a process each time.
 * {@link #openSecond()} opens another one the same way, for a command that streams output ({@link TouchWatcher}).
 */
public final class RootShell {
    private static RootShell instance;

    private static IShellService shizukuService; // bound once, then asked for as many shells as needed

    private final boolean root;
    private final Process process; // su (null for Shizuku: its pipes end the shell when closed)
    private final OutputStream stdin;
    private final InputStream stdout;
    private int width;
    private int height;

    public static synchronized RootShell get() throws IOException {
        if (instance == null) {
            instance = hasSu() ? openRoot() : openShizuku();
        }
        return instance;
    }

    /** Another shell, separate from {@link #get()}'s: for a command that runs as long as the app (getevent). */
    public static RootShell openSecond() throws IOException {
        return hasSu() ? openRoot() : openShizuku();
    }

    private RootShell(boolean root, Process process, OutputStream stdin, InputStream stdout) throws IOException {
        this.root = root;
        this.process = process;
        this.stdin = stdin;
        this.stdout = new BufferedInputStream(stdout, 1 << 20);
        // stderr is never read: send it nowhere so a chatty command can't fill the pipe and block
        exec("exec 2>/dev/null");
    }

    private static RootShell openRoot() throws IOException {
        Process process = Runtime.getRuntime().exec("su");
        try {
            return new RootShell(true, process, process.getOutputStream(), process.getInputStream());
        } catch (EOFException e) { // su exited at once: root was denied
            throw new IOException("root was denied: allow SGM Bot in Magisk, then press ▶ again");
        }
    }

    // --- Shizuku -----------------------------------------------------------------------------------------------

    /** Where the device stands for running without root, for the setup screen and error messages. */
    public enum Access { ROOT, NO_SHIZUKU, SHIZUKU_STOPPED, SHIZUKU_NOT_ALLOWED, SHIZUKU_READY }

    public static Access access(PackageManager pm) {
        if (hasSu()) {
            return Access.ROOT;
        }
        if (!Shizuku.pingBinder()) {
            return isInstalled(pm, SHIZUKU_PACKAGE) ? Access.SHIZUKU_STOPPED : Access.NO_SHIZUKU;
        }
        if (Shizuku.isPreV11() || Shizuku.checkSelfPermission() != PackageManager.PERMISSION_GRANTED) {
            return Access.SHIZUKU_NOT_ALLOWED;
        }
        return Access.SHIZUKU_READY;
    }

    public static final String SHIZUKU_PACKAGE = "moe.shizuku.privileged.api";

    /** su on the PATH (checked by looking, not running it: running it would make Magisk ask). */
    public static boolean hasSu() {
        String path = System.getenv("PATH");
        for (String dir : (path != null ? path : "/system/bin:/system/xbin").split(":")) {
            if (new File(dir, "su").exists()) {
                return true;
            }
        }
        return new File("/sbin/su").exists() || new File("/debug_ramdisk/su").exists();
    }

    private static boolean isInstalled(PackageManager pm, String pkg) {
        try {
            pm.getPackageInfo(pkg, 0);
            return true;
        } catch (PackageManager.NameNotFoundException e) {
            return false;
        }
    }

    private static RootShell openShizuku() throws IOException {
        if (!Shizuku.pingBinder()) {
            throw new IOException("no root and Shizuku isn't running: open Shizuku and tap Start (setup: SGM Bot app)");
        }
        if (Shizuku.isPreV11() || Shizuku.checkSelfPermission() != PackageManager.PERMISSION_GRANTED) {
            throw new IOException("SGM Bot isn't allowed in Shizuku yet: open SGM Bot and tap Allow");
        }
        IShellService service = shellService();
        try {
            ParcelFileDescriptor[] in = ParcelFileDescriptor.createPipe();
            ParcelFileDescriptor out = service.openShell(in[0]);
            in[0].close();
            return new RootShell(false, null, new ParcelFileDescriptor.AutoCloseOutputStream(in[1]),
                    new ParcelFileDescriptor.AutoCloseInputStream(out));
        } catch (RemoteException e) {
            throw new IOException("Shizuku shell failed: " + e.getMessage());
        }
    }

    private static synchronized IShellService shellService() throws IOException {
        if (shizukuService == null || !shizukuService.asBinder().pingBinder()) {
            shizukuService = bindShellService();
        }
        return shizukuService;
    }

    private static IShellService bindShellService() throws IOException {
        CountDownLatch bound = new CountDownLatch(1);
        IShellService[] result = new IShellService[1];
        Shizuku.UserServiceArgs args = new Shizuku.UserServiceArgs(
                new ComponentName(BuildConfig.APPLICATION_ID, ShellService.class.getName()))
                .daemon(false)                       // ends with the app
                .processNameSuffix("shell")
                .debuggable(BuildConfig.DEBUG)
                .version(BuildConfig.VERSION_CODE);  // a new app version starts a new service
        ServiceConnection connection = new ServiceConnection() {
            @Override
            public void onServiceConnected(ComponentName name, IBinder binder) {
                if (binder != null && binder.pingBinder()) {
                    result[0] = IShellService.Stub.asInterface(binder);
                }
                bound.countDown();
            }

            @Override
            public void onServiceDisconnected(ComponentName name) {
                synchronized (RootShell.class) {
                    instance = null; // the next ▶ binds again
                    shizukuService = null;
                }
            }
        };
        new Handler(Looper.getMainLooper()).post(() -> Shizuku.bindUserService(args, connection));
        try {
            if (!bound.await(15, TimeUnit.SECONDS) || result[0] == null) {
                throw new IOException("Shizuku didn't start the shell: restart Shizuku and try again");
            }
        } catch (InterruptedException e) {
            throw new IOException("interrupted while starting the Shizuku shell");
        }
        return result[0];
    }

    // --- commands ----------------------------------------------------------------------------------------------

    public boolean isRoot() {
        return root;
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
                dropIfDead();
                throw new EOFException("shell closed");
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

    /** Starts a command that keeps writing (getevent) and returns its output to read line by line. The shell is
     * used up: {@link #close()} it when done. */
    public synchronized InputStream stream(String command) throws IOException {
        stdin.write(("exec " + command + "\n").getBytes(StandardCharsets.UTF_8));
        stdin.flush();
        return stdout;
    }

    /** Ends a shell from {@link #openSecond()}. A command still running in it ends at its next write (its
     * output pipe is gone). */
    public void close() {
        try {
            stdin.close();
        } catch (IOException ignored) {
            // already closed
        }
        try {
            stdout.close();
        } catch (IOException ignored) {
            // already closed
        }
        if (process != null) {
            process.destroy();
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
                dropIfDead();
                throw new EOFException("shell closed during screencap");
            }
            off += got;
        }
        return buf;
    }

    /** A closed shell (Shizuku stopped, root revoked) is replaced on the next {@link #get()}. */
    private void dropIfDead() {
        synchronized (RootShell.class) {
            if (instance == this) {
                instance = null;
            }
        }
    }

    private static int littleEndianInt(byte[] b, int at) {
        return (b[at] & 0xff) | (b[at + 1] & 0xff) << 8 | (b[at + 2] & 0xff) << 16 | (b[at + 3] & 0xff) << 24;
    }
}
