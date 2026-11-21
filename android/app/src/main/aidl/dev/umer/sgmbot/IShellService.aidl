package dev.umer.sgmbot;

// Runs in a process Shizuku starts as adb's shell user (ShellService).
interface IShellService {
    // Shizuku calls this transaction to end the service
    void destroy() = 16777114;

    // Starts `sh` reading commands from stdin; returns the read end of its stdout
    ParcelFileDescriptor openShell(in ParcelFileDescriptor stdin) = 1;
}
