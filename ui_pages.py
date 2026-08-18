"""Pàgines de consulta, flota, indicadors i manteniment."""

from datetime import date, datetime
import io

import pandas as pd
import streamlit as st

from database import (
    DATABASE_INTEGRITY_ERRORS,
    afegir_autocar,
    analitzar_canvis_dataframe,
    desar_canvis_autocars,
    desar_canvis_registres,
    get_db_connection,
    matricula_valida,
    read_dataframe,
)


CONSULTA_REGISTRES = """
    SELECT
        r.id AS "ID Registre",
        r.matricula AS "Matrícula",
        r.hora_entrada AS "Arribada",
        COALESCE(r.hora_sortida, '-') AS "Sortida",
        COALESCE(r.estacio, '-') AS "Estació",
        COALESCE(r.sentit, '-') AS "Sentit",
        r.estat AS "Estat actual",
        COALESCE(CAST(a.capacitat AS TEXT), 'No catalogat') AS "Capacitat",
        COALESCE(a.acces_pmr, '-') AS "Accés PMR",
        COALESCE(a.aire_acondicionat, '-') AS "Aire condicionat",
        COALESCE(a.conductor, '-') AS "Conductor"
    FROM registres r
    LEFT JOIN autocars a ON r.matricula = a.matricula
    ORDER BY r.id DESC
"""


def _llegir_dataframe(consulta):
    conn = get_db_connection()
    try:
        return read_dataframe(consulta, conn)
    finally:
        conn.close()


@st.fragment
def render_registres():
    st.header("Registres")
    st.caption("Consulta l'historial de moviments i descarrega les dades quan ho necessitis.")

    historial, exportacio = st.tabs(["Historial", "Exportació"])
    df_registres = _llegir_dataframe(CONSULTA_REGISTRES)

    with historial:
        if df_registres.empty:
            st.info("Encara no hi ha cap moviment registrat.")
        else:
            esperant = int((df_registres["Estat actual"] == "Esperant").sum())
            columna_esperant, columna_total = st.columns(2)
            columna_esperant.metric("Vehicles esperant", esperant)
            columna_total.metric("Moviments registrats", len(df_registres))
            st.dataframe(df_registres, width="stretch", hide_index=True)

    with exportacio:
        st.subheader("Exportar dades")
        st.caption("L'arxiu inclou l'historial complet i el llistat de la flota.")
        df_autocars = _llegir_dataframe("SELECT * FROM autocars ORDER BY matricula")
        sortida = io.BytesIO()
        amb_sortida_buida = df_registres.replace({"-": ""})
        with pd.ExcelWriter(sortida, engine="openpyxl") as writer:
            amb_sortida_buida.to_excel(
                writer, sheet_name="Historial i accessos", index=False
            )
            df_autocars.to_excel(writer, sheet_name="Flota autocars", index=False)

        st.download_button(
            "Descarregar informe Excel",
            data=sortida.getvalue(),
            file_name=(
                "registre_autobusos_"
                f"{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
            ),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            icon=":material/download:",
            width="stretch",
            on_click="ignore",
        )


@st.fragment
def render_indicadors():
    st.header("Indicadors")
    st.caption("Visió ràpida de l'activitat i l'estat actual dels autocars.")

    avui = date.today().isoformat()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(DISTINCT matricula)
            FROM registres
            WHERE DATE(hora_entrada) = ?
        """, (avui,))
        autocars_del_dia = cursor.fetchone()[0] or 0

        cursor.execute("""
            SELECT estacio, COUNT(*)
            FROM registres
            WHERE estat = 'Esperant'
            GROUP BY estacio
        """)
        espera_per_estacio = dict(cursor.fetchall())

        cursor.execute("""
            SELECT sentit, COUNT(*)
            FROM registres
            WHERE estat = 'Circulant'
            GROUP BY sentit
        """)
        circulant_per_sentit = dict(cursor.fetchall())

        cursor.execute("""
            SELECT CAST(SUBSTR(hora_entrada, 12, 2) AS INTEGER), COUNT(*)
            FROM registres
            WHERE DATE(hora_entrada) = ?
            GROUP BY CAST(SUBSTR(hora_entrada, 12, 2) AS INTEGER)
            ORDER BY 1
        """, (avui,))
        per_franja = cursor.fetchall()
    finally:
        conn.close()

    columnes = st.columns(4)
    columnes[0].metric("Autocars del dia", autocars_del_dia)
    columnes[1].metric("En espera", sum(espera_per_estacio.values()))
    columnes[2].metric("Circulant", sum(circulant_per_sentit.values()))
    mitjana = sum(valor for _, valor in per_franja) / len(per_franja) if per_franja else 0
    columnes[3].metric("Mitjana per hora", f"{mitjana:.1f}")

    estacions, sentits = st.columns(2)
    with estacions:
        st.subheader("Espera per estació")
        if espera_per_estacio:
            for estacio, quantitat in sorted(espera_per_estacio.items()):
                st.metric(estacio or "Sense estació", quantitat)
        else:
            st.info("No hi ha autocars esperant.")

    with sentits:
        st.subheader("Circulació per sentit")
        if circulant_per_sentit:
            for sentit, quantitat in sorted(circulant_per_sentit.items()):
                st.metric(sentit or "Sense sentit", quantitat)
        else:
            st.info("No hi ha autocars circulant.")

    st.subheader("Distribució horària")
    if per_franja:
        franges = pd.DataFrame(per_franja, columns=["Hora", "Autocars"])
        franges["Hora"] = franges["Hora"].map(
            lambda hora: f"{hora:02d}:00–{hora + 1:02d}:00"
        )
        st.bar_chart(franges.set_index("Hora"))
    else:
        st.info("Encara no hi ha dades d'avui.")


def _formulari_alta_autocar():
    st.subheader("Afegir un autocar")
    with st.form("form_alta_autocar", clear_on_submit=True):
        matricula = st.text_input("Matrícula", placeholder="5678JKL").strip().upper()
        capacitat = st.number_input(
            "Capacitat", min_value=1, max_value=120, value=55
        )
        pmr = st.selectbox("Accés PMR", ["Sí", "No"])
        aire = st.selectbox("Aire condicionat", ["Sí", "No"])
        conductor = st.selectbox("Conductor", ["H", "M"])
        submitted = st.form_submit_button(
            "Afegir a la flota",
            type="primary",
            icon=":material/add:",
            width="stretch",
        )

    if not submitted:
        return
    if not matricula_valida(matricula):
        st.error("La matrícula ha de tenir 4 xifres i 3 consonants.")
        return
    try:
        afegir_autocar(matricula, capacitat, pmr, aire, conductor)
        st.success(f"L'autocar {matricula} s'ha afegit a la flota.")
    except DATABASE_INTEGRITY_ERRORS:
        st.error(f"La matrícula {matricula} ja està registrada.")


def _editor_autocars():
    st.subheader("Editar la flota")
    st.caption(
        "Fes els canvis que necessitis i desa'ls tots alhora. "
        "La taula no es recarrega mentre l'edites."
    )
    original = _llegir_dataframe("SELECT * FROM autocars ORDER BY matricula")
    st.session_state.setdefault("versio_editor_autocars", 0)
    versio = st.session_state["versio_editor_autocars"]
    with st.form(f"formulari_editor_autocars_{versio}"):
        editat = st.data_editor(
            original,
            num_rows="dynamic",
            key=f"editor_autocars_{versio}",
            column_config={
                "matricula": st.column_config.TextColumn(
                    "Matrícula", required=True
                ),
                "capacitat": st.column_config.NumberColumn(
                    "Capacitat", min_value=1, max_value=150
                ),
                "acces_pmr": st.column_config.SelectboxColumn(
                    "Accés PMR", options=["Sí", "No"]
                ),
                "aire_acondicionat": st.column_config.SelectboxColumn(
                    "Aire condicionat", options=["Sí", "No"]
                ),
                "conductor": st.column_config.TextColumn("Conductor"),
            },
            width="stretch",
            hide_index=True,
        )
        confirmat = st.checkbox(
            "Confirmo qualsevol modificació o baixa feta a la taula",
            key=f"confirmar_autocars_{versio}",
        )
        desar = st.form_submit_button(
            "Desar canvis de la flota",
            icon=":material/save:",
            type="primary",
        )

    if not desar:
        return

    afegides, modificades, eliminades = analitzar_canvis_dataframe(
        original,
        editat,
        "matricula",
        ["capacitat", "acces_pmr", "aire_acondicionat", "conductor"],
    )
    hi_ha_canvis = bool(afegides or modificades or eliminades)
    requereix_confirmacio = bool(modificades or eliminades)

    if not hi_ha_canvis:
        st.info("No hi ha canvis per desar.")
        return
    if requereix_confirmacio and not confirmat:
        st.warning(
            "Marca la confirmació abans de desar modificacions o baixes."
        )
        return

    try:
        desar_canvis_autocars(afegides, modificades, eliminades)
        st.session_state["versio_editor_autocars"] += 1
        st.cache_data.clear()
        st.success(
            f"Canvis desats: {len(afegides)} altes, "
            f"{len(modificades)} modificacions i {len(eliminades)} baixes."
        )
    except Exception as error:
        st.error(f"No s'han pogut desar els canvis: {error}")


@st.fragment
def render_flota():
    st.header("Flota")
    st.caption("Consulta, amplia o corregeix el catàleg d'autocars.")

    consulta, alta, edicio = st.tabs(["Llistat", "Alta", "Edició"])
    with consulta:
        flota = _llegir_dataframe("""
            SELECT
                matricula AS "Matrícula",
                capacitat AS "Capacitat",
                acces_pmr AS "Accés PMR",
                aire_acondicionat AS "Aire condicionat",
                conductor AS "Conductor"
            FROM autocars
            ORDER BY matricula
        """)
        st.dataframe(flota, width="stretch", hide_index=True)
    with alta:
        _formulari_alta_autocar()
    with edicio:
        _editor_autocars()


@st.fragment
def render_manteniment():
    st.header("Manteniment")
    st.caption("Corregeix manualment moviments concrets quan sigui necessari.")

    original = _llegir_dataframe("SELECT * FROM registres ORDER BY id DESC")
    st.session_state.setdefault("versio_editor_registres", 0)
    versio = st.session_state["versio_editor_registres"]
    st.caption(
        "Fes els canvis que necessitis i desa'ls tots alhora. "
        "La taula no es recarrega mentre l'edites."
    )
    with st.form(f"formulari_editor_registres_{versio}"):
        editat = st.data_editor(
            original,
            num_rows="dynamic",
            key=f"editor_registres_{versio}",
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "matricula": st.column_config.TextColumn(
                    "Matrícula", required=True
                ),
                "hora_entrada": st.column_config.TextColumn("Hora d'arribada"),
                "hora_sortida": st.column_config.TextColumn("Hora de sortida"),
                "estacio": st.column_config.SelectboxColumn(
                    "Estació", options=["SR", "GR"]
                ),
                "sentit": st.column_config.TextColumn("Sentit", disabled=True),
                "estat": st.column_config.SelectboxColumn(
                    "Estat", options=["Esperant", "Circulant"]
                ),
            },
            width="stretch",
            hide_index=True,
        )
        confirmat = st.checkbox(
            "Confirmo qualsevol modificació o eliminació feta a la taula",
            key=f"confirmar_registres_{versio}",
        )
        desar = st.form_submit_button(
            "Desar canvis dels registres",
            icon=":material/save:",
            type="primary",
        )

    if not desar:
        return

    afegides, modificades, eliminades = analitzar_canvis_dataframe(
        original,
        editat,
        "id",
        ["matricula", "hora_entrada", "hora_sortida", "estacio", "sentit", "estat"],
    )
    hi_ha_canvis = bool(afegides or modificades or eliminades)
    requereix_confirmacio = bool(modificades or eliminades)
    if not hi_ha_canvis:
        st.info("No hi ha canvis per desar.")
        return
    if requereix_confirmacio and not confirmat:
        st.warning(
            "Marca la confirmació abans de desar modificacions o eliminacions."
        )
        return

    try:
        desar_canvis_registres(afegides, modificades, eliminades)
        st.session_state["versio_editor_registres"] += 1
        st.cache_data.clear()
        st.success(
            f"Canvis desats: {len(afegides)} altes, "
            f"{len(modificades)} modificacions i "
            f"{len(eliminades)} eliminacions."
        )
    except Exception as error:
        st.error(f"No s'han pogut desar els registres: {error}")
