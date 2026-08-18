from pathlib import Path

from streamlit.testing.v1 import AppTest

import database


def render_pagina_de_prova(nom):
    from ui_pages import (
        render_flota,
        render_indicadors,
        render_manteniment,
        render_registres,
    )

    pagines = {
        "registres": render_registres,
        "indicadors": render_indicadors,
        "flota": render_flota,
        "manteniment": render_manteniment,
    }
    pagines[nom]()


def test_pantalla_operativa_carrega_sense_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("GESTIO_BUS_SQLITE_FILE", str(tmp_path / "app.db"))
    monkeypatch.setattr(database, "DATABASE_BACKEND", "sqlite")
    monkeypatch.setattr(database, "SQLITE_FILE", tmp_path / "app.db")

    app_file = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_file))
    app.run(timeout=30)

    assert not app.exception
    assert app.header[0].value == "Control d'arribades i sortides"
    assert len(app.segmented_control) == 1
    assert {boto.label for boto in app.button} >= {
        "Capturar matrícula",
        "Registrar ARRIBADA",
    }
    assert len(app.get("camera_input")) == 0
    assert all(not boto.value for boto in app.button)


def test_sortida_preselecciona_estacio_arribada(monkeypatch, tmp_path):
    fitxer = tmp_path / "sortida.db"
    monkeypatch.setenv("GESTIO_BUS_SQLITE_FILE", str(fitxer))
    monkeypatch.setattr(database, "DATABASE_BACKEND", "sqlite")
    monkeypatch.setattr(database, "SQLITE_FILE", fitxer)
    database.init_db()

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO registres (matricula, hora_entrada, estacio, estat)
        VALUES (?, ?, ?, 'Esperant')
    """, ("1234BCD", "2026-08-18 10:00:00", "SR"))
    conn.commit()
    conn.close()

    app_file = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_file)).run(timeout=30)
    app.text_input[0].set_value("1234BCD").run(timeout=30)

    assert not app.exception
    assert app.segmented_control[0].value == "SR"
    assert "Registrar SORTIDA" in {boto.label for boto in app.button}


def test_sortida_deixa_el_formulari_net(monkeypatch, tmp_path):
    fitxer = tmp_path / "sortida_neta.db"
    monkeypatch.setenv("GESTIO_BUS_SQLITE_FILE", str(fitxer))
    monkeypatch.setattr(database, "DATABASE_BACKEND", "sqlite")
    monkeypatch.setattr(database, "SQLITE_FILE", fitxer)
    database.init_db()

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO registres (matricula, hora_entrada, estacio, estat)
        VALUES (?, ?, ?, 'Esperant')
    """, ("1234BCD", "2026-08-18 10:00:00", "SR"))
    conn.commit()
    conn.close()

    app_file = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_file)).run(timeout=30)
    app.text_input[0].set_value("1234BCD").run(timeout=30)
    clau_matricula_abans = app.text_input[0].key
    boto_sortida = next(
        boto for boto in app.button if boto.label == "Registrar SORTIDA"
    )
    boto_sortida.click().run(timeout=30)

    assert not app.exception
    assert not app.error
    assert not app.warning
    assert not app.success
    assert not app.info
    assert app.text_input[0].value == ""
    assert app.text_input[0].key != clau_matricula_abans
    assert app.segmented_control[0].value is None

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT estacio, sentit, estat, hora_sortida FROM registres ORDER BY id"
    )
    estacio, sentit, estat, hora_sortida = cursor.fetchone()
    assert (estacio, sentit, estat) == ("SR", "Descendent", "Circulant")
    assert hora_sortida
    conn.close()


def test_matricula_nova_desa_fitxa_rapida_abans_de_lentrada(
    monkeypatch, tmp_path
):
    fitxer = tmp_path / "matricula_nova.db"
    monkeypatch.setenv("GESTIO_BUS_SQLITE_FILE", str(fitxer))
    monkeypatch.setattr(database, "DATABASE_BACKEND", "sqlite")
    monkeypatch.setattr(database, "SQLITE_FILE", fitxer)
    database.init_db()

    app_file = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_file)).run(timeout=30)
    app.text_input[0].set_value("9876ZZZ").run(timeout=30)
    clau_matricula_abans = app.text_input[0].key
    boto_registre = next(
        boto for boto in app.button if boto.label == "Registrar ARRIBADA"
    )
    assert not boto_registre.disabled
    assert len(app.number_input) == 1
    assert app.number_input[0].label == "Capacitat"

    app.segmented_control[0].set_value("SR")
    boto_registre.click().run(timeout=30)

    assert not app.exception
    assert not app.error
    assert not app.warning
    assert not app.success
    assert app.text_input[0].value == ""
    assert app.text_input[0].key != clau_matricula_abans
    assert app.segmented_control[0].value is None

    conn = database.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT matricula, estacio, estat FROM registres ORDER BY id"
    )
    assert cursor.fetchall() == [("9876ZZZ", "SR", "Esperant")]
    cursor.execute("""
        SELECT matricula, capacitat, acces_pmr, aire_acondicionat, conductor
        FROM autocars
    """)
    assert cursor.fetchall() == [("9876ZZZ", 55, "Sí", "Sí", "H")]
    conn.close()


def test_pagines_secundaries_carreguen_sense_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("GESTIO_BUS_SQLITE_FILE", str(tmp_path / "pagines.db"))
    monkeypatch.setattr(database, "DATABASE_BACKEND", "sqlite")
    monkeypatch.setattr(database, "SQLITE_FILE", tmp_path / "pagines.db")
    database.init_db()

    pagines = [
        ("registres", "Registres"),
        ("indicadors", "Indicadors"),
        ("flota", "Flota"),
        ("manteniment", "Manteniment"),
    ]
    for nom, titol in pagines:
        app = AppTest.from_function(
            render_pagina_de_prova, args=(nom,)
        ).run(timeout=30)
        assert not app.exception
        assert app.header[0].value == titol
