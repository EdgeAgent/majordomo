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
  if you want the chat page; the daemon is deliberately just the tick.
