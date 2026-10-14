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

Pick a view at the top right.

- **Timeline** shows what is overdue, due today, and due in the next 7 days, with Later, Done, and All open underneath. Drag tasks to reorder them.
- **By class** gives each class and extracurricular its own card, with its tasks sorted by due date. The chips at the top slice every card by time: All open, Overdue, Today, Next 7 days, Later, and Done. Under All open, each card folds far-off tasks into a "+ n later" link. Each card has a quick add.
- **Calendar** shows a month grid. Click a day to see its tasks and add one. Drag a task to another day to change its due date.

Working with tasks and tags:

- Click a task name to rename it, the date to change it, or the tag to move it. Click the circle to check it off.
- Click a class or extracurricular chip to show only that one in every view. Click it again to clear the filter.
- Press **Edit** above the chips to rename a class or extracurricular in place, or delete one. Drag chips, or drag a card header in the By class view, to reorder them. Drop a chip into the other row to turn a class into an extracurricular, or the reverse.
- Renaming keeps working with Canvas. If you rename `CSE 100` to `Data Structures`, new Canvas tasks for that course land under the new name.
- Canvas tasks keep your edits. A task you rename keeps its name, a task you check off stays done, and a task you delete does not come back.
- Canvas tags come from course codes, so `CSE100_FA26_001` becomes **CSE 100**.

## Backups

Your tasks, checkmarks, and tags live in your browser's storage, which can be cleared. The dashboard therefore sends a copy to the helper a few seconds after every change and after every **Refresh**. The copies are in `data/backups/` and stay on your computer: `latest.json`, one file per day for 30 days, and a `history/` folder that keeps the last 10 versions that were replaced while tasks went missing.

- A browser that has no saved tasks, such as after clearing site data, offers to restore the latest backup before it does anything else.
- If you decline, you are asked whether to start fresh. Keeping the older backup pauses backups in that browser, and the refresh report says so, until you press **Restore from backup** at the bottom of the page.
- The helper refuses to replace a backup with one that is empty or far smaller, so a cleared browser cannot wipe it.
- **Restore from backup** replaces the tasks in this browser with the latest copy. **Export backup** and **Import backup** still work as before.

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
2. Open `about:addons`, click **TritonDash Sync**, and on the Permissions tab turn on every site toggle: PrairieLearn, Gradescope, `localhost`, and `127.0.0.1`. Firefox-based browsers leave these off after a manual install, and the extension cannot attach to the dashboard until they are on. Reload the dashboard tab afterwards.

Then sign in to PrairieLearn and Gradescope, reload the dashboard page, and click **Refresh**. If you reload the extension later, reload the dashboard page too.

**Keep the extension after restarting Firefox or Zen.** A temporary add-on is removed every time the browser quits. To install it permanently, sign it with Mozilla, which is free and private (an unlisted add-on). Follow the steps at the top of `scripts/sign_extension.sh`, run `bash scripts/sign_extension.sh`, then install the `.xpi` from `dist/` through `about:addons`. This path has not been tested end to end.

**What the refresh report checks.** Each source gets a line, and the summary opens by itself when something needs attention.
- A calendar link that was regenerated, or one that has no entry in `.env`, shows its reason.
- PrairieLearn or Gradescope shows a warning, and keeps the last good data, when its pages load but no longer contain the tables the extension looks for. This usually means the site changed its layout.
- A missing sign-in, or site access that is switched off in `about:addons`, is named.

The extension's address patterns deliberately leave out the port (`http://localhost/*`). Firefox and Zen match nothing when a pattern includes one, and a test in `tests/` guards against putting it back.

The extension assumes PrairieLearn at `us.prairielearn.com`. If your course uses another address, change it in `extension/background.js` and `extension/manifest.json`.

The parsers were written against one student's account, and these sites can change their pages. If a site shows zero deadlines when you expect some, please open an issue and attach a saved copy of the page.

## Other schools

The dashboard works with any Canvas school. Use your own Canvas calendar feed. Set `timezone` in `config/dashboard.yaml` to match your school.

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

- Your feed URL, tasks, and backups stay on your computer. The dashboard server listens only on `127.0.0.1` and rejects requests from other websites.
- The extension requests access to only PrairieLearn, Gradescope, and the local dashboard. It sends nothing anywhere else.
- Do not post your `.env` file or your feed URL. If a link leaks, generate a new feed link in Canvas.

## Troubleshooting

| Problem | Fix |
|---|---|
| The page will not load | The server may not be running. Run `bash scripts/install.sh` again, or start it by hand with `.venv/bin/python scripts/dashboard_server.py`. |
| **Refresh** says the helper is not running | Same as above. |
| A calendar chip is red after **Refresh** | The chip names the cause. "HTTP 404" or "HTTP 403" usually means the calendar link was regenerated, so copy the new link from Canvas into `.env`. "is not set in .env" means that feed has no link yet. |
| No Canvas tasks appear | Check that `CANVAS_ICAL_URL` is set in `.env`, then look at `logs/sync.log`. |
| PrairieLearn or Gradescope "browser extension not detected" | The extension is not loaded in this browser, or this page is not at `http://127.0.0.1:8765` or `http://localhost:8765`. Reload the extension (Firefox and Zen drop it on restart), then reload the page. The chip also shows how old the last good data is. |
| PrairieLearn or Gradescope "needs a sign-in" | Sign in to that site in the same browser as the extension, then refresh. |
| "The extension is not responding" | Reload the dashboard page. This happens after the extension is reloaded. |
| My tasks vanished | Press **Restore from backup** at the bottom of the page. If that finds nothing, you are probably on a different address or browser: use **Export backup** in the old one and **Import backup** in the new one. |
| "Task backup: paused" in the refresh report | This browser started empty and you kept the older backup. Press **Restore from backup** to resume. |
| PrairieLearn or Gradescope "site access is off" | In `about:addons`, open the extension, go to its Permissions tab, and turn on every site toggle. |
| PrairieLearn or Gradescope shows a layout warning | The site probably changed its pages. The last good data stays in place. Save the page and open an issue so the parser can be updated. |

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

## Credits

The idea of reading PrairieLearn and Gradescope through the browser session comes from [illini-dash](https://github.com/sushelan/illini-dash), a similar tool for UIUC. No code was copied from it.

## License

MIT. See `LICENSE`.
