from src.database_bootstrap import ensure_schema
from src.utils.config import DB_PATH


def main() -> None:
    ensure_schema()
    print(f"Database is ready: {DB_PATH}")


if __name__ == "__main__":
    main()
