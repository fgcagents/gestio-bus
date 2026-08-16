# Gestió de Flota i Accessos

Aplicació Streamlit per gestionar la flota d'autocars i registrar entrades i sortides durant un tall per obres.

## Funcionalitats

- Lectura de matrícules amb càmera i OCR.
- Registre automàtic d'entrades i sortides.
- Alta i manteniment de la flota.
- Edició de les taules de dades.
- Exportació de l'historial a Excel.

## Execució local

Requereix Python 3.11.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Desplegament a Streamlit Community Cloud

1. Selecciona aquest repositori a Streamlit Community Cloud.
2. Indica `app.py` com a fitxer principal.
3. Utilitza Python 3.11 a la configuració avançada.
4. No cal configurar cap secret per a la versió actual.

## Persistència de dades

La versió actual utilitza SQLite (`gestio_autobusos.db`). En un desplegament a Streamlit Community Cloud, el disc local no és persistent: la base de dades pot desaparèixer quan l'aplicació es reinicia, canvia de màquina o es torna a desplegar.

Per a un ús real amb dades que s'han de conservar, cal substituir SQLite per una base de dades externa persistent (per exemple, PostgreSQL o Supabase).

## Primer inici

La primera càrrega pot trigar perquè EasyOCR ha de carregar el model de reconeixement.
