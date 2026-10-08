# TritonDash

A personal deadline dashboard for UCSD students that fills itself from Canvas. It pulls your assignments from your Canvas calendar feed every night, shows what is overdue, due today, and due this week, and lets you check things off, rename them, reorder them, and add your own tasks. Everything runs on your computer. Nothing is sent to anyone else.

Optional add-ons bring in PrairieLearn and Gradescope deadlines, which Canvas does not list.

This is an unofficial student project. It is not affiliated with UC San Diego, Instructure, PrairieLearn, or Gradescope.

## Quick start (macOS)

1. Get the code and open a terminal in its folder:
   ```bash
   git clone https://github.com/arnavdhole/TritonDash.git
   cd TritonDash
   ```
2. Run the installer. It asks for your Canvas feed URL (see below), fetches your deadlines, and sets up two background jobs: a nightly refresh at 2:00 AM and the dashboard server.
   ```bash
   bash scripts/install.sh
   ```
3. Open **http://127.0.0.1:8765** in your browser. Click **Refresh** any time to check Canvas right away.

Use that address every time. Your browser saves your tasks per address, so switching between addresses looks like losing your data.

### Finding your Canvas feed URL

In Canvas, open **Calendar**, then click **Calendar Feed** at the bottom right and copy the link. It looks like `https://canvas.ucsd.edu/feeds/calendars/user_XXXX.ics`.

Treat this link like a password. Anyone who has it can read your calendar. It goes in a file called `.env` on your computer, which is never uploaded to GitHub.

## Using the dashboard

- Click a task name to rename it, the date to change it, or the tag to move it.
- Drag tasks to reorder them.
- Canvas tasks keep your edits. A task you rename keeps its name, a task you check off stays done, and a task you delete does not come back.
- Canvas tags come from course codes, so `CSE100_FA26_001` becomes **CSE 100**. Rename any of them in `config/dashboard.yaml`.

## Settings

The installer copies `config/dashboard.example.yaml` to `config/dashboard.yaml`. Open it to rename tags, trim long titles, include Canvas calendar events, or add a second school's feed. Run `bash scripts/install.sh` again, or `.venv/bin/python -m src.dashboard_export`, after changing it.

## PrairieLearn and Gradescope (optional)

PrairieLearn and Gradescope have no calendar feed, and their APIs are not open to students. The included browser extension reads those sites while you are signed in, the same way you would, and hands the deadlines to the dashboard on your computer. It runs only when you click **Refresh**, and only while your browser is open and signed in to those sites.

Gradescope items that you have already submitted or that have no due date are skipped.

Install it once:

**Chrome, Arc, Edge, Brave**
1. Open `chrome://extensions` and turn on Developer mode.
2. Click **Load unpacked** and choose the `extension` folder.

**Firefox, Zen**
1. Open `about:debugging`, choose **This Firefox**, then **Load Temporary Add-on**, and pick `extension/manifest.json`. Temporary add-ons disappear when the browser restarts, so repeat this after a restart.
2. Open `about:addons`, click **Dashboard Sync**, and on the Permissions tab allow access to PrairieLearn, Gradescope, and the local dashboard.

Then sign in to PrairieLearn and Gradescope, reload the dashboard page, and click **Refresh**. If you reload the extension later, reload the dashboard page too.

The extension assumes PrairieLearn at `us.prairielearn.com`. If your course uses another address, change it in `extension/background.js` and `extension/manifest.json`.

The parsers were written against one student's account, and these sites can change their pages. If a site shows zero deadlines when you expect some, please open an issue and attach a saved copy of the page.

## Other schools

The dashboard works with any Canvas school. Use your own Canvas calendar feed. Set `timezone` in `config/dashboard.yaml` and `TIMEZONE` in `.env` to match your school.

## Windows and Linux

The dashboard and the optional extension work on any system. The installer sets up background jobs only on macOS. Elsewhere, run these yourself:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env            # then add your feed URL
.venv/bin/python scripts/dashboard_server.py   # keep this running
```

Schedule `.venv/bin/python -m src.dashboard_export` with cron or Task Scheduler if you want a nightly refresh. On Windows, use `.venv\Scripts\python`.

## Privacy and security

- Your feed URL and tasks stay on your computer. The dashboard server listens only on `127.0.0.1` and rejects requests from other websites.
- The extension requests access to only PrairieLearn, Gradescope, and the local dashboard. It sends nothing anywhere else.
- Do not post your `.env` file or your feed URL. If a link leaks, generate a new feed link in Canvas.

## Troubleshooting

| Problem | Fix |
|---|---|
| The page will not load | The server may not be running. Run `bash scripts/install.sh` again, or start it by hand with `.venv/bin/python scripts/dashboard_server.py`. |
| **Refresh** says the helper is not running | Same as above. |
| No Canvas tasks appear | Check that `CANVAS_ICAL_URL` is set in `.env`, then look at `logs/sync.log`. |
| PrairieLearn or Gradescope "needs a sign-in" | Sign in to that site in the same browser as the extension, then refresh. |
| "The extension is not responding" | Reload the dashboard page. This happens after the extension is reloaded. |
| My tasks vanished | You are probably on a different address or browser. Use **Export backup** in the old one and **Import backup** in the new one. |

## Optional: Google Calendar sync

The project also contains an older sync that copies deadlines to Google Calendar. It needs a Google Cloud project, so it is not part of the quick start. Install the extra packages with `pip install -r requirements-gcal.txt`, follow `scripts/setup_oauth.py`, and run `python -m src.main`.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

## Credits

The idea of reading PrairieLearn and Gradescope through the browser session comes from [illini-dash](https://github.com/sushelan/illini-dash), a similar tool for UIUC. No code was copied from it.

## License

MIT. See `LICENSE`.
