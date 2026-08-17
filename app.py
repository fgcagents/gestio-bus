import streamlit as st
import pandas as pd
from datetime import datetime
import easyocr
import re
import io

from database import (
    DATABASE_INTEGRITY_ERRORS,
    calcular_sentit,
    database_status,
    get_db_connection,
    init_db,
    read_dataframe,
    sync_registres_sequence,
)

# Page config
st.set_page_config(page_title="Gestió de Flota i Accessos - Tall per Obres", layout="wide", page_icon="🚌")

def netejar_i_filtrar_matricula(text_raw):
    """Extreu i normalitza exclusivament una matrícula del format 1234BCD."""
    # Convertim a majúscules i eliminem espais i caràcters especials.
    text_net = re.sub(r'[^A-Z0-9]', '', text_raw.upper())

    # Format actual: 4 xifres i 3 consonants vàlides, sense vocals, Ñ ni Q.
    patro_matricula = r'\d{4}[B-DF-HJ-NPR-TV-Z]{3}'
    match_actual = re.search(patro_matricula, text_net)
    if match_actual:
        return match_actual.group(0)

    # EasyOCR pot confondre caràcters visualment semblants. Corregim cada
    # caràcter només segons la seva posició esperada dins de la matrícula.
    lletres_a_digits = str.maketrans({
        'O': '0', 'Q': '0', 'D': '0',
        'I': '1', 'L': '1', 'T': '1',
        'Z': '2', 'A': '4', 'S': '5',
        'G': '6', 'B': '8',
    })
    digits_a_lletres = str.maketrans({
        '0': 'D', '1': 'L', '2': 'Z', '5': 'S',
        '6': 'G', '7': 'T', '8': 'B', '9': 'G',
    })

    for inici in range(max(0, len(text_net) - 6)):
        bloc = text_net[inici:inici + 7]
        part_numerica = bloc[:4]
        part_lletres = bloc[4:]

        # Evita convertir paraules arbitràries en falses matrícules.
        if (
            sum(caracter.isdigit() for caracter in part_numerica) < 2
            or sum(caracter.isalpha() for caracter in part_lletres) < 2
        ):
            continue

        candidat = (
            part_numerica.translate(lletres_a_digits)
            + part_lletres.translate(digits_a_lletres)
        )
        if re.fullmatch(patro_matricula, candidat):
            return candidat

    return ""


def afegir_autocar_a_flota(matricula, capacitat, acces_pmr, aire_acondicionat, conductor):
    """Afegeix un autocar a la flota dins d'una transacció segura."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO autocars (
                matricula, capacitat, acces_pmr, aire_acondicionat, conductor
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            matricula,
            capacitat,
            acces_pmr,
            aire_acondicionat,
            conductor,
        ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def completar_alta_rapida():
    """Desa l'autocar pendent utilitzant els valors del formulari ràpid."""
    matricula = st.session_state.get("matricula_pendent_alta")
    if not matricula:
        return

    try:
        afegir_autocar_a_flota(
            matricula,
            st.session_state[f"capacitat_rapida_{matricula}"],
            st.session_state[f"pmr_rapid_{matricula}"],
            st.session_state[f"ac_rapid_{matricula}"],
            st.session_state[f"conductor_rapid_{matricula}"].strip(),
        )
        st.session_state["missatge_alta_rapida"] = (
            f"L'autocar {matricula} s'ha afegit correctament a la flota."
        )
    except DATABASE_INTEGRITY_ERRORS:
        st.session_state["missatge_alta_rapida"] = (
            f"La matrícula {matricula} ja constava a la flota."
        )
    finally:
        st.session_state["matricula_pendent_alta"] = None


def descartar_alta_rapida():
    """Tanca el formulari sense afegir l'autocar a la flota."""
    st.session_state["matricula_pendent_alta"] = None


try:
    init_db()
except Exception:
    st.error(
        "No s'ha pogut connectar amb la base de dades. "
        "Revisa el secret DATABASE_URL de Streamlit Cloud."
    )
    st.stop()

st.session_state.setdefault("matricula_pendent_alta", None)
st.session_state.setdefault("missatge_alta_rapida", None)

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['es', 'en'])

reader = load_ocr()

# Sidebar Navigation
st.sidebar.title("🚌 Gestió d'Autobusos")
# st.sidebar.markdown("**Control d'Accessos - Tall per Obres**")
db_label, db_is_persistent = database_status()
db_icon = "🟢" if db_is_persistent else "🟡"
st.sidebar.caption(f"{db_icon} Base de dades: {db_label}")

# Injectar CSS per millorar l'espaiat entre opcions del radio button
st.markdown("""
    <style>
   div[data-testid="stSidebar"] div[data-testid="stRadioGroup"] {
        gap: 18px;
    }
    div[data-testid="stSidebar"] label[data-testid="stRadioOption"] {
        padding-bottom: 8px;
        border-bottom: 1px solid rgba(255,255,255,0.08);
    }
    div[data-testid="stSidebar"] label[data-testid="stRadioOption"]:last-child {
        border-bottom: none;
    }
    
    </style>
""", unsafe_allow_html=True)

page = st.sidebar.radio("Navegació", [
    "📷 Arribada / Sortida",
    "📊 Registre Arribades / Sortides",
    "📈 KPI i Estadístiques",
    "🚌 Alta Autocars",
    "✏️ Edició i Manteniment de Taules",
    "📥 Exportació de Dades (Excel)"
])

# -----------------------------------------------------------------------------
# 1. CONTROL D'ACCESSOS (Càmera / Manual amb Filtre REGEX)
# -----------------------------------------------------------------------------
if page == "📷 Arribada / Sortida":
    st.header("📷 Control Arribades i Sortides")
    st.caption("Captura la matrícula mitjançant la càmera o escriu-la manualment per registrar l'entrada o sortida.")

    # CSS corregit: eliminem el max-width fix i forcem el 100% real de l'amplada
    # disponible tant al contenidor com al <video> intern.
    st.markdown("""
        <style>
        div[data-testid="stCameraInput"] {
            width: 100% !important;
        }
        div[data-testid="stCameraInput"] video {
            width: 100% !important;
            height: auto !important;
            border-radius: 10px;
            border: 2px solid #0066cc;
        }
        </style>
    """, unsafe_allow_html=True)

    # 1. Captura d'imatge a l'amplada total de la pàgina (fora de columnes)
    st.subheader("1. Captura amb Càmera")
    camera_photo = st.camera_input("Fes una foto a la matrícula del autobús")

    matricula_detectada = ""
    if camera_photo is not None:
        with st.spinner("Processant la imatge amb OCR..."):
            photo_bytes = camera_photo.getvalue()

            # Llegim i concatenem tot el text trobat a la imatge.
            results = reader.readtext(photo_bytes, detail=0)

            if results:
                raw_text = "".join(results)
                candidate = netejar_i_filtrar_matricula(raw_text)

                if candidate:
                    st.success(f"Matrícula detectada: **{candidate}**")
                    matricula_detectada = candidate
                else:
                    st.warning(
                        "No s'ha detectat cap matrícula amb el format "
                        "de 4 xifres i 3 lletres. Utilitza l'entrada manual."
                    )
            else:
                st.warning("No s'ha detectat cap text a la foto. Utilitza l'entrada manual.")

    st.divider()

    # 2. Confirmació / Entrada Manual, en una fila separada sota la càmera.
    # Aquí sí té sentit limitar l'amplada, ja que és un input curt i un botó.
    st.subheader("2. Confirmació / Entrada Manual")
    missatge_alta_rapida = st.session_state.pop("missatge_alta_rapida", None)
    if missatge_alta_rapida:
        st.success(missatge_alta_rapida)

    col_input, col_buit = st.columns([1, 1])
    with col_input:
        val_inicial = matricula_detectada if matricula_detectada else ""
        matricula_input = st.text_input("Matrícula del vehicle:", value=val_inicial, placeholder="Ex: 1234BCD").strip().upper()
    
    # Si la matrícula s'ha canviat, comprovar si hi ha un registre obert i preseleccionar l'estació
    estacio_preseleccionada = "Seleccionar..."
    if matricula_input:
        conn_check = get_db_connection()
        c_check = conn_check.cursor()
        c_check.execute("""
            SELECT estacio FROM registres 
            WHERE matricula = ? AND estat = 'Esperant' 
            ORDER BY id DESC LIMIT 1
        """, (matricula_input,))
        result = c_check.fetchone()
        if result and result[0]:
            estacio_preseleccionada = result[0]
            # Precarregar al session_state
            st.session_state.estacio_sortida = estacio_preseleccionada
        conn_check.close()

    # Radio buttons permanents per a l'estació (serveixen tant per OCR com per entrada manual)
    st.subheader("Estació de sortida")
    if estacio_preseleccionada != "Seleccionar...":
        st.info(f"📍 Estació detectada de l'entrada: **{estacio_preseleccionada}**")
    
    estacio_seleccionada = st.radio(
        "Estació",
        ["Seleccionar...", "SR", "GR"],
        key="estacio_sortida",
        label_visibility="collapsed",
        horizontal=True,
        help="Selecciona l'estació d'on surt l'autobús. Es desa quan es registra la sortida."
    )

    if st.button("🔄 Registrar Accés (Entrada/Sortida)", type="primary", use_container_width=True):
        if not matricula_input:
            st.error("Si us plau, introdueix una matrícula vàlida.")
        elif st.session_state.get("estacio_sortida") == "Seleccionar...":
            st.error("Si us plau, selecciona una estació vàlida (SR o GR).")
        else:
            conn = get_db_connection()
            c = conn.cursor()
            
            # Comprovar si l'autocar està catalogat a la flota
            c.execute("SELECT * FROM autocars WHERE matricula = ?", (matricula_input,))
            autocar = c.fetchone()
            autocar_no_catalogat = autocar is None
            
            # Comprovar si hi ha un moviment obert
            c.execute("""
                SELECT id, hora_entrada FROM registres 
                WHERE matricula = ? AND estat = 'Esperant' 
                ORDER BY id DESC LIMIT 1
            """, (matricula_input,))
            open_reg = c.fetchone()
            
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if open_reg:
                # Registrar Sortida - usar els radio buttons permanents
                reg_id = open_reg[0]
                estacio = st.session_state.get("estacio_sortida")
                sentit = calcular_sentit(estacio) if estacio else None
                
                c.execute("""
                    UPDATE registres 
                    SET hora_sortida = ?, sentit = ?, estat = 'Circulant' 
                    WHERE id = ?
                """, (now_str, sentit, reg_id))
                conn.commit()
                st.success(f"✅ **SORTIDA REGISTRADA** per a l'autobús **{matricula_input}** a les {now_str}.")
                if sentit:
                    st.info(f"📍 Estació: **{estacio}** | 🔄 Sentit: **{sentit}**")
            else:
                # Registrar Entrada amb estació (sense sentit, es calcula a la sortida)
                estacio = st.session_state.get("estacio_sortida")
                
                c.execute("""
                    INSERT INTO registres (matricula, hora_entrada, estacio, estat) 
                    VALUES (?, ?, ?, 'Esperant')
                """, (matricula_input, now_str, estacio))
                conn.commit()
                st.success(f"🟢 **ENTRADA REGISTRADA** per a l'autobús **{matricula_input}** a les {now_str}.")
                if estacio:
                    st.info(f"📍 Estació: **{estacio}**")

            conn.close()

            if autocar_no_catalogat:
                st.session_state["matricula_pendent_alta"] = matricula_input
                st.warning(
                    f"La matrícula **{matricula_input}** no forma part de la flota. "
                    "La pots afegir ara amb el formulari ràpid."
                )
            else:
                # Si la matrícula ja està catalogada, netejar la variable
                st.session_state["matricula_pendent_alta"] = None

    # Mostrar formulari ràpid només si hi ha una matrícula pendent I aquesta no està catalogada
    matricula_pendent = st.session_state.get("matricula_pendent_alta")
    
    # Verificar que la matrícula pendent segueix no estant catalogada
    if matricula_pendent:
        conn_verify = get_db_connection()
        c_verify = conn_verify.cursor()
        c_verify.execute("SELECT * FROM autocars WHERE matricula = ?", (matricula_pendent,))
        ainda_no_catalogat = c_verify.fetchone() is None
        conn_verify.close()
        
        if ainda_no_catalogat:
            with st.container(border=True):
                st.subheader("Afegir l'autocar a la flota")
                st.caption(
                    f"Completa les dades de **{matricula_pendent}** o deixa l'alta per a més tard."
                )

                with st.form(f"alta_rapida_{matricula_pendent}", clear_on_submit=True):
                    st.number_input(
                        "Capacitat (places)",
                        min_value=1,
                        max_value=120,
                        value=55,
                        key=f"capacitat_rapida_{matricula_pendent}",
                    )
                    st.selectbox(
                        "Accés PMR",
                        ["Sí", "No"],
                        key=f"pmr_rapid_{matricula_pendent}",
                    )
                    st.selectbox(
                        "Aire condicionat",
                        ["Sí", "No"],
                        key=f"ac_rapid_{matricula_pendent}",
                    )
                    st.selectbox(
                        "Conductor",
                        ["H", "M"],
                        key=f"conductor_rapid_{matricula_pendent}",
                    )
                    st.form_submit_button(
                        "Afegir a la flota",
                        type="primary",
                        icon=":material/add:",
                        on_click=completar_alta_rapida,
                    )
                    st.form_submit_button(
                        "Ara no",
                        icon=":material/schedule:",
                        on_click=descartar_alta_rapida,
                    )
        else:
            # Si la matrícula ja s'ha catalogat, netejar
            st.session_state["matricula_pendent_alta"] = None

# -----------------------------------------------------------------------------
# 2. REGISTRE D'ENTRADES I SORTIDES
# -----------------------------------------------------------------------------
elif page == "📊 Registre Arribades / Sortides":
    st.header("📊 Registre Arribades i Sortides")
    # st.caption("Aquesta taula mostra els moviments combinats amb les característiques del vehicle.")

    conn = get_db_connection()
    query = """
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
            COALESCE(a.aire_acondicionat, '-') AS "Aire Acondicionat",
            COALESCE(a.conductor, '-') AS "Conductor"
        FROM registres r
        LEFT JOIN autocars a ON r.matricula = a.matricula
        ORDER BY r.id DESC
    """
    df_registres = read_dataframe(query, conn)
    conn.close()

    if not df_registres.empty:
        dins_count = len(df_registres[df_registres['Estat actual'] == 'Esperant'])
        total_count = len(df_registres)
        
        m1, m2 = st.columns(2)
        m1.metric("Vehicles actualment esperant", dins_count)
        m2.metric("Total de moviments enregistrats", total_count)
        
        st.dataframe(df_registres, width="stretch")
    else:
        st.info("Encara no hi ha cap accés registrat.")

# -----------------------------------------------------------------------------
# 3. KPI I ESTADÍSTIQUES
# -----------------------------------------------------------------------------
elif page == "📈 KPI i Estadístiques":
    st.header("📈 KPI i Estadístiques")
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # Obté la data actual
    from datetime import date
    today = date.today()
    today_start = f"{today} 00:00:00"
    today_end = f"{today} 23:59:59"
    
    # 1. Autocars registrats del dia
    c.execute("""
        SELECT COUNT(DISTINCT matricula) as count 
        FROM registres 
        WHERE DATE(hora_entrada) = ?
    """, (today,))
    autocars_del_dia = c.fetchone()[0] or 0
    
    # 2. Autocars en espera per estació
    c.execute("""
        SELECT estacio, COUNT(*) as count 
        FROM registres 
        WHERE estat = 'Esperant' 
        GROUP BY estacio
    """)
    espera_por_estacio = dict(c.fetchall())
    
    # 3. Autocars circulant per sentit
    c.execute("""
        SELECT sentit, COUNT(*) as count 
        FROM registres 
        WHERE estat = 'Circulant' 
        GROUP BY sentit
    """)
    circulant_por_sentit = dict(c.fetchall())
    
    # 4. Mitjana d'autocars per franja horaria
    c.execute("""
        SELECT 
            CAST(SUBSTR(hora_entrada, 12, 2) AS INTEGER) as hora,
            COUNT(*) as count
        FROM registres
        WHERE DATE(hora_entrada) = ?
        GROUP BY CAST(SUBSTR(hora_entrada, 12, 2) AS INTEGER)
        ORDER BY hora
    """, (today,))
    por_franja = c.fetchall()
    
    conn.close()
    
    # Mostrar KPIs
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("🚌 Autocars del dia", autocars_del_dia)
    
    with col2:
        en_espera = sum(espera_por_estacio.values())
        st.metric("⏳ En espera", en_espera)
    
    with col3:
        circulant = sum(circulant_por_sentit.values())
        st.metric("🔄 Circulant", circulant)
    
    with col4:
        if por_franja:
            mitjana = sum(h[1] for h in por_franja) / len(por_franja)
            st.metric("📊 Mitjana/hora", f"{mitjana:.1f}")
        else:
            st.metric("📊 Mitjana/hora", "0.0")
    
    st.divider()
    
    # Detalls per estació
    col_estacio, col_sentit = st.columns(2)
    
    with col_estacio:
        st.subheader("Autocars en espera per estació")
        if espera_por_estacio:
            for estacio, count in sorted(espera_por_estacio.items()):
                st.write(f"**{estacio}**: {count} 🚌")
        else:
            st.info("No hi ha autocars en espera")
    
    with col_sentit:
        st.subheader("Autocars circulant per sentit")
        if circulant_por_sentit:
            for sentit, count in sorted(circulant_por_sentit.items()):
                st.write(f"**{sentit}**: {count} 🚌")
        else:
            st.info("No hi ha autocars circulant")
    
    st.divider()
    st.subheader("Distribució per franja horaria")
    if por_franja:
        franja_df = pd.DataFrame(por_franja, columns=["Hora", "Autocars"])
        franja_df["Hora"] = franja_df["Hora"].apply(lambda x: f"{x:02d}:00-{x+1:02d}:00")
        st.bar_chart(franja_df.set_index("Hora"))
    else:
        st.info("No hi ha dades de franges horàries")

# -----------------------------------------------------------------------------
# 4. ALTA I GESTIÓ DE FLOTA (AUTOCARS)
# -----------------------------------------------------------------------------
elif page == "🚌 Alta Autocars":
    st.header("🚌 Alta Autocars")
    st.caption("Afegeix nous autocars a la base de dades amb totes les seves especificacions tècniques.")

    col_form, col_table = st.columns([1, 1.5])

    with col_form:
        st.subheader("Alta Nou Autocar")
        with st.form("form_alta_autocar", clear_on_submit=True):
            mat = st.text_input("Matrícula *", placeholder="Ex: 5678JKL").strip().upper()
            cap = st.number_input("Capacitat (places) *", min_value=1, max_value=120, value=55)
            pmr = st.selectbox("Accés PMR (Mobilitat Reduïda)", ["Sí", "No"])
            ac = st.selectbox("Aire Acondicionat", ["Sí", "No"])
            conductor = st.selectbox("Conductor", ["H", "M"])
            
            submitted = st.form_submit_button("➕ Guardar Autocar")
            
            if submitted:
                if not mat:
                    st.error("La matrícula és un camp obligatori.")
                else:
                    try:
                        afegir_autocar_a_flota(mat, cap, pmr, ac, conductor)
                        st.success(f"Autocar **{mat}** afegit correctament!")
                    except DATABASE_INTEGRITY_ERRORS:
                        st.error(f"La matrícula **{mat}** ja està registrada a la base de dades.")

    with col_table:
        st.subheader("Autocars registrats ")
        conn = get_db_connection()
        df_autocars = read_dataframe(
            'SELECT matricula AS "Matrícula", capacitat AS "Capacitat", '
            'acces_pmr AS "Accés PMR", aire_acondicionat AS "Aire Acondicionat", '
            'conductor AS "Conductor" FROM autocars',
            conn,
        )
        conn.close()
        
        st.dataframe(df_autocars, width="stretch")

# -----------------------------------------------------------------------------
# 4. EDICIÓ I MANTENIMENT DE TAULES
# -----------------------------------------------------------------------------
elif page == "✏️ Edició i Manteniment de Taules":
    st.header("✏️ Edició de Taules de Dades")
    st.caption("Modifica directament qualsevol dada de la taula d'autocars o ajusta registres d'arribada/sortida.")

    tab1, tab2 = st.tabs(["Edició Flota", "Edició Arribades/Sortides"])

    with tab1:
        st.subheader("Edició de la Taula d'Autocars")
        conn = get_db_connection()
        df_autocars_edit = read_dataframe("SELECT * FROM autocars", conn)
        conn.close()

        edited_autocars = st.data_editor(
            df_autocars_edit, 
            num_rows="dynamic", 
            key="editor_autocars",
            column_config={
                "matricula": st.column_config.TextColumn("Matrícula (Clau Única)", required=True),
                "capacitat": st.column_config.NumberColumn("Capacitat", min_value=1, max_value=150),
                "acces_pmr": st.column_config.SelectboxColumn("Accés PMR", options=["Sí", "No"]),
                "aire_acondicionat": st.column_config.SelectboxColumn("Aire Acondicionat", options=["Sí", "No"]),
                "conductor": st.column_config.TextColumn("Conductor")
            },
            width="stretch"
        )

        if st.button("💾 Desar Canvis a la Taula d'Autocars"):
            conn = get_db_connection()
            c = conn.cursor()
            try:
                c.execute("DELETE FROM autocars")
                for _, row in edited_autocars.iterrows():
                    if pd.notna(row['matricula']) and str(row['matricula']).strip():
                        capacitat = (
                            int(row['capacitat'])
                            if pd.notna(row['capacitat'])
                            else None
                        )
                        c.execute("""
                            INSERT INTO autocars (matricula, capacitat, acces_pmr, aire_acondicionat, conductor)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            str(row['matricula']).strip().upper(),
                            capacitat,
                            row['acces_pmr'] if pd.notna(row['acces_pmr']) else None,
                            row['aire_acondicionat'] if pd.notna(row['aire_acondicionat']) else None,
                            row['conductor'] if pd.notna(row['conductor']) else None,
                        ))
                conn.commit()
                st.success("S'han guardat tots els canvis a la taula d'Autocars!")
            except Exception as e:
                st.error(f"S'ha produït un error en desar els canvis: {e}")
            finally:
                conn.close()

    with tab2:
        st.subheader("Edició de la Taula de Registres d'Accés")
        conn = get_db_connection()
        df_registres_edit = read_dataframe("SELECT * FROM registres", conn)
        conn.close()

        edited_registres = st.data_editor(
            df_registres_edit,
            num_rows="dynamic",
            key="editor_registres",
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "matricula": st.column_config.TextColumn("Matrícula", required=True),
                "hora_entrada": st.column_config.TextColumn("Hora Entrada"),
                "hora_sortida": st.column_config.TextColumn("Hora Sortida"),
                "estacio": st.column_config.SelectboxColumn("Estació", options=["SR", "GR"]),
                "sentit": st.column_config.TextColumn("Sentit", disabled=True),
                "estat": st.column_config.SelectboxColumn("Estat", options=["Esperant", "Circulant"]),
            },
            width="stretch"
        )

        if st.button("💾 Desar Canvis als Registres"):
            conn = get_db_connection()
            c = conn.cursor()
            try:
                c.execute("DELETE FROM registres")
                for _, row in edited_registres.iterrows():
                    if pd.notna(row['matricula']) and str(row['matricula']).strip():
                        estacio = row['estacio'] if pd.notna(row['estacio']) else None
                        sentit = calcular_sentit(estacio) if estacio else None
                        values = (
                            str(row['matricula']).strip().upper(),
                            row['hora_entrada'] if pd.notna(row['hora_entrada']) else None,
                            row['hora_sortida'] if pd.notna(row['hora_sortida']) else None,
                            estacio,
                            sentit,
                            row['estat'] if pd.notna(row['estat']) else None,
                        )
                        if pd.notna(row['id']):
                            c.execute("""
                                INSERT INTO registres (
                                    id, matricula, hora_entrada, hora_sortida, estacio, sentit, estat
                                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (int(row['id']), *values))
                        else:
                            c.execute("""
                                INSERT INTO registres (
                                    matricula, hora_entrada, hora_sortida, estacio, sentit, estat
                                ) VALUES (?, ?, ?, ?, ?, ?)
                            """, values)
                sync_registres_sequence(conn)
                conn.commit()
                st.success("S'han guardat els canvis a la taula de registres!")
            except Exception as e:
                st.error(f"Error en desar els registres: {e}")
            finally:
                conn.close()

# -----------------------------------------------------------------------------
# 5. EXPORTACIÓ A EXCEL
# -----------------------------------------------------------------------------
elif page == "📥 Exportació de Dades (Excel)":
    # st.header("📥 Exportació de la Informació a Excel")
    st.caption("Descarrega tot l'historial de moviments o el llistat de la flota en un fitxer Excel formatat.")

    conn = get_db_connection()
    query_full = """
        SELECT 
            r.id AS "ID Registre",
            r.matricula AS "Matrícula",
            r.hora_entrada AS "Hora Entrada",
            COALESCE(r.hora_sortida, '') AS "Hora Sortida",
            COALESCE(r.estacio, '') AS "Estació",
            COALESCE(r.sentit, '') AS "Sentit",
            r.estat AS "Estat",
            COALESCE(CAST(a.capacitat AS TEXT), '') AS "Capacitat",
            COALESCE(a.acces_pmr, '') AS "Accés PMR",
            COALESCE(a.aire_acondicionat, '') AS "Aire Acondicionat",
            COALESCE(a.conductor, '') AS "Conductor"
        FROM registres r
        LEFT JOIN autocars a ON r.matricula = a.matricula
        ORDER BY r.id DESC
    """
    df_full = read_dataframe(query_full, conn)
    df_autocars = read_dataframe("SELECT * FROM autocars", conn)
    conn.close()

    st.subheader("Vista prèvia de les dades a exportar")
    st.dataframe(df_full.head(10), width="stretch")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_full.to_excel(writer, sheet_name='Historial i Accés', index=False)
        df_autocars.to_excel(writer, sheet_name='Flota Autocars', index=False)
    
    excel_data = output.getvalue()

    st.download_button(
        label="📥 Descarregar Informe complet en Excel (.xlsx)",
        data=excel_data,
        file_name=f"registre_autobusos_tall_obres_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
