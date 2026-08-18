"""Aplicació Streamlit de gestió d'autocars i moviments."""

import streamlit as st

from database import database_status, init_db, vehicles_esperant


st.set_page_config(
    page_title="Gestió d'autobusos",
    page_icon=":material/directions_bus:",
    layout="wide",
)

from ui_operativa import _ultims_moviments, render_operativa  # noqa: E402
from ui_pages import (  # noqa: E402
    render_flota,
    render_indicadors,
    render_manteniment,
    render_registres,
)


@st.cache_resource
def ensure_db_initialized():
    init_db()
    return True


def _refrescar_dades():
    """Invalida només les consultes visibles abans del rerun del botó."""
    vehicles_esperant.clear()
    _ultims_moviments.clear()


try:
    ensure_db_initialized()
except Exception:
    st.error(
        "No s'ha pogut connectar amb la base de dades. "
        "Revisa el secret DATABASE_URL de Streamlit Cloud.",
        icon=":material/database_off:",
    )
    st.stop()


with st.sidebar:
    st.subheader("Dades de treball")
    etiqueta_bd, persistent = database_status()
    st.badge(
        etiqueta_bd,
        icon=":material/database:",
        color="green" if persistent else "orange",
    )
    st.metric("Vehicles esperant", vehicles_esperant())
    st.button(
        "Actualitzar dades",
        icon=":material/refresh:",
        width="stretch",
        help="Torna a llegir l'estat actual de la base de dades.",
        on_click=_refrescar_dades,
    )
    st.caption("Els canvis només es desen quan confirmes l'operació.")


pagina = st.navigation(
    [
        st.Page(
            render_operativa,
            title="Operativa",
            icon=":material/swap_vert:",
            default=True,
        ),
        st.Page(
            render_registres,
            title="Registres",
            icon=":material/table_view:",
        ),
        st.Page(
            render_indicadors,
            title="Indicadors",
            icon=":material/monitoring:",
        ),
        st.Page(
            render_flota,
            title="Flota",
            icon=":material/directions_bus:",
        ),
        st.Page(
            render_manteniment,
            title="Manteniment",
            icon=":material/build:",
        ),
    ],
    position="top",
)
pagina.run()
