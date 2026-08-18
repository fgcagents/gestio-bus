import sqlite3

import pandas as pd

import database


def configurar_sqlite_temporal(monkeypatch, tmp_path):
    fitxer = tmp_path / "prova.db"
    monkeypatch.setattr(database, "DATABASE_BACKEND", "sqlite")
    monkeypatch.setattr(database, "SQLITE_FILE", fitxer)
    return fitxer


def test_init_db_sqlite_es_idempotent(monkeypatch, tmp_path):
    fitxer = configurar_sqlite_temporal(monkeypatch, tmp_path)

    database.init_db()
    database.init_db()

    with sqlite3.connect(fitxer) as conn:
        columnes = {
            fila[1] for fila in conn.execute("PRAGMA table_info(registres)").fetchall()
        }
    assert {"id", "matricula", "hora_entrada", "hora_sortida", "estacio", "sentit", "estat"} <= columnes


def test_init_db_postgresql_no_provoca_errors_de_columna_duplicada(monkeypatch):
    class CursorFals:
        def __init__(self):
            self.consultes = []

        def execute(self, consulta, params=()):
            self.consultes.append(consulta)
            return self

    class ConnexioFalsa:
        backend = "postgresql"

        def __init__(self):
            self.cursor_fals = CursorFals()
            self.commits = 0
            self.rollbacks = 0

        def cursor(self):
            return self.cursor_fals

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            pass

    conn = ConnexioFalsa()
    monkeypatch.setattr(database, "DATABASE_BACKEND", "postgresql")
    monkeypatch.setattr(database, "get_db_connection", lambda: conn)

    database.init_db()

    alteracions = [q for q in conn.cursor_fals.consultes if "ALTER TABLE" in q]
    assert len(alteracions) == 2
    assert all("IF NOT EXISTS" in q for q in alteracions)
    assert conn.commits == 1
    assert conn.rollbacks == 0


def test_analitzar_canvis_dataframe_distingeix_canvis():
    original = pd.DataFrame([
        {"matricula": "1111BBB", "capacitat": 50},
        {"matricula": "2222CCC", "capacitat": 55},
    ])
    editat = pd.DataFrame([
        {"matricula": "1111BBB", "capacitat": 60},
        {"matricula": "3333DDD", "capacitat": 40},
    ])

    afegides, modificades, eliminades = database.analitzar_canvis_dataframe(
        original, editat, "matricula", ["capacitat"]
    )

    assert [fila["matricula"] for fila in afegides] == ["3333DDD"]
    assert [fila["matricula"] for fila in modificades] == ["1111BBB"]
    assert eliminades == ["2222CCC"]


def test_desar_autocars_aplica_canvis_sense_reconstruir_taula(monkeypatch, tmp_path):
    fitxer = configurar_sqlite_temporal(monkeypatch, tmp_path)
    database.init_db()

    with sqlite3.connect(fitxer) as conn:
        conn.executemany(
            "INSERT INTO autocars VALUES (?, ?, ?, ?, ?)",
            [
                ("1111BBB", 50, "Sí", "Sí", "H"),
                ("2222CCC", 55, "No", "Sí", "M"),
            ],
        )

    database.desar_canvis_autocars(
        afegides=[{
            "matricula": "3333DDD", "capacitat": 40, "acces_pmr": "Sí",
            "aire_acondicionat": "No", "conductor": "H",
        }],
        modificades=[{
            "matricula": "1111BBB", "capacitat": 60, "acces_pmr": "Sí",
            "aire_acondicionat": "Sí", "conductor": "H",
        }],
        eliminades=[],
    )

    with sqlite3.connect(fitxer) as conn:
        files = conn.execute(
            "SELECT matricula, capacitat FROM autocars ORDER BY matricula"
        ).fetchall()

    assert files == [("1111BBB", 60), ("2222CCC", 55), ("3333DDD", 40)]
