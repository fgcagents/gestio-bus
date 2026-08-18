"""Pantalla operativa d'arribades, sortides i captura OCR."""

from datetime import datetime
import hashlib
import io
import re

import easyocr
import numpy as np
from PIL import Image, ImageOps
import streamlit as st

from database import (
    PATRO_MATRICULA,
    calcular_sentit,
    get_db_connection,
    matricula_valida,
    read_dataframe,
    vehicles_esperant,
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
    # Les matrícules només necessiten el model llatí bàsic. Evitar un segon
    # idioma redueix el temps d'inicialització i la memòria del procés.
    return easyocr.Reader(["en"], gpu=False)


CARACTERS_MATRICULA = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def preparar_imatge_ocr(photo_bytes):
    """Orienta, retalla i limita la fotografia abans d'executar EasyOCR."""
    with Image.open(io.BytesIO(photo_bytes)) as original:
        imatge = ImageOps.exif_transpose(original).convert("RGB")

    amplada, alcada = imatge.size
    # La guia de captura demana centrar la matrícula. Eliminem la major part
    # del vehicle i del fons per reduir molt la feina del detector de text.
    imatge = imatge.crop((
        int(amplada * 0.12),
        int(alcada * 0.28),
        int(amplada * 0.88),
        int(alcada * 0.72),
    ))
    imatge.thumbnail((1280, 720), Image.Resampling.LANCZOS)
    return np.asarray(imatge)


def seleccionar_candidat_ocr(resultats, mida_imatge):
    """Tria el candidat més fiable sense barrejar deteccions independents."""
    if not resultats:
        return "", 0.0

    amplada, alcada = mida_imatge
    centre_imatge = (amplada / 2, alcada / 2)
    candidats = []
    for caixa, text, confianca in resultats:
        candidat = netejar_i_filtrar_matricula(text)
        if not candidat:
            continue

        centre_x = sum(punt[0] for punt in caixa) / len(caixa)
        centre_y = sum(punt[1] for punt in caixa) / len(caixa)
        distancia_relativa = (
            abs(centre_x - centre_imatge[0]) / max(amplada, 1)
            + abs(centre_y - centre_imatge[1]) / max(alcada, 1)
        )
        # La confiança és el criteri principal; la proximitat al centre
        # resol empats i evita prioritzar rètols del fons.
        puntuacio = float(confianca) - 0.15 * distancia_relativa
        candidats.append((puntuacio, float(confianca), candidat))

    if not candidats:
        return "", 0.0
    _, confianca, candidat = max(candidats)
    return candidat, confianca


PREFIX_CAMP_MATRICULA = "camp_matricula_operativa_"


def _normalitzar_matricula_operativa(clau_camp):
    valor = st.session_state.get(clau_camp, "")
    st.session_state["matricula_operativa"] = valor.strip().upper()


def _renovar_camp_matricula(valor=""):
    """Prepara un camp nou sense modificar el giny actiu de Streamlit."""
    st.session_state["matricula_operativa"] = valor.strip().upper()
    st.session_state["versio_matricula_operativa"] = (
        st.session_state.get("versio_matricula_operativa", 0) + 1
    )


def _context_matricula(matricula):
    """Llegeix el registre obert i la flota amb una sola connexió a la BD."""
    if not matricula_valida(matricula):
        return None, False

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                r.id,
                r.hora_entrada,
                r.estacio,
                CASE WHEN a.matricula IS NULL THEN 0 ELSE 1 END
            FROM (SELECT ? AS matricula) AS target
            LEFT JOIN autocars AS a
                ON a.matricula = target.matricula
            LEFT JOIN registres AS r
                ON r.id = (
                    SELECT id
                    FROM registres
                    WHERE matricula = target.matricula
                      AND estat = 'Esperant'
                    ORDER BY id DESC
                    LIMIT 1
                )
        """, (matricula,))
        registre_id, hora_entrada, estacio, catalogat = cursor.fetchone()
        registre = (
            (registre_id, hora_entrada, estacio)
            if registre_id is not None
            else None
        )
        return registre, bool(catalogat)
    finally:
        conn.close()


def _registrar_acces(matricula, estacio_seleccionada, dades_autocar=None):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
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
            cursor.execute(
                "SELECT 1 FROM autocars WHERE matricula = ?",
                (matricula,),
            )
            if cursor.fetchone() is None:
                if not dades_autocar:
                    raise ValueError(
                        "Cal completar la fitxa ràpida de l'autocar."
                    )
                cursor.execute("""
                    INSERT INTO autocars (
                        matricula, capacitat, acces_pmr,
                        aire_acondicionat, conductor
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(matricula) DO NOTHING
                """, (
                    matricula,
                    dades_autocar["capacitat"],
                    dades_autocar["acces_pmr"],
                    dades_autocar["aire_acondicionat"],
                    dades_autocar["conductor"],
                ))
            cursor.execute("""
                INSERT INTO registres (matricula, hora_entrada, estacio, estat)
                VALUES (?, ?, ?, 'Esperant')
            """, (matricula, ara, estacio_seleccionada))
            operacio = "arribada"
            missatge = f"Arribada registrada per a {matricula} a les {ara}."

        conn.commit()
        return operacio, missatge
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
    st.session_state.pop("ocr_confidence", None)
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
        with st.spinner("Preparant el lector i llegint la matrícula..."):
            imatge_ocr = preparar_imatge_ocr(photo_bytes)
            resultats = carregar_ocr().readtext(
                imatge_ocr,
                detail=1,
                decoder="greedy",
                allowlist=CARACTERS_MATRICULA,
                paragraph=False,
                batch_size=1,
                workers=0,
                canvas_size=1280,
                mag_ratio=1.0,
            )
            candidat, confianca = seleccionar_candidat_ocr(
                resultats,
                (imatge_ocr.shape[1], imatge_ocr.shape[0]),
            )
            st.session_state["ocr_photo_hash"] = photo_hash
            st.session_state["ocr_candidate"] = candidat
            st.session_state["ocr_confidence"] = confianca
            st.session_state["ocr_sense_text"] = not bool(resultats)

    candidat = st.session_state.get("ocr_candidate", "")
    if candidat:
        st.success(
            f"Matrícula detectada: **{candidat}**",
            icon=":material/check_circle:",
        )
        if st.button(
            f"Utilitzar {candidat}",
            type="primary",
            icon=":material/check:",
            width="stretch",
        ):
            _renovar_camp_matricula(candidat)
            st.session_state["matricula_context"] = None
            _reiniciar_captura_ocr()
            st.rerun()
    elif st.session_state.get("ocr_sense_text"):
        st.warning(
            "No s'ha detectat text. Torna a fer la fotografia o entra-la manualment.",
            icon=":material/warning:",
        )
    else:
        st.warning(
            "No s'ha pogut identificar una matrícula vàlida.",
            icon=":material/warning:",
        )


def _registrar_moviment_formulari():
    """Registra el moviment abans de renderitzar de nou els camps del formulari."""
    matricula = st.session_state.get("matricula_operativa", "").strip().upper()
    estacio = st.session_state.get("estacio_sortida")

    if not matricula_valida(matricula):
        return
    if estacio not in {"SR", "GR"}:
        st.session_state["avis_operativa"] = (
            "Selecciona l'estació abans de registrar el moviment."
        )
        return

    dades_autocar = None
    if "alta_rapida_capacitat" in st.session_state:
        dades_autocar = {
            "capacitat": st.session_state["alta_rapida_capacitat"],
            "acces_pmr": st.session_state["alta_rapida_pmr"],
            "aire_acondicionat": st.session_state["alta_rapida_aire"],
            "conductor": st.session_state["alta_rapida_conductor"],
        }

    try:
        _, missatge = _registrar_acces(matricula, estacio, dades_autocar)
    except Exception as error:
        st.session_state["error_operativa"] = (
            f"No s'ha pogut registrar el moviment: {error}"
        )
        return

    st.session_state["missatge_operativa"] = missatge
    _renovar_camp_matricula()
    st.session_state["matricula_context"] = None
    st.session_state["estacio_sortida"] = None
    for clau in (
        "alta_rapida_capacitat",
        "alta_rapida_pmr",
        "alta_rapida_aire",
        "alta_rapida_conductor",
    ):
        st.session_state.pop(clau, None)
    _reiniciar_captura_ocr()
    _ultims_moviments.clear()
    vehicles_esperant.clear()


@st.cache_data(ttl=5, show_spinner=False)
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


@st.fragment
def _render_panell_operativa():
    st.session_state.setdefault("matricula_operativa", "")
    st.session_state.setdefault("versio_matricula_operativa", 0)
    st.session_state.setdefault("matricula_context", None)
    st.session_state.setdefault("estacio_sortida", None)
    st.session_state.setdefault("versio_camera_ocr", 0)
    missatge = st.session_state.pop("missatge_operativa", None)
    if missatge:
        st.toast(missatge, icon=":material/check_circle:")

    error = st.session_state.pop("error_operativa", None)
    if error:
        st.error(error, icon=":material/error:")

    avis = st.session_state.pop("avis_operativa", None)
    if avis:
        st.warning(avis, icon=":material/warning:")

    with st.container(border=True):
        clau_camp_matricula = (
            f"{PREFIX_CAMP_MATRICULA}"
            f"{st.session_state['versio_matricula_operativa']}"
        )
        for clau in tuple(st.session_state):
            if (
                isinstance(clau, str)
                and clau.startswith(PREFIX_CAMP_MATRICULA)
                and clau != clau_camp_matricula
            ):
                st.session_state.pop(clau, None)

        columna_matricula, columna_camera = st.columns([3, 1])
        with columna_matricula:
            matricula = st.text_input(
                "Matrícula",
                value=st.session_state["matricula_operativa"],
                key=clau_camp_matricula,
                placeholder="1234BCD",
                max_chars=7,
                on_change=_normalitzar_matricula_operativa,
                args=(clau_camp_matricula,),
            ).strip().upper()
        with columna_camera:
            st.write("")
            if st.button(
                "Capturar matrícula",
                icon=":material/photo_camera:",
                width="stretch",
            ):
                dialog_captura_ocr()

        registre_obert, autocar_catalogat = _context_matricula(matricula)
        requereix_alta = bool(
            matricula_valida(matricula)
            and not registre_obert
            and not autocar_catalogat
        )
        if st.session_state.get("matricula_context") != matricula:
            st.session_state["matricula_context"] = matricula
            st.session_state["estacio_sortida"] = (
                registre_obert[2] if registre_obert and registre_obert[2] else None
            )
            for clau in (
                "alta_rapida_capacitat",
                "alta_rapida_pmr",
                "alta_rapida_aire",
                "alta_rapida_conductor",
            ):
                st.session_state.pop(clau, None)

        if matricula and not matricula_valida(matricula):
            st.warning(
                "Format esperat: 4 xifres i 3 consonants, per exemple 1234BCD.",
                icon=":material/warning:",
            )

        if registre_obert:
            _, hora_entrada, estacio_arribada = registre_obert
            st.info(
                f"**Sortida pendent** · Arribada a {estacio_arribada or '-'} "
                f"a les {hora_entrada}",
                icon=":material/logout:",
            )
            etiqueta_accio = "Registrar SORTIDA"
            icona_accio = ":material/logout:"
        else:
            if requereix_alta:
                st.warning(
                    "**Autocar no catalogat.** Completa les dades del nou "
                    "autocar abans de registrar l'arribada.",
                    icon=":material/directions_bus:",
                )
            elif matricula_valida(matricula):
                st.info(
                    "**Nova arribada preparada.** Selecciona l'estació i "
                    "confirma el moviment.",
                    icon=":material/login:",
                )
            etiqueta_accio = "Registrar ARRIBADA"
            icona_accio = ":material/login:"

        estacio_bloquejada = bool(registre_obert and registre_obert[2])
        with st.form("formulari_moviment", border=False):
            estacio = st.segmented_control(
                "Estació",
                options=["SR", "GR"],
                key="estacio_sortida",
                selection_mode="single",
                disabled=estacio_bloquejada,
            )
            if requereix_alta:
                st.markdown("**Dades del nou autocar**")
                columna_capacitat, columna_pmr = st.columns(2)
                with columna_capacitat:
                    st.number_input(
                        "Capacitat",
                        min_value=1,
                        max_value=120,
                        value=55,
                        key="alta_rapida_capacitat",
                    )
                with columna_pmr:
                    st.selectbox(
                        "Accés PMR",
                        ["Sí", "No"],
                        key="alta_rapida_pmr",
                    )
                columna_aire, columna_conductor = st.columns(2)
                with columna_aire:
                    st.selectbox(
                        "Aire condicionat",
                        ["Sí", "No"],
                        key="alta_rapida_aire",
                    )
                with columna_conductor:
                    st.selectbox(
                        "Conductor",
                        ["H", "M"],
                        key="alta_rapida_conductor",
                    )
            st.form_submit_button(
                etiqueta_accio,
                type="primary",
                icon=icona_accio,
                width="stretch",
                disabled=not matricula_valida(matricula),
                on_click=_registrar_moviment_formulari,
            )

    st.subheader("Últims moviments")
    ultims = _ultims_moviments()
    if ultims.empty:
        st.info(
            "Encara no hi ha moviments registrats.",
            icon=":material/info:",
        )
    else:
        st.dataframe(ultims, width="stretch", hide_index=True)


def render_operativa():
    st.header(":material/swap_vert: Control d'arribades i sortides")
    st.caption("Registra un moviment manualment o captura la matrícula amb la càmera.")
    _render_panell_operativa()
