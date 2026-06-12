import os
from dotenv import load_dotenv
from main import get_total_commit_count, commit_and_push


load_dotenv()


if __name__ == "__main__":
    limit = os.getenv("LIMIT")

    limit = int(limit) if limit else None

    if limit:
        while get_total_commit_count() < limit:
            result = commit_and_push()
            if not result:
                break
    else:
        while True:
            result = commit_and_push()
            if not result:
                break
