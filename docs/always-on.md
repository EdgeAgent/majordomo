# Always-on: the daemon

Reminders only fire while something is listening. The web app listens
(its background tick), but only while it runs. The daemon is the
listener with nothing else attached:

```bash
majordomo daemon                  # tick every 30 seconds, forever
majordomo daemon --interval 60    # tick once a minute
majordomo daemon --once           # one tick, print what's due, exit
```

Each tick fires every due reminder — the same `fire_due` engine the
web app and `majordomo schedule run-due` use — prints it, and drops it
into the `inbox` session, where the next chat (terminal or web) shows
it. `--once` is the smoke test: run it by hand before installing the
service and you should see your due reminders, or `Nothing due.`

## Initiative: what else each tick does

Firing reminders is only half the tick. Right after it, the
initiative engine (`src/majordomo/initiative.py`) takes its turn —
in the daemon and in the web app's background tick alike. Both jobs
are read-only: the engine never sends mail and never calls an acting
tool.

- **Mail watch.** The tick polls the mailbox (the same backend the
  mail tools use). A message whose id has never been seen gets a
  one-line digest in the `inbox` session: `📬 New mail from <sender>:
  <subject>`. The daemon also prints it. The very first tick only
  establishes the baseline — everything already in the mailbox is
  history, not news — so a fresh install does not flood you with its
  own inbox. An unconfigured or unreachable mailbox is skipped
  quietly; the tick carries on.
- **Escalation.** The engine records every reminder it watches fire.
  If one is still unacknowledged more than **two hours** later, the
  tick surfaces it once more — `⏰ Still waiting: <text>` — and marks
  it escalated, so it never repeats. *Acknowledged* has a precise
  meaning here, because the schedule store has no ack button: the
  reminder left the store (you cancelled or cleared it — a deliberate
  action). A one-time reminder sitting in the store as `done` was
  only *fired*; that does not count as you having seen it. A
  recurring reminder that fires again restarts its own clock.

### Notifications: the same lines, on your phone

The digest and escalation lines above land in the `inbox` session —
which helps when you next open the window. To have them *reach* you,
set a notification webhook:

```bash
MAJORDOMO_NOTIFY_WEBHOOK=https://ntfy.sh/your-topic   # any URL that takes a JSON POST
majordomo notify "Test" "It works"                    # prove the channel before you rely on it
```

Each new-mail digest and each escalation is then also POSTed to that
URL as `{"title", "body", "source": "majordomo"}` — the title says
which kind it is ("new mail" / "a reminder needs you"), the body is
the same one line the inbox gets. The shape suits ntfy-style servers,
generic webhook receivers, and automation inboxes (Make/n8n/Zapier
webhook URLs included). Delivery is best effort: a dead webhook is
logged by the tick and never breaks it, and nothing about the inbox
digest changes. Notifications are outbound only — Majordomo opens no
listener for replies. Unset the variable and they're off.

### The state file

The engine's memory is one small JSON file, `initiative.json`, in
the data directory:

```json
{
  "seen_mail_ids": ["fake-1", "fake-2"],
  "fired": {
    "a1b2c3d4": {"text": "Call the bank", "fired_at": "2026-11-21T09:00:00+00:00", "escalated": false}
  }
}
```

It is safe to inspect, edit, or delete: deleting it just makes the
next tick re-baseline the mail watch and forget any pending
escalations. The morning brief (`majordomo brief`) reads the same
file to count how much of your mail is new.

## Linux: systemd user service

A ready-made unit ships at `deploy/majordomo.service`:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/majordomo.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now majordomo
loginctl enable-linger $USER   # keep it running after you log out
```

Check on it with `systemctl --user status majordomo`; follow its
output with `journalctl --user -u majordomo -f`. If the `majordomo`
executable is not at `~/.local/bin/majordomo` (a virtualenv install,
say), edit the unit's `ExecStart` line before enabling it.
Configuration comes from `MAJORDOMO_*` environment variables or a
`.env` file in your home directory — the unit's working directory.

## Windows: Task Scheduler

An installer script ships at `deploy/install-windows-task.ps1`:

```powershell
powershell -ExecutionPolicy Bypass -File deploy\install-windows-task.ps1
```

It registers a **Majordomo Daemon** task that starts at logon, runs
`majordomo daemon --interval 30` as your user (no admin needed), and
restarts it a few times if it ever exits. If `majordomo.exe` is not on
your PATH, pass `-MajordomoExe C:\path\to\majordomo.exe`. Remove it
with:

```powershell
Unregister-ScheduledTask -TaskName "Majordomo Daemon" -Confirm:$false
```

Set configuration as user environment variables, or in a `.env` file
in your home directory.

## Notes

- The daemon and the web app can run at the same time: `fire_due`
  marks one-time reminders done as it fires them, so a reminder is
  delivered once even with two listeners.
- The daemon does not start the web UI. Run `majordomo serve` as well
  if you want the window; the daemon is deliberately just the tick.
