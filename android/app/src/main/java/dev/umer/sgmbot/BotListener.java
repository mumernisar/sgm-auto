package dev.umer.sgmbot;

/** Called from the bot's Python thread. */
public interface BotListener {
    void onLine(String line);

    void onFinished();
}
