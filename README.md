# git-commit-scheduler

Queues Git commits with priority ordering and executes them based on a configurable daily threshold. Snapshots are taken before and after operations to enable rollback on failure.

---

## Architecture

The tool operates in two phases:

**Scheduling Phase (`main.py`)**

The script prompts for commit details (message, target directory, priority, excluded files), snapshots the current project state to `storage/<index>/commit/`, and appends an entry to `storage/schedule.csv` sorted by priority descending.

**Execution Phase (`runner.pyw`)**

The script counts commits made today across all repositories under `SEARCH_DIR` (filtered by author email), then processes the queue until the daily limit is reached or the queue is empty. For each commit:

1. Acquires a file lock (`storage/schedule.lock`) before CSV operations
2. Reads the queue and selects the highest-priority entry (`iloc[0]`)
3. Creates a backup snapshot at `storage/<index>/backup/`
4. Updates the CSV with the backup path and releases the lock
5. Overwrites the target directory with the scheduled snapshot
6. Executes `git add .`, `git commit -m`, and `git push`
7. Restores the target directory from backup (regardless of Git operation outcome)
8. Acquires lock, removes the processed entry from CSV, deletes `storage/<index>/`, and releases lock

If Git operations fail, the backup is restored before re-raising the exception. CSV modifications are protected by a file-based lock mechanism with 100 retries at 0.1-second intervals. Locks older than 5 minutes are automatically removed as stale.

```
Execution Flow
──────────────
acquire_lock()
    ├─ Create schedule.lock if absent
    ├─ Write PID to lock file
    └─ Retry up to 100 times (0.1s delay)
        └─ Remove stale locks (>5 min)

commit_and_push()
    ├─ Lock → Read CSV → Create backup → Update CSV → Release
    ├─ Copy commit snapshot to project_dir
    ├─ git add . && git commit && git push
    │   └─ On failure: Restore from backup, re-raise
    ├─ Restore from backup (always)
    └─ Lock → Remove entry → Delete storage/<index>/ → Release
```

---

## Requirements

| Requirement | Version | Purpose |
|------------|---------|---------|
| Python | ≥ 3.12 | Runtime (specified in `pyproject.toml`) |
| Git | Any | Commit and push operations via subprocess |
| pandas | ≥ 3.0.3 | CSV queue management |
| python-dotenv | ≥ 0.9.9 | Environment variable loading |

**System Dependencies:**
- Git must be on `PATH`
- Git remotes must be pre-configured with authentication (SSH keys or credential manager)

---

## Installation

Clone the repository and install dependencies:

```bash
git clone <repository-url> git-commit-scheduler
cd git-commit-scheduler
uv sync
```

Or with pip:

```bash
pip install -e .
```

---

## Configuration

Copy `example.env` to `.env` and populate the required variables:

```env
EMAIL=you@example.com
SEARCH_DIR=D:\projects
LIMIT=2
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EMAIL` | Yes | None | Git author email. Used to filter commits when counting today's total. Script exits with error if unset. |
| `SEARCH_DIR` | Yes | None | Root directory containing Git repositories. Walked recursively via `os.walk()`. Nested repositories (repos inside repos) are detected and excluded from descent. Script exits with error if unset. |
| `LIMIT` | No | None | Daily commit threshold. Execution stops when `get_total_commit_count()` reaches this value. If unset or empty, processes the entire queue without limit. |

---

## Usage

### Schedule a Commit

```bash
python main.py
```

The script prompts for:

- **Commit Message**: Text passed to `git commit -m`
- **Excluded Files**: Space-separated list of file/folder names. These are added to the default exclusions (`.venv`, `.git`, `__pycache__`) and passed to `shutil.ignore_patterns()` during snapshot.
- **Project Directory**: Absolute path to the target repository. Must contain a `.git` directory; re-prompts if absent.
- **Priority**: Unique non-negative integer. Higher values are processed first. Re-prompts if the value already exists in the queue.

The scheduler:
1. Acquires a file lock (`storage/schedule.lock`)
2. Generates a new `index` (max existing index + 1, or 1 if queue is empty)
3. Copies the project directory to `storage/<index>/commit/`, excluding specified files
4. Appends a row to `storage/schedule.csv` and re-sorts by priority (descending)
5. Releases the lock

### Execute the Queue

```bash
python runner.pyw
```

**Behavior depends on `LIMIT` configuration:**

- **If `LIMIT` is set:** Loops while `get_total_commit_count() < LIMIT`, calling `commit_and_push()` until the limit is reached or the queue is empty.
- **If `LIMIT` is unset or empty:** Loops unconditionally, processing all queued commits until the queue is empty.

The executor stops early if `commit_and_push()` returns `False` (indicating an error) or `None` (indicating an empty queue).

---

## Automation with Windows Task Scheduler

Open **Task Scheduler** (`taskschd.msc`) and click **Create Task**.

**General**
- Name: `git-commit-scheduler`
- ☑ Run whether user is logged on or not
- ☑ Run with highest privileges

**Triggers**
- New → On a schedule → Daily
- Set execution time (e.g., 11:00 PM)
- Add additional triggers if multiple daily runs are needed

**Actions**
- New → Start a program
- Program/script: `pythonw.exe` (or absolute path to `pythonw.exe` for silent execution)
- Arguments: `runner.pyw`
- Start in: `D:\scripts\git-commit-scheduler` (absolute path to project root)

**Conditions**
- Uncheck "Start the task only if the computer is on AC power" for laptop use

**Settings**
- ☑ If the task is already running, do not start a new instance

Verify the task by right-clicking it and selecting **Run**. A Last Run Result of `0x0` indicates success.

---

## Output Structure

The tool creates the following directory structure:

```
storage/
├── schedule.csv          # Priority-sorted queue
├── schedule.lock         # File lock (transient, removed after operations)
└── <index>/              # Per-commit working directories (deleted after push)
    ├── commit/           # Snapshot of project state at scheduling time
    └── backup/           # Snapshot of project state before Git operations
```

**CSV Schema (`storage/schedule.csv`):**

| Column | Type | Description |
|--------|------|-------------|
| `index` | int | Auto-incremented identifier (max + 1). Used as the snapshot directory name. |
| `commit_message` | str | Message passed to `git commit -m`. |
| `project_dir` | str | Absolute path to the target repository. |
| `commit_dir` | str | Path to the scheduled snapshot (always `storage/<index>/commit`). |
| `backup_dir` | str | Path to the pre-push snapshot (initially `None`, set to `storage/<index>/backup` during execution). |
| `priority` | int | Sort key (descending). Higher values are processed first. Must be unique and non-negative. |
| `excluded_files` | str | Space-separated list of file/folder names excluded from snapshots via `shutil.ignore_patterns()`. |

The file is initialized with these columns if it does not exist. Rows are sorted by `priority` descending after each addition. The executor always processes `iloc[0]` (highest priority).

---

## Error Handling

**Lock Acquisition Failures:**
- The `acquire_lock()` function retries 100 times at 0.1-second intervals before raising `TimeoutError`.
- Locks older than 5 minutes are considered stale and automatically removed.
- The lock file contains the process PID for debugging.

**Git Operation Failures:**
- If `git add`, `git commit`, or `git push` fails, the exception is caught in `commit_and_push()`.
- The project directory is restored from `backup/` before re-raising the exception.
- The CSV entry and storage directory are **not** removed on failure, allowing manual investigation or retry.
- The function returns `False` on error, causing `runner.pyw` to stop processing.

**Empty Queue:**
- `commit_and_push()` returns `None` if the CSV is empty, causing `runner.pyw` to exit.

**Missing Environment Variables:**
- The script checks for `EMAIL` and `SEARCH_DIR` on startup. If either is unset, it prints an error message and exits with code 1.

**Lock Release Failures:**
- The `release_lock()` function suppresses exceptions when removing the lock file, printing a warning instead.
- Errors during lock release in `commit_and_push()` are wrapped in a try-except to ensure they do not mask Git operation failures.

---

## Limitations

- **Lock mechanism is simple polling.** The tool retries 100 times at 0.1-second intervals (maximum 10-second wait). High contention may cause delays or lock acquisition failure.
- **Snapshots are full directory copies.** `shutil.copytree()` duplicates the entire project directory minus excluded files. Large repositories consume significant disk space in `storage/`.
- **Priority must be manually managed.** The tool enforces unique priorities but does not provide renumbering or automatic gap filling. Scheduling with an existing priority causes a re-prompt.
- **Nested repositories are counted correctly.** `os.walk()` detects `.git` directories and prunes further descent (`dirs[:] = []`), preventing double-counting in nested repositories.
- **Daily commit count is author-filtered and date-bound.** The count uses `git rev-list --count HEAD --since=<today> 00:00 --author=<EMAIL>`, which depends on Git's date parsing and the system clock. Commits made in a different timezone may not be counted correctly.
- **`git push` errors do not delete the queue entry.** Failed commits remain in the queue and must be manually removed from `storage/schedule.csv` or retried.
- **`storage/` is local only.** The `.gitignore` file excludes `storage/` from version control. Snapshots and the queue are not shared across machines.
- **Excluded files are stored as space-separated strings.** File names containing spaces will cause incorrect parsing during execution.
- **The tool uses `subprocess.run(..., check=True)` for Git commands.** Non-zero exit codes raise `CalledProcessError`, which is caught and handled as described in Error Handling.

---

## Corrections

- **Architecture:** Added explicit lock acquisition/release steps in execution flow. The original README mentioned the lock mechanism but did not detail when locks are acquired and released during `commit_and_push()`.
- **Architecture:** Corrected the restoration behavior. The code restores from backup **regardless** of Git operation outcome, not only on failure. After a successful push, the backup is restored to return the project to its pre-commit state.
- **Architecture:** Added execution flow ASCII diagram to clarify lock timing, retry logic, and stale lock timeout (5 minutes).
- **Requirements:** Converted to a table format and added specific dependency versions from `pyproject.toml` (`pandas>=3.0.3`, `python-dotenv>=0.9.9`). Removed mention of `uv` as a requirement (it is a recommended tool, not a dependency).
- **Configuration:** Added `Default` column to clarify behavior when `LIMIT` is unset. Clarified that the script **exits with error** if `EMAIL` or `SEARCH_DIR` are missing (code calls `exit(1)`).
- **Configuration:** Clarified that `os.walk()` prevents descent into nested repositories via `dirs[:] = []`.
- **Usage:** Removed `uv run` prefix from commands in the primary usage section. The tool is a standalone Python script and does not require `uv` to run.
- **Usage:** Added detail on the `LIMIT` logic: the executor uses `<` comparison, not `<=`. Execution continues while the count is strictly less than the limit.
- **Automation:** Changed the program path from `uv.exe` to `pythonw.exe`. The code is a `.pyw` file (windowless Python script) and should be run with the Python interpreter, not `uv`. Using `uv run` is valid but not required for scheduled execution.
- **Output Structure:** Added section to document the `storage/` directory layout and CSV schema with column types.
- **Output Structure:** Clarified that `backup_dir` is initially `None` and only populated during execution.
- **Error Handling:** Added new section to document lock retry logic (100 retries, 0.1s intervals), stale lock timeout (5 minutes), Git failure restoration, and missing environment variable behavior.
- **Limitations:** Added detail on lock retry timing (100 × 0.1s = 10s maximum wait).
- **Limitations:** Clarified that failed commits are **not** removed from the queue, requiring manual intervention.
- **Limitations:** Added limitation on space-separated `excluded_files` parsing.
- **Limitations:** Clarified that nested repositories are explicitly handled via `dirs[:] = []` in `os.walk()`.
- **Limitations:** Added note on `subprocess.run(..., check=True)` behavior for Git commands.
