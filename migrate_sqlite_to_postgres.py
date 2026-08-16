"""Migració única de la base SQLite local cap a PostgreSQL."""

from database import init_db, migrate_sqlite_to_postgres


if __name__ == "__main__":
    init_db()
    totals = migrate_sqlite_to_postgres()
    print(
        "Migració completada: "
        f"{totals['autocars']} autocars i {totals['registres']} registres."
    )
