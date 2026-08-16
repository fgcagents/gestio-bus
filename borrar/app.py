import streamlit as st
import streamlit.components.v1 as html_components
import pandas as pd
import sqlite3
from datetime import datetime
import easyocr
from PIL import Image
import io
import re
from borrar.ocr_utils import prepare_image_for_ocr

# Page config
st.set_page_config(page_title="Gestió de Flota i Accessos - Tall per Obres", layout="wide", page_icon="🚌")

# Initialize SQLite database
DB_FILE = "gestio_autobusos.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Table for Autocars (Master Data)
    c.execute("""
        CREATE TABLE IF NOT EXISTS autocars (
            matricula TEXT PRIMARY KEY,
            capacitat INTEGER,
            acces_pmr TEXT,
            aire_acondicionat TEXT,
            conductor TEXT
        )
    """)
    # Table for Access Logs (Movements)
    c.execute("""
        CREATE TABLE IF NOT EXISTS registres (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            matricula TEXT NOT NULL,
            hora_entrada TEXT NOT NULL,
            hora_sortida TEXT,
            estat TEXT NOT NULL,
            FOREIGN KEY (matricula) REFERENCES autocars (matricula)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# DB Helper functions
def get_db_connection():
    return sqlite3.connect(DB_FILE)

@st.cache_resource
def load_ocr():
    return easyocr.Reader(['es', 'en'])

reader = load_ocr()

# Helper function: Regex processing for Spanish license plates
def netejar_i_filtrar_matricula(text_raw):
    # 1. Convert to uppercase and strip non-alphanumeric characters
    text_net = re.sub(r'[^A-Z0-9]', '', text_raw.upper())
    
    # 2. Match standard Spanish plate: 4 digits + 3 consonants (ignoring vowels and 'E' country indicator)
    match_actual = re.search(r'\d{4}[B-DF-HJ-NP-TV-Z]{3}', text_net)
    if match_actual:
        return match_actual.group(0)
    
    # 3. Match old Spanish plate format: 1-2 province letters + 4 digits + 1-2 letters
    match_antic = re.search(r'[A-Z]{1,2}\d{4}[A-Z]{1,2}', text_net)
    if match_antic:
        return match_antic.group(0)
        
    # 4. Fallback if 'E' prefix was included in string length > 7
    if text_net.startswith('E') and len(text_net) > 7:
        text_sense_e = text_net[1:]
        match_sense_e = re.search(r'\d{4}[B-DF-HJ-NP-TV-Z]{3}', text_sense_e)
        if match_sense_e:
            return match_sense_e.group(0)

    return text_net

# Sidebar Navigation
st.sidebar.title("🚌 Gestió d'Autobusos")
st.sidebar.markdown("**Control d'Accessos - Tall per Obres**")
page = st.sidebar.radio("Navegació", [
    "📷 Control d'Accessos (Càmera / Manual)",
    "📊 Registre d'Entrades i Sortides",
    "🚌 Alta i Gestió de Flota (Autocars)",
    "✏️ Edició i Manteniment de Taules",
    "📥 Exportació de Dades (Excel)"
])

# -----------------------------------------------------------------------------
# 1. CONTROL D'ACCESSOS (Càmera HTML5 amb Zoom / Manual)
# -----------------------------------------------------------------------------
if page == "📷 Control d'Accessos (Càmera / Manual)":
    st.header("📷 Control d'Accessos de Vehicles")
    st.caption("Captura la matrícula mitjançant la càmera amb control de zoom o escriu-la manualment per registrar l'entrada o sortida.")

    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("1. Captura amb Càmera i Zoom")
        
        # Component únic de Càmera HTML5/JS amb Zoom
        camera_html = """
        <div style="text-align: center; font-family: sans-serif;">
            <video id="video" autoplay playsinline style="width: 100%; max-width: 380px; border: 2px solid #ccc; border-radius: 8px;"></video>
            <br><br>
            <label for="zoomRange"><b>Nivell de Zoom:</b> </label>
            <input type="range" id="zoomRange" min="1" max="5" step="0.1" value="2" style="width: 50%;">
            <span id="zoomValue">2.0x</span>
        </div>

        <script>
        const video = document.getElementById('video');
        const zoomRange = document.getElementById('zoomRange');
        const zoomValue = document.getElementById('zoomValue');
        let imageTrack = null;

        navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: { ideal: "environment" },
                zoom: true
            }
        }).then(stream => {
            video.srcObject = stream;
            imageTrack = stream.getVideoTracks()[0];
            const capabilities = imageTrack.getCapabilities();
            if (capabilities.zoom) {
                zoomRange.min = capabilities.zoom.min;
                zoomRange.max = capabilities.zoom.max;
                zoomRange.step = capabilities.zoom.step;
                zoomRange.value = Math.min(2.0, capabilities.zoom.max);
                applyZoom(zoomRange.value);
            } else {
                zoomRange.disabled = true;
                zoomValue.innerText = "Zoom no suportat per la lent";
            }
        }).catch(err => {
            navigator.mediaDevices.getUserMedia({ video: true }).then(stream => {
                video.srcObject = stream;
            });
        });

        zoomRange.oninput = (e) => { applyZoom(e.target.value); };

        function applyZoom(val) {
            zoomValue.innerText = parseFloat(val).toFixed(1) + 'x';
            if (imageTrack && imageTrack.applyConstraints) {
                imageTrack.applyConstraints({ advanced: [{ zoom: val }] });
            }
        }
        </script>
        """
        html_components.html(camera_html, height=280)

        # Captura directa per pujar la foto o utilitzar l'entrada manual
        uploaded_photo = st.file_uploader("O selecciona una imatge capturada:", type=["jpg", "jpeg", "png"])

        matricula_detectada = ""
        if uploaded_photo is not None:
            try:
                image = Image.open(uploaded_photo)
                image = image.convert("RGB")
                image_array = prepare_image_for_ocr(image)

                with st.spinner("Processant la imatge amb OCR i filtrat de matrícula..."):
                    results = reader.readtext(image_array, detail=0)
                    if results:
                        raw_candidate = "".join(results)
                        candidate = netejar_i_filtrar_matricula(raw_candidate)
                        st.success(f"Matrícula detectada i filtrada: **{candidate}**")
                        matricula_detectada = candidate
                    else:
                        st.warning("No s'ha detectat cap text clar. Utilitza l'entrada manual a sota.")
            except Exception as e:
                st.error(f"No s'ha pogut processar la imatge per OCR: {e}")


    with col2:
        st.subheader("2. Confirmació / Entrada Manual")
        val_inicial = matricula_detectada if matricula_detectada else ""
        matricula_input = st.text_input("Matrícula del vehicle:", value=val_inicial, placeholder="Ex: 1234BCD").strip().upper()
        
        if st.button("🔄 Registrar Accés (Entrada/Sortida)", type="primary"):
            if not matricula_input:
                st.error("Si us plau, introdueix una matrícula vàlida.")
            else:
                conn = get_db_connection()
                c = conn.cursor()
                
                c.execute("SELECT * FROM autocars WHERE matricula = ?", (matricula_input,))
                autocar = c.fetchone()
                
                if not autocar:
                    st.warning(f"⚠️ La matrícula **{matricula_input}** no està donada d'alta a la flota. Pots enregistrar l'accés, però recorda donar-la d'alta a la secció 'Alta i Gestió de Flota'.")
                
                c.execute("""
                    SELECT id, hora_entrada FROM registres 
                    WHERE matricula = ? AND estat = 'DINS' 
                    ORDER BY id DESC LIMIT 1
                """, (matricula_input,))
                open_reg = c.fetchone()
                
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                if open_reg:
                    reg_id = open_reg[0]
                    c.execute("""
                        UPDATE registres 
                        SET hora_sortida = ?, estat = 'FORA' 
                        WHERE id = ?
                    """, (now_str, reg_id))
                    conn.commit()
                    st.success(f"✅ **SORTIDA REGISTRADA** per a l'autobús **{matricula_input}** a les {now_str}.")
                else:
                    c.execute("""
                        INSERT INTO registres (matricula, hora_entrada, estat) 
                        VALUES (?, ?, 'DINS')
                    """, (matricula_input, now_str))
                    conn.commit()
                    st.success(f"🟢 **ENTRADA REGISTRADA** per a l'autobús **{matricula_input}** a les {now_str}.")
                
                conn.close()

# -----------------------------------------------------------------------------
# 2. REGISTRE D'ENTRADES I SORTIDES
# -----------------------------------------------------------------------------
elif page == "📊 Registre d'Entrades i Sortides":
    st.header("📊 Registre General d'Entrades i Sortides")
    st.caption("Aquesta taula mostra els moviments combinats amb les característiques del vehicle.")

    conn = get_db_connection()
    query = """
        SELECT 
            r.id AS 'ID Registre',
            r.matricula AS 'Matrícula',
            r.hora_entrada AS 'Arribada',
            COALESCE(r.hora_sortida, '-') AS 'Sortida',
            r.estat AS 'Estat actual',
            COALESCE(a.capacitat, 'No catalogat') AS 'Capacitat',
            COALESCE(a.acces_pmr, '-') AS 'Accés PMR',
            COALESCE(a.aire_acondicionat, '-') AS 'Aire Acondicionat',
            COALESCE(a.conductor, '-') AS 'Conductor'
        FROM registres r
        LEFT JOIN autocars a ON r.matricula = a.matricula
        ORDER BY r.id DESC
    """
    df_registres = pd.read_sql_query(query, conn)
    conn.close()

    if not df_registres.empty:
        dins_count = len(df_registres[df_registres['Estat actual'] == 'DINS'])
        total_count = len(df_registres)
        
        m1, m2 = st.columns(2)
        m1.metric("Vehicles actualment a DINS", dins_count)
        m2.metric("Total de moviments enregistrats", total_count)
        
        st.dataframe(df_registres, use_container_width=True)
    else:
        st.info("Encara no hi ha cap accés registrat.")

# -----------------------------------------------------------------------------
# 3. ALTA I GESTIÓ DE FLOTA
# -----------------------------------------------------------------------------
elif page == "🚌 Alta i Gestió de Flota (Autocars)":
    st.header("🚌 Alta i Gestió de la Flota d'Autocars")
    st.caption("Afegeix nous autocars a la base de dades amb totes les seves especificacions tècniques.")

    col_form, col_table = st.columns([1, 1.5])

    with col_form:
        st.subheader("Formulari d'Alta de Nou Autocar")
        with st.form("form_alta_autocar", clear_on_submit=True):
            mat = st.text_input("Matrícula *", placeholder="Ex: 5678JKL").strip().upper()
            cap = st.number_input("Capacitat (places) *", min_value=1, max_value=120, value=55)
            pmr = st.selectbox("Accés PMR (Mobilitat Reduïda)", ["Sí", "No"])
            ac = st.selectbox("Aire Acondicionat", ["Sí", "No"])
            conductor = st.text_input("Nom i Cognoms del Conductor", placeholder="Ex: Joan Garcia")
            
            submitted = st.form_submit_button("➕ Guardar Autocar")
            
            if submitted:
                if not mat:
                    st.error("La matrícula és un camp obligatori.")
                else:
                    conn = get_db_connection()
                    c = conn.cursor()
                    try:
                        c.execute("""
                            INSERT INTO autocars (matricula, capacitat, acces_pmr, aire_acondicionat, conductor)
                            VALUES (?, ?, ?, ?, ?)
                        """, (mat, cap, pmr, ac, conductor))
                        conn.commit()
                        st.success(f"Autocar **{mat}** afegit correctament!")
                    except sqlite3.IntegrityError:
                        st.error(f"La matrícula **{mat}** ja està registrada a la base de dades.")
                    finally:
                        conn.close()

    with col_table:
        st.subheader("Flota d'Autocars Catalogats")
        conn = get_db_connection()
        df_autocars = pd.read_sql_query("SELECT matricula AS 'Matrícula', capacitat AS 'Capacitat', acces_pmr AS 'Accés PMR', aire_acondicionat AS 'Aire Acondicionat', conductor AS 'Conductor' FROM autocars", conn)
        conn.close()
        
        st.dataframe(df_autocars, use_container_width=True)

# -----------------------------------------------------------------------------
# 4. EDICIÓ I MANTENIMENT DE TAULES
# -----------------------------------------------------------------------------
elif page == "✏️ Edició i Manteniment de Taules":
    st.header("✏️ Edició Directa de les Taules de Dades")
    st.caption("Modifica directament qualsevol dada de la taula d'autocars o ajusta registres d'arribada/sortida.")

    tab1, tab2 = st.tabs(["Edició Flota (Autocars)", "Edició Registres d'Accés"])

    with tab1:
        st.subheader("Edició de la Taula d'Autocars")
        conn = get_db_connection()
        df_autocars_edit = pd.read_sql_query("SELECT * FROM autocars", conn)
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
            use_container_width=True
        )

        if st.button("💾 Desar Canvis a la Taula d'Autocars"):
            conn = get_db_connection()
            c = conn.cursor()
            try:
                c.execute("DELETE FROM autocars")
                for _, row in edited_autocars.iterrows():
                    if row['matricula']:
                        c.execute("""
                            INSERT INTO autocars (matricula, capacitat, acces_pmr, aire_acondicionat, conductor)
                            VALUES (?, ?, ?, ?, ?)
                        """, (row['matricula'].upper(), row['capacitat'], row['acces_pmr'], row['aire_acondicionat'], row['conductor']))
                conn.commit()
                st.success("S'han guardat tots els canvis a la taula d'Autocars!")
            except Exception as e:
                st.error(f"S'ha produït un error en desar els canvis: {e}")
            finally:
                conn.close()

    with tab2:
        st.subheader("Edició de la Taula de Registres d'Accés")
        conn = get_db_connection()
        df_registres_edit = pd.read_sql_query("SELECT * FROM registres", conn)
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
                "estat": st.column_config.SelectboxColumn("Estat", options=["DINS", "FORA"])
            },
            use_container_width=True
        )

        if st.button("💾 Desar Canvis als Registres"):
            conn = get_db_connection()
            c = conn.cursor()
            try:
                c.execute("DELETE FROM registres")
                for _, row in edited_registres.iterrows():
                    if row['matricula']:
                        c.execute("""
                            INSERT INTO registres (id, matricula, hora_entrada, hora_sortida, estat)
                            VALUES (?, ?, ?, ?, ?)
                        """, (row['id'], row['matricula'].upper(), row['hora_entrada'], row['hora_sortida'], row['estat']))
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
    st.header("📥 Exportació de la Informació a Excel")
    st.caption("Descarrega tot l'historial de moviments o el llistat de la flota en un fitxer Excel formatat.")

    conn = get_db_connection()
    query_full = """
        SELECT 
            r.id AS 'ID Registre',
            r.matricula AS 'Matrícula',
            r.hora_entrada AS 'Hora Entrada',
            COALESCE(r.hora_sortida, '') AS 'Hora Sortida',
            r.estat AS 'Estat',
            COALESCE(a.capacitat, '') AS 'Capacitat',
            COALESCE(a.acces_pmr, '') AS 'Accés PMR',
            COALESCE(a.aire_acondicionat, '') AS 'Aire Acondicionat',
            COALESCE(a.conductor, '') AS 'Conductor'
        FROM registres r
        LEFT JOIN autocars a ON r.matricula = a.matricula
        ORDER BY r.id DESC
    """
    df_full = pd.read_sql_query(query_full, conn)
    df_autocars = pd.read_sql_query("SELECT * FROM autocars", conn)
    conn.close()

    st.subheader("Vista prèvia de les dades a exportar")
    st.dataframe(df_full.head(10), use_container_width=True)

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

