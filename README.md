# Rupert Analytics

A simple Windows app that shows how Rupert's AI Diaries (@rupertsaidiaries) is doing on YouTube:
channel totals, every video's numbers, a page for each video with a plain-English diagnosis, and
editable targets.

It only reads data. It never changes anything on the channel.

## Setting up a new computer (for example, the laptop)

You only do this once per computer. You'll need three things first.

1. **Python.** Go to python.org, click the big "Download Python" button, and run the installer.
   On the first screen, tick **"Add python.exe to PATH"** before clicking Install.
2. **The Google sign-in file.** Copy `client_secret.json` from the PC into this folder on the laptop:
   press the Windows key, type `%APPDATA%` and press Enter, then open the folder called
   `youtube-analytics-mcp` (create it if it isn't there) and paste the file in.
   Do not email this file or put it anywhere public.
3. **The app itself.** On GitHub, click the green **Code** button, then **Download ZIP**.
   Unzip it somewhere you'll keep it, such as Documents.

Then:

1. Open the unzipped folder and double-click **setup.bat**. Wait for it to say "Setup finished"
   (a few minutes the first time).
2. If a browser opens asking you to sign in, sign in with the Google account that owns the
   channel, then click **Continue** (you may see a "Google hasn't verified this app" warning;
   that's expected for this personal app).
3. Double-click **Rupert Analytics** on the desktop.

## Using it day to day

- **Rupert Analytics** (desktop shortcut): opens the app. It shows the last saved numbers straight away,
  even without internet.
- **Refresh** (top right): pulls the latest numbers from YouTube. Takes about 30 seconds.
- **Overview**: channel totals and every video. Click a column heading to sort. Click a row to open that video.
- **Targets**: the goal for each number, and how the channel is doing against it. Change the numbers
  in the boxes and click Save.

## Things to know

- YouTube's numbers run 2 to 3 days behind. Impressions and CTR are about 2 days behind.
- A video is shown as "too early to judge" for its first 48 hours.
- The wording in the Diagnosis panel is in a file called `diagnosis.json` in
  `%APPDATA%\Rupert Analytics`. Open it in Notepad to change the wording.
- If you ever need to sign in again, double-click **Sign in to YouTube.bat**.

## For the developer

- `app.py` is the window and the link between the page and the data.
- `analytics.py` pulls the data through the connector in `connector/` (the same code as the YouTube
  connector for Claude). It reuses the same sign-in file, so there's only one Google sign-in per computer.
- `metrics.py` holds the colour rules, drop-off detection, verdicts and diagnosis rules.
- `defaults/` holds the starting targets and diagnosis wording. Your edited copies live in `%APPDATA%\Rupert Analytics`.
- `ui/` is the page (HTML, CSS and JavaScript).
