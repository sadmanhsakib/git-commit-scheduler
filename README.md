# git-commit-scheduler

> Automatically stage, commit, and push your Git projects on a schedule — with priority queuing, snapshot backups, and a configurable commit threshold.

---

## How It Works

The scheduler operates in two distinct phases:

**Phase 1 — Schedule (`main.py`)**
You run this interactively to queue up a commit. It:
1. Prompts you for a commit message, files to exclude, the project directory, and a priority level.
2. Takes a snapshot of your project (minus excluded files/folders) and stores it under `storage/<index>/commit/`.
3. Appends a row to `storage/schedule.csv`, sorted by priority (highest first).

**Phase 2 — Execute (`runner.pyw`)**
This is the file you point your task scheduler at. It:
1. Counts how many commits you have already made today (across all Git repos under `SEARCH_DIR`) using `git rev-list`.
2. If your daily commit count is **≤ 2**, it pops the highest-priority item from the queue, creates a backup snapshot at `storage/<index>/backup/`, runs `git add . && git commit && git push`, then restores the backup to the project directory and cleans up storage.
3. Repeats until the daily threshold is met or the queue is empty.

The backup-then-restore pattern means your working directory is always left in a clean, known state after a push — even if something goes wrong mid-flight.

```
git-commit-scheduler/
├── main.py            # Interactive scheduler — queue a new commit
├── runner.pyw          # Executor — called by the task scheduler
├── storage/
│   ├── schedule.csv   # The commit queue (index, message, dirs, priority)
│   └── <index>/
│       ├── commit/    # Snapshot taken at schedule time
│       └── backup/    # Snapshot taken just before push (restored after)
├── .env               # Your local config (not committed)
├── example.env        # Template for .env
└── pyproject.toml
```

---

## Prerequisites

- Python ≥ 3.14
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Git installed and available on `PATH`
- Git remotes already configured on the projects you want to push

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <your-fork-url> git-commit-scheduler
cd git-commit-scheduler
uv sync
```

Or with pip:

```bash
pip install -e .
```

### 2. Configure environment variables

Copy the template and fill in your values:

```bash
copy example.env .env
```

Open `.env` and set:

```env
# The email address associated with your Git commits (used to count today's commits)
EMAIL=you@example.com

# Root directory that runner.pyw will walk to count today's commits
SEARCH_DIR=D:\projects
```

`SEARCH_DIR` should be the parent folder that contains all your Git repositories. The script walks it recursively and stops descending when it finds a `.git` directory, so nested repos are handled correctly.

### 3. Queue your first commit

```bash
uv run python main.py
```

You will be prompted for:

| Prompt | Description |
|---|---|
| `Commit Message` | The message passed to `git commit -m` |
| `Excluded Files` | Space-separated file/folder names to skip when snapshotting (e.g. `.venv node_modules dist`) |
| `Project Directory` | Absolute path to the Git repo you want to commit |
| `Priority` | Integer ≥ 0, unique. Higher number = processed first |

---

## Running the Executor Manually

```bash
uv run python runner.pyw
```

This will process the queue until your daily commit count exceeds 2, then stop.

---

## Automating with Windows Task Scheduler

This is the intended way to run `runner.pyw` — set it and forget it.

### Step-by-step

1. Open **Task Scheduler** (`taskschd.msc`).
2. Click **Create Task** (not "Basic Task" — you need the full editor).

**General tab**
- Name: `git-commit-scheduler`
- Check **Run whether user is logged on or not**
- Check **Run with highest privileges**

**Triggers tab**
- Click **New…**
- Begin the task: **On a schedule**
- Choose **Daily**, set your preferred time (e.g. `11:00 PM`)
- Optionally add a second trigger at a different time if you want multiple pushes per day

**Actions tab**
- Click **New…**
- Action: **Start a program**
- Program/script: full path to your `uv` executable, e.g.:
  ```
  C:\Users\<you>\.local\bin\uv.exe
  ```
- Add arguments:
  ```
  run python runner.pyw
  ```
- Start in (the project root):
  ```
  D:\scripts\git-commit-scheduler
  ```

**Conditions tab**
- Uncheck **Start the task only if the computer is on AC power** if you are on a laptop and want it to run on battery.

**Settings tab**
- Check **If the task is already running, do not start a new instance**

3. Click **OK** and enter your Windows password when prompted.

> **Tip:** To verify the task works, right-click it in Task Scheduler and choose **Run**. Check the Last Run Result column — `0x0` means success.

---

## Adjusting the Daily Commit Threshold

The threshold is controlled by the `LIMIT` variable in your `.env` file:

```env
LIMIT=2
```

`runner.pyw` will keep popping from the queue until your total commit count for today exceeds this value, then stop. Change it to any integer without touching code.

`LIMIT` is optional. If it is not set, `runner.pyw` will execute exactly one commit from the queue and stop, regardless of how many commits you have made today.
If you don't want any limit, just leave it empty(`LIMIT=`). `runner.pyw` will keep commiting until the queue is empty then. 

---

## The Commit Queue (`storage/schedule.csv`)

| Column | Description |
|---|---|
| `index` | Auto-incremented ID, also used as the storage folder name |
| `commit_message` | Message passed to `git commit -m` |
| `project_dir` | Absolute path to the target Git repo |
| `commit_dir` | Path to the snapshot taken at schedule time |
| `backup_dir` | Path to the snapshot taken just before push |
| `priority` | Sort key — higher values are processed first |
| `excluded_files` | List of file/folder names excluded from both the commit and backup snapshots |

The CSV is sorted by `priority` descending every time a new entry is added. `runner.pyw` always pops `iloc[0]` — the highest-priority pending commit.

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `EMAIL` | Yes | Git author email used to filter `git rev-list --author` |
| `SEARCH_DIR` | Yes | Root directory walked to count today's commits |
| `LIMIT` | No | Daily commit threshold — runner stops once today's commit count exceeds this value. If unset, exactly one commit is executed per run |

---

## Notes and Caveats

- **`git push` must be pre-authenticated.** The script does not handle credentials. Use SSH keys or a credential manager (e.g. Git Credential Manager) so pushes succeed non-interactively.
- **The backup is a full directory copy**, not a diff. For very large repos, make sure you have enough disk space in `storage/`.
- **`storage/` is gitignored** by default, so your snapshots and the schedule CSV are local-only.
- The daily commit counter uses `--since=<today> 00:00` with your configured `EMAIL`, so it correctly reflects only your commits made today, not all commits in the repo.
