# Persistència a Streamlit Community Cloud

L'aplicació utilitza PostgreSQL quan troba el secret `DATABASE_URL`. Si no el
troba, continua utilitzant `gestio_autobusos.db` només per al treball local.

## 1. Configurar PostgreSQL

Crea una base PostgreSQL gestionada i copia'n la URL de connexió completa. Ha de
tenir un format semblant a aquest:

```toml
DATABASE_URL = "postgresql://USUARI:CONTRASENYA@HOST:5432/BASE_DE_DADES?sslmode=require"
```

No publiquis mai la URL al repositori.

## 2. Migrar les dades locals

1. Copia `.streamlit/secrets.toml.example` com a `.streamlit/secrets.toml`.
2. Substitueix la URL d'exemple per la URL real.
3. Executa una sola vegada:

```powershell
python migrate_sqlite_to_postgres.py
```

La migració només s'executa si PostgreSQL és buit. Així evita duplicar o
sobreescriure dades existents.

## 3. Configurar Streamlit Cloud

A la configuració de l'app, obre **Advanced settings → Secrets** i enganxa-hi:

```toml
DTABASE_URL = A"LA_URL_REAL_DE_POSTGRESQL"
```

Quan la connexió sigui correcta, la barra lateral mostrarà
`Base de dades: PostgreSQL persistent`.
