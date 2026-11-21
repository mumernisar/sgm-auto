package dev.umer.sgmbot;

import android.os.ParcelFileDescriptor;
import android.os.RemoteException;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * Shizuku's "user service": Shizuku starts this class in its own process as adb's shell user, which may take
 * screenshots, inject input and change the screen size. It hands the app an `sh` over two pipes, so
 * {@link RootShell} talks to it exactly as it talks to `su`.
 */
public class ShellService extends IShellService.Stub {
    public ShellService() {
    }

    @Override
    public void destroy() {
        System.exit(0);
    }

    @Override
    public ParcelFileDescriptor openShell(ParcelFileDescriptor stdin) throws RemoteException {
        try {
            Process sh = new ProcessBuilder("sh").redirectErrorStream(true).start();
            ParcelFileDescriptor[] out = ParcelFileDescriptor.createPipe();
            pump(new ParcelFileDescriptor.AutoCloseInputStream(stdin), sh.getOutputStream());
            pump(sh.getInputStream(), new ParcelFileDescriptor.AutoCloseOutputStream(out[1]));
            return out[0];
        } catch (IOException e) {
            throw new RemoteException("couldn't start sh: " + e.getMessage());
        }
    }

    /** Copy in to out on a thread, flushing every read (commands are line by line). */
    private static void pump(InputStream in, OutputStream out) {
        Thread t = new Thread(() -> {
            byte[] buf = new byte[1 << 16];
            try (InputStream i = in; OutputStream o = out) {
                for (int n; (n = i.read(buf)) > 0; ) {
                    o.write(buf, 0, n);
                    o.flush();
                }
            } catch (IOException ignored) {
                // the other side closed: the app went away or the shell exited
            }
        });
        t.setDaemon(true);
        t.start();
    }
}
