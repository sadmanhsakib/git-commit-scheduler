from main import get_total_commit_count, commit_and_push

if __name__ == "__main__":
    while not get_total_commit_count() > 2:
        commit_and_push()