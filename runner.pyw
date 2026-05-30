import os
from dotenv import load_dotenv
from main import get_total_commit_count, commit_and_push


load_dotenv()


if __name__ == "__main__":
    limit = os.getenv("LIMIT")
    if limit:
        limit = int(limit)
    else:
        limit = None

    if limit:
        while not get_total_commit_count() > limit:
            commit_and_push()
    else:
        while True:
            result = commit_and_push()
            if result == "Nothing to commit. ":
                break
