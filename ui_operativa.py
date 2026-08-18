"""Pantalla operativa d'arribades, sortides i captura OCR."""

from datetime import datetime
import hashlib
import re

import easyocr
import streamlit as st

from database import (
    DATABASE_INTEGRITY_ERRORS,
    PATRO_MATRICULA,
    afegir_autocar,
    calcular_sentit,
    get_db_connection,
    matricula_valida,
    read_dataframe,
)


def netejar_i_filtrar_matricula(text_raw):
    """Extreu i normalitza exclusivament una matrícula del format 1234BCD."""
    text_net = re.sub(r"[^A-Z0-9]", "", text_raw.upper())

    match_actual = re.search(PATRO_MATRICULA, text_net)
    if match_actual:
        return match_actual.group(0)

    lletres_a_digits = str.maketrans({
        "O": "0", "Q": "0", "D": "0", "I": "1", "L": "1",
        "T": "1", "Z": "2", "A": "4", "S": "5", "G": "6", "B": "8",
    })
    digits_a_lletres = str.maketrans({
        "0": "D", "1": "L", "2": "Z", "5": "S", "6": "G",
        "7": "T", "8": "B", "9": "G",
    })

    for inici in range(max(0, len(text_net) - 6)):
        bloc = text_net[inici:inici + 7]
        part_numerica = bloc[:4]
        part_lletres = bloc[4:]
        if (
            sum(caracter.isdigit() for caracter in part_numerica) < 2
            or sum(caracter.isalpha() for caracter in part_lletres) < 2
        ):
            continue

        candidat = (
            part_numerica.translate(lletres_a_digits)
            + part_lletres.translate(digits_a_lletres)
        )
        if re.fullmatch(PATRO_MATRICULA, candidat):
            return candidat

    return ""


@st.cache_resource
def carregar_ocr():
    return easyocr.Reader(["es", "en"])


def _normalitzar_matricula_operativa():
    valor = st.session_state.get("matricula_operativa", "")
    st.session_state["matricula_operativa"] = valor.strip().upper()


def _registre_obert(matricula):
    if not matricula_valida(matricula):
        return None
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, hora_entrada, estacio
            FROM registres
            WHERE matricula = ? AND estat = 'Esperant'
            ORDER BY id DESC LIMIT 1
        """, (matricula,))
        return cursor.fetchone()
    finally:
        conn.close()


def _registrar_acces(matricula, estacio_seleccionada):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM autocars WHERE matricula = ?",
            (matricula,),
        )
        autocar_catalogat = cursor.fetchone() is not None

        cursor.execute("""
            SELECT id, hora_entrada, estacio
            FROM registres
            WHERE matricula = ? AND estat = 'Esperant'
            ORDER BY id DESC LIMIT 1
        """, (matricula,))
        registre_obert = cursor.fetchone()
        ara = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if registre_obert:
            registre_id, _, estacio_arribada = registre_obert
            estacio_sortida = estacio_arribada or estacio_seleccionada
            sentit = calcular_sentit(estacio_sortida)
            cursor.execute("""
                UPDATE registres
                SET hora_sortida = ?, sentit = ?, estat = 'Circulant'
                WHERE id = ?
            """, (ara, sentit, registre_id))
            operacio = "sortida"
            missatge = f"Sortida registrada per a {matricula} a les {ara}."
        else:
            cursor.execute("""
                INSERT INTO registres (matricula, hora_entrada, estacio, estat)
                VALUES (?, ?, ?, 'Esperant')
            """, (matricula, ara, estacio_seleccionada))
            operacio = "arribada"
            missatge = f"Arribada registrada per a {matricula} a les {ara}."

        conn.commit()
        return operacio, missatge, autocar_catalogat
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _reiniciar_captura_ocr():
    st.session_state["versio_camera_ocr"] = (
        st.session_state.get("versio_camera_ocr", 0) + 1
    )
    st.session_state.pop("ocr_photo_hash", None)
    st.session_state.pop("ocr_candidate", None)
    st.session_state.pop("ocr_sense_text", None)


@st.dialog("Captura de matrícula", width="large")
def dialog_captura_ocr():
    st.caption(
        "Centra la matrícula, evita reflexos i procura que ocupi bona part de la imatge."
    )
    versio = st.session_state.get("versio_camera_ocr", 0)
    fotografia = st.camera_input(
        "Fes una fotografia de la matrícula",
        key=f"camera_ocr_{versio}",
    )

    if fotografia is None:
        return

    photo_bytes = fotografia.getvalue()
    photo_hash = hashlib.sha256(photo_bytes).hexdigest()
    if st.session_state.get("ocr_photo_hash") != photo_hash:
        with st.spinner("Llegint la matrícula..."):
            resultats = carregar_ocr().readtext(photo_bytes, detail=0)
            candidat = netejar_i_filtrar_matricula("".join(resultats)) if resultats else ""
            st.session_state["ocr_photo_hash"] = photo_hash
            st.session_state["ocr_candidate"] = candidat
            st.session_state["ocr_sense_text"] = not bool(resultats)

    candidat = st.session_state.get("ocr_candidate", "")
    if candidat:
        st.success(f"Matrícula detectada: **{candidat}**")
        if st.button(
            f"Utilitzar {candidat}",
            type="primary",
            icon=":material/check:",
            width="stretch",
        ):
            st.session_state["matricula_operativa"] = candidat
            st.session_state["matricula_context"] = None
            _reiniciar_captura_ocr()
            st.rerun()
    elif st.session_state.get("ocr_sense_text"):
        st.warning("No s'ha detectat text. Torna a fer la fotografia o entra-la manualment.")
    else:
        st.warning("No s'ha pogut identificar una matrícula vàlida.")


@st.dialog("Autocar no catalogat")
def dialog_alta_rapida(matricula):
    st.write(f"Vols afegir **{matricula}** a la flota?")
    with st.form(f"alta_rapida_{matricula}"):
        capacitat = st.number_input(
            "Capacitat", min_value=1, max_value=120, value=55
        )
        pmr = st.selectbox("Accés PMR", ["Sí", "No"])
        aire = st.selectbox("Aire condicionat", ["Sí", "No"])
        conductor = st.selectbox("Conductor", ["H", "M"])
        desar = st.form_submit_button(
            "Afegir a la flota",
            type="primary",
            icon=":material/add:",
            width="stretch",
        )

    if desar:
        try:
            afegir_autocar(matricula, capacitat, pmr, aire, conductor)
            st.session_state["missatge_operativa"] = (
                f"L'autocar {matricula} s'ha afegit a la flota."
            )
        except DATABASE_INTEGRITY_ERRORS:
            st.session_state["missatge_operativa"] = (
                f"L'autocar {matricula} ja constava a la flota."
            )
        except ValueError as error:
            st.session_state["missatge_operativa"] = str(error)
        st.session_state["matricula_pendent_alta"] = None
        st.rerun()

    if st.button("Ara no", icon=":material/schedule:", width="stretch"):
        st.session_state["matricula_pendent_alta"] = None
        st.rerun()


def _ultims_moviments():
    conn = get_db_connection()
    try:
        return read_dataframe("""
            SELECT
                matricula AS "Matrícula",
                hora_entrada AS "Arribada",
                COALESCE(hora_sortida, '-') AS "Sortida",
                COALESCE(estacio, '-') AS "Estació",
                estat AS "Estat"
            FROM registres
            ORDER BY id DESC
            LIMIT 5
        """, conn)
    finally:
        conn.close()


def render_operativa():
    st.header("Control d'arribades i sortides")
    st.caption("Registra un moviment manualment o captura la matrícula amb la càmera.")

    st.session_state.setdefault("matricula_operativa", "")
    st.session_state.setdefault("matricula_context", None)
    st.session_state.setdefault("estacio_sortida", None)
    st.session_state.setdefault("versio_camera_ocr", 0)
    st.session_state.setdefault("matricula_pendent_alta", None)

    missatge = st.session_state.pop("missatge_operativa", None)
    if missatge:
        st.toast(missatge, icon=":material/check_circle:")
        st.success(missatge)

    with st.container(border=True):
        columna_matricula, columna_camera = st.columns([3, 1])
        with columna_matricula:
            matricula = st.text_input(
                "Matrícula",
                key="matricula_operativa",
                placeholder="1234BCD",
                max_chars=7,
                on_change=_normalitzar_matricula_operativa,
            ).strip().upper()
        with columna_camera:
            st.write("")
            if st.button(
                "Capturar matrícula",
                icon=":material/photo_camera:",
                width="stretch",
            ):
                dialog_captura_ocr()

        registre_obert = _registre_obert(matricula)
        if st.session_state.get("matricula_context") != matricula:
            st.session_state["matricula_context"] = matricula
            st.session_state["estacio_sortida"] = (
                registre_obert[2] if registre_obert and registre_obert[2] else None
            )

        if matricula and not matricula_valida(matricula):
            st.warning("Format esperat: 4 xifres i 3 consonants, per exemple 1234BCD.")

        estacio_bloquejada = bool(registre_obert and registre_obert[2])
        estacio = st.segmented_control(
            "Estació",
            options=["SR", "GR"],
            key="estacio_sortida",
            selection_mode="single",
            disabled=estacio_bloquejada,
        )

        if registre_obert:
            _, hora_entrada, estacio_arribada = registre_obert
            st.info(
                f"**Sortida pendent** · Arribada a {estacio_arribada or '-'} "
                f"a les {hora_entrada}"
            )
            etiqueta_accio = "Registrar SORTIDA"
            icona_accio = ":material/logout:"
        else:
            if matricula_valida(matricula):
                st.caption("Nova arribada preparada per registrar.")
            etiqueta_accio = "Registrar ARRIBADA"
            icona_accio = ":material/login:"

        formulari_valid = matricula_valida(matricula) and estacio in {"SR", "GR"}
        if st.button(
            etiqueta_accio,
            type="primary",
            icon=icona_accio,
            width="stretch",
            disabled=not formulari_valid,
        ):
            try:
                _, missatge, catalogat = _registrar_acces(matricula, estacio)
                st.session_state["missatge_operativa"] = missatge
                if not catalogat:
                    st.session_state["matricula_pendent_alta"] = matricula
                st.session_state["matricula_operativa"] = ""
                st.session_state["matricula_context"] = None
                st.session_state["estacio_sortida"] = None
                _reiniciar_captura_ocr()
                st.rerun()
            except Exception as error:
                st.error(f"No s'ha pogut registrar el moviment: {error}")

    st.subheader("Últims moviments")
    ultims = _ultims_moviments()
    if ultims.empty:
        st.info("Encara no hi ha moviments registrats.")
    else:
        st.dataframe(ultims, width="stretch", hide_index=True)

    pendent = st.session_state.get("matricula_pendent_alta")
    if pendent:
        dialog_alta_rapida(pendent)
