import os, time
import shutil, subprocess
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

AUTHOR_EMAIL = os.getenv("EMAIL")
SEARCH_DIR = os.getenv("SEARCH_DIR")

today = datetime.now().strftime("%Y-%m-%d")

if not os.path.exists("storage/schedule.csv"):
    df = pd.DataFrame(columns=["index", "commit_message", "project_dir",
                               "commit_dir", "backup_dir", "priority", "excluded_files"])
    df.to_csv("storage/schedule.csv", index=False)


def main():
    schedule_commit()


def get_total_commit_count() -> int:
    total_commits = 0
    for root, dirs, files in os.walk(SEARCH_DIR):
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


def schedule_commit():
    commit_message = input("Commit Message: ")

    while True:
        try:
            excluded_files = [".venv", ".git", "__pycache__"]
            excluded_files.extend(input("Excluded Files (space-separated): ").split())
            break
        except (ValueError, ZeroDivisionError):
            continue

    while True:
        project_dir = input("Project Directory: ")
        if os.path.exists(Path(project_dir) / ".git"):
            break

    df = pd.read_csv("storage/schedule.csv")

    while True:
        try:
            priority = int(input("Priority: "))
            if priority >= 0 and priority not in df["priority"].values:
                break
        except (ValueError, ZeroDivisionError):
            continue

    index = int(df["index"].max()) + 1 if not df.empty else 1
    commit_dir = f"storage/{index}/commit"    
    backup_dir = None

    os.makedirs(commit_dir, exist_ok=True)

    # storing the current project
    shutil.copytree(project_dir, commit_dir, 
                    dirs_exist_ok=True, ignore=shutil.ignore_patterns(*excluded_files))

    
    excluded_files_str = " ".join(excluded_files)
    df.loc[len(df)] = [index, commit_message, project_dir, commit_dir,
                       backup_dir, priority, excluded_files_str]
    df = df.sort_values(by="priority", ascending=False)
    df.to_csv("storage/schedule.csv", index=False)

    print("✅ Commit scheduled successfully!")


def commit_and_push():
    try:
        df = pd.read_csv("storage/schedule.csv")

        if df.empty:
            print("Nothing to commit. ")
            return "Nothing to commit. "

        df['backup_dir'] = df['backup_dir'].astype(str)

        row = df.iloc[0]
        backup_dir = f"storage/{row['index']}/backup"
        excluded_files = row['excluded_files'].split()

        # storing the current project snapshot
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copytree(row["project_dir"], backup_dir, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(*excluded_files))
        df.loc[0, "backup_dir"] = backup_dir
        
        shutil.copytree(row["commit_dir"], row["project_dir"], dirs_exist_ok=True)

        subprocess.run(["git", "add", "." ], cwd=row["project_dir"], check=True)
        subprocess.run(["git", "commit", "-m", row["commit_message"]], cwd=row["project_dir"], check=True)
        subprocess.run(["git", "push"], cwd=row["project_dir"], check=True)
        print("✅ Git Push Successful. ")

        shutil.copytree(backup_dir, row["project_dir"], dirs_exist_ok=True)

        df = df[1:]
        df.to_csv("storage/schedule.csv", index=False)
        shutil.rmtree(f"storage/{row['index']}", ignore_errors=True)
    except Exception as error:
        print(f"Error: {error}")

if __name__ == "__main__":
    start_time = time.time()
    main()
    print(f"✅ Execution completed in {time.time() - start_time:.2f} seconds")
