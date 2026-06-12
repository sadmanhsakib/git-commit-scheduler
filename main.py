import os
import time
import shutil
import subprocess
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

AUTHOR_EMAIL = os.getenv("EMAIL")
SEARCH_DIR = os.getenv("SEARCH_DIR")

if not AUTHOR_EMAIL or not SEARCH_DIR:
    print("Please set EMAIL and SEARCH_DIR in .env")
    exit(1)

today = datetime.now().strftime("%Y-%m-%d")
STORAGE_PATH = Path(__file__).parent / "storage" / "schedule.csv"
LOCK_FILE = Path(__file__).parent / "storage" / "schedule.lock"

if not os.path.exists(STORAGE_PATH):
    df = pd.DataFrame(columns=["index", "commit_message", "project_dir",
                               "commit_dir", "backup_dir", "priority", "excluded_files"])
    os.makedirs(STORAGE_PATH.parent, exist_ok=True)
    df.to_csv(STORAGE_PATH, index=False)


def main():
    schedule_commit()


def get_total_commit_count() -> int:
    total_commits = 0
    for root, dirs, _ in os.walk(SEARCH_DIR):
        root_path = Path(root)

        if (root_path / ".git").exists():
            try:
                result = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(root_path),
                        "rev-list",
                        "--count",
                        "HEAD",
                        f"--since={today} 00:00",
                        f"--author={AUTHOR_EMAIL}",
                    ],
                    capture_output=True,
                    text=True,
                )

                count = int(result.stdout.strip() or 0)
                total_commits += count
            except Exception as e:
                print(f"Error in {root_path}: {e}")

            # Prevent descending into nested repos
            dirs[:] = []
    return total_commits


def acquire_lock():
    """Acquire file lock for CSV operations using a simple lock file mechanism."""
    max_retries = 100
    retry_delay = 0.1
    
    for attempt in range(max_retries):
        try:
            # Try to create the lock file exclusively
            if not LOCK_FILE.exists():
                LOCK_FILE.touch()
                # Write our PID to the lock file for debugging
                with open(LOCK_FILE, 'w') as f:
                    f.write(str(os.getpid()))
                return LOCK_FILE
            else:
                # Check if the lock is stale (older than 5 minutes)
                lock_age = time.time() - LOCK_FILE.stat().st_mtime
                if lock_age > 300:  # 5 minutes
                    print("⚠️ Removing stale lock file")
                    LOCK_FILE.unlink()
                    continue
                # Wait and retry
                time.sleep(retry_delay)
        except Exception as e:
            print(f"⚠️ Error acquiring lock: {e}")
            time.sleep(retry_delay)
    
    raise TimeoutError(f"Could not acquire lock after {max_retries} retries")


def release_lock(lock_file):
    """Release file lock by removing the lock file."""
    try:
        if lock_file and lock_file.exists():
            lock_file.unlink()
    except Exception as e:
        print(f"⚠️ Error releasing lock: {e}")


def schedule_commit():
    commit_message = input("Commit Message: ")

    while True:
        try:
            excluded_files = [".venv", ".git", "__pycache__"]
            excluded_files.extend(input("Excluded Files (space-separated): ").split())
            break
        except ValueError:
            print("⚠️ Please enter valid file names separated by spaces.")
            continue

    while True:
        project_dir = input("Project Directory: ")
        if os.path.exists(Path(project_dir) / ".git"):
            break

    lock = acquire_lock()
    try:
        df = pd.read_csv(STORAGE_PATH, dtype={
            "index": "int64",
            "commit_message": "str",
            "project_dir": "str",
            "commit_dir": "str",
            "backup_dir": "str",
            "priority": "int64",
            "excluded_files": "str"
        })

        while True:
            try:
                priority = int(input("Priority: "))
                if priority >= 0 and (df.empty or priority not in df["priority"].values):
                    break
                else:
                    print("⚠️ Priority already exists. Please choose a different priority.")
            except ValueError:
                print("⚠️ Please enter a valid integer for priority.")
                continue

        index = int(df["index"].max()) + 1 if not df.empty else 1
        commit_dir = f"storage/{index}/commit"    
        backup_dir = ""  # Empty string instead of None to ensure string dtype

        os.makedirs(commit_dir, exist_ok=True)

        # storing the current project
        shutil.copytree(project_dir, commit_dir, 
                        dirs_exist_ok=True, ignore=shutil.ignore_patterns(*excluded_files))

        excluded_files_str = " ".join(excluded_files)
        df.loc[len(df)] = [index, commit_message, project_dir, commit_dir,
                           backup_dir, priority, excluded_files_str]
        df = df.sort_values(by="priority", ascending=False)
        df.to_csv(STORAGE_PATH, index=False)

        print("✅ Commit scheduled successfully!")
    finally:
        release_lock(lock)


def commit_and_push():
    backup_dir = None
    try:
        lock = acquire_lock()
        df = pd.read_csv(STORAGE_PATH, dtype={
            "index": "int64",
            "commit_message": "str",
            "project_dir": "str",
            "commit_dir": "str",
            "backup_dir": "str",
            "priority": "int64",
            "excluded_files": "str"
        })

        if df.empty:
            release_lock(lock)
            return None

        row = df.iloc[0]
        backup_dir = f"storage/{row['index']}/backup"
        excluded_files = row['excluded_files'].split()

        # storing the current project snapshot
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copytree(row["project_dir"], backup_dir, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(*excluded_files))
        df.loc[0, "backup_dir"] = backup_dir
        df.to_csv(STORAGE_PATH, index=False)
        release_lock(lock)
        
        # Restore from backup if git operations fail
        try:
            shutil.copytree(row["commit_dir"], row["project_dir"], dirs_exist_ok=True)

            subprocess.run(["git", "add", "." ], cwd=row["project_dir"], check=True)
            subprocess.run(["git", "commit", "-m", row["commit_message"]], cwd=row["project_dir"], check=True)
            subprocess.run(["git", "push"], cwd=row["project_dir"], check=True)
            print("✅ Git Push Successful. ")
        except Exception as git_error:
            print(f"Git operation failed: {git_error}")
            print("Restoring project from backup...")
            if backup_dir and os.path.exists(backup_dir):
                shutil.copytree(backup_dir, row["project_dir"], dirs_exist_ok=True)
            raise git_error

        # Restore from backup after successful push
        shutil.copytree(backup_dir, row["project_dir"], dirs_exist_ok=True)

        lock = acquire_lock()
        df = pd.read_csv(STORAGE_PATH, dtype={
            "index": "int64",
            "commit_message": "str",
            "project_dir": "str",
            "commit_dir": "str",
            "backup_dir": "str",
            "priority": "int64",
            "excluded_files": "str"
        })
        df = df.iloc[1:].reset_index(drop=True)
        df.to_csv(STORAGE_PATH, index=False)
        shutil.rmtree(f"storage/{row['index']}")
        release_lock(lock)
        
        return True
    except Exception as error:
        print(f"Error: {error}")
        # Ensure lock is released if error occurs
        try:
            if 'lock' in locals():
                release_lock(lock)
        except:
            pass
        return False


if __name__ == "__main__":
    main()
