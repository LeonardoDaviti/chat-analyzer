# Instagram Chat Analyzer

Turn your own Instagram chats into clear charts and an interactive dashboard.

This tool looks at the messages in your Instagram conversations and shows you
things like who texts more, how fast each person replies, when you talk during
the day, how the tone changes over months, which words each person uses, and
much more.

**Everything runs on your own computer.** Your messages are never uploaded
anywhere. There is no account, no cloud, and no internet connection needed to
do the analysis. The results are plain files and a web page that live in a
folder on your machine.

---

## What you need

- A computer running Windows, macOS, or Linux.
- About 20 minutes (plus waiting time for Instagram to prepare your data).
- Your own Instagram data download (steps below).

---

## Step 1 — Get your Instagram data

You have to ask Instagram for a copy of your messages. This is a normal,
built-in feature. Do it from the Instagram app or from instagram.com.

1. Open Instagram and go to **Settings**.
2. Tap **Accounts Center**.
3. Tap **Your information and permissions**.
4. Tap **Download your information**.
5. Tap **Download or transfer information**.
6. Choose the **account** you want to analyze.
7. Choose **Some of your information** (not everything).
8. In the list, tick **Messages** only. Leave everything else unticked.
9. Tap **Next** / **Download to device**.
10. Now set the options carefully:
    - **Format: JSON** — this is the most important setting. It must be JSON,
      *not* HTML. (If you pick HTML, the tool cannot read your data.)
    - **Media quality: Low** — keeps the download small; photos are not needed.
    - **Date range: All time** — so you get your full history.
11. Tap **Create files** / **Submit request**.
12. Now wait. Instagram prepares the file in the background. This can take
    anywhere from a few minutes to a couple of days. You will get an email
    and/or a notification when it is ready.
13. When it is ready, open the email or the Download your information page and
    **download the ZIP file** to your computer. Remember where you saved it
    (for example, your Downloads folder).

You now have a file with a name like `instagram-yourname-2026-...zip`.

---

## Step 2 — Set up the tool

You only do this part once.

### 2a. Install Python

This tool needs **Python 3.11 or newer**.

- Download it from **https://www.python.org/downloads/** and run the installer.
- **On Windows:** on the first screen of the installer, tick the box that says
  **"Add Python to PATH"** before clicking Install. This matters.

To check it worked, open a terminal (see below) and type `python --version`
(on some systems `python3 --version`). You should see a version number of 3.11
or higher.

- **Windows terminal:** press the Start button, type **PowerShell**, open it.
- **macOS terminal:** open the **Terminal** app (in Applications → Utilities).
- **Linux terminal:** open your usual terminal app.

### 2b. Get the project

Download this project as a ZIP from its page (green **Code** button →
**Download ZIP**) and unzip it, or, if you know git:

```
git clone <the-project-url>
```

Then, in your terminal, go into the project folder. For example:

```
cd "Instagram Analysis"
```

### 2c. Create the environment and install

Copy and paste these commands into your terminal.

**Linux / macOS:**

```
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
```

**Windows (PowerShell):**

```
python -m venv venv
venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

After this, your terminal prompt usually shows `(venv)` at the start. That
means the environment is active. If you close the terminal and come back later,
just run the `activate` line again before using the tool.

---

## Step 3 — Run the analysis

### 3a. Import your download

Point the tool at the ZIP file you got from Instagram:

```
python main.py --import-zip path/to/your-download.zip
```

Replace `path/to/your-download.zip` with the real location of your file (for
example on Windows `C:\Users\You\Downloads\instagram-yourname-2026.zip`). This
copies your chats into the project's `Chats/` folder and tells you how many
conversations it found.

### 3b. Analyze everything

```
python main.py
```

That's it. The tool finds all your chats, figures out **which name is yours**
automatically (it's the person who appears in every conversation), and analyzes
each chat. You'll see a line like:

```
Detected account owner: David (use --my-name to override)
```

If it guesses your name wrong, you can set it yourself:

```
python main.py --my-name "Your Name"
```

Analyzing many chats can take a little while. When it finishes, results are
saved in a folder called `Outputs/`.

### 3c. Build the dashboard

```
python build_dashboard.py
```

Then open the file **`Dashboard/index.html`** by double-clicking it. It opens
in your normal web browser as a private local page.

### Analyzing only some chats

You can focus on one or a few conversations by name:

```
python main.py --chat "Mariam"
python build_dashboard.py --chat "Mariam"
```

Or analyze everything but skip some chats:

```
python main.py --exclude "Group Chat,Spam Account"
```

---

## What you get

**In the `Outputs/` folder** — for each chat, a set of image charts (message
balance, busiest days, reply times, language mix, top words, and more), plus
the raw numbers as data files if you ever want them.

**In `Dashboard/index.html`** — one interactive page tying it all together. You
pick a chat, drag a time slider, and every panel updates. It includes:

- **Pulse** — the headline numbers: total messages, who sends more, typical
  reply times, active days.
- **Timeline** — activity over time, with automatic markers where something
  clearly changed (a spike, a cooling-off, a shift in balance).
- **Balance & depth** — how evenly the conversation is shared, how long each
  person's "turns" run, and how deep versus casual the talk is.
- **Endings & restarts** — who tends to send the last message, who re-opens a
  quiet chat, and who gets "left on read" or "left on reacted".
- **Psycholinguistics** — gentle language signals like we/you/I balance, warm
  versus cold wording, and thank-yous and apologies.
- **Language cards** — each person's favourite words and emojis, most
  distinctive vocabulary, and how varied their language is.
- **Shifts** — a before-and-after comparison of two time periods so you can see
  what changed between them.

None of this is a judgement or a diagnosis — it's just a friendly, detailed
mirror of the patterns in your own conversations.

---

## Privacy

- The analysis runs **100% on your computer**. Nothing is sent over the
  internet.
- Your chats (`Chats/`), the results (`Outputs/`), and the dashboard
  (`Dashboard/`) are all kept out of version control on purpose, so they can't
  be accidentally shared or committed.
- The dashboard is a plain local file. Opening it does not upload anything; it
  simply reads the data already on your machine.

---

## Frequently asked questions

**I downloaded my data but the files end in `.html`, not `.json`.**
Instagram gave you the wrong format. Go back to Download your information and
request it again, and this time choose **format: JSON**. The tool can only read
JSON exports.

**The Georgian text or emojis look broken/garbled in the raw export.**
That's normal — Instagram stores them in a mangled way in the export file. The
tool automatically fixes (decodes) them, so the charts and dashboard show them
correctly. You don't need to do anything.

**How do I analyze just one conversation?**
Use the `--chat` option with part of the person's name, for example
`python main.py --chat "Mariam"` and then
`python build_dashboard.py --chat "Mariam"`.

**Where are my results?**
Charts and data are in `Outputs/`. The interactive page is
`Dashboard/index.html` — double-click it to open it in your browser.
