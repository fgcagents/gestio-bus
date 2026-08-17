"""Migració única de la base SQLite local cap a PostgreSQL.

NOTA: Executa aquest script LOCALMENT, no a Streamlit Cloud.
A Streamlit Cloud, la base de dades PostgreSQL es configura automàticament
mitjançant la variable DATABASE_URL en els secrets.
"""

from database import init_db, migrate_sqlite_to_postgres


if __name__ == "__main__":
    try:
        init_db()
        totals = migrate_sqlite_to_postgres()
        print(
            "✅ Migració completada: "
            f"{totals['autocars']} autocars i {totals['registres']} registres."
        )
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Si estàs a Streamlit Cloud, aquesta migració no és necessària.")
