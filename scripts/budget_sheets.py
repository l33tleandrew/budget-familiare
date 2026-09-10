#!/usr/bin/env python3
"""
budget_sheets.py — Interfaccia CLI per Budget Familiare Google Sheets
Uso:
  python3 budget_sheets.py read-categories
  python3 budget_sheets.py append --data "01/09/2026" --tipo "Uscita" \
    --categoria "Supermercato" --sottocategoria "" \
    --importo 23.0 --descrizione "" --note ""
"""
import json, os, re, sys, argparse, urllib.request, urllib.parse, time
from datetime import datetime

PROFILE_DIR      = "/opt/data/profiles/budgetingagent"
TOKEN_FILE       = f"{PROFILE_DIR}/google_token.json"
CRED_FILE        = f"{PROFILE_DIR}/google_client_secret.json"
SPREADSHEET_ID   = "1iDYzjzyu_du_axBmzOzI6k4DrzV2Y52_UZTFMtM6JB0"
SHEET_NAME       = "Transazioni 2026"
TASSONOMIA_FILE  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "references", "tassonomia.yaml")

# ─────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────

def _load_creds():
    with open(CRED_FILE) as f:
        cred_data = json.load(f)
    client_info = list(cred_data.values())[0]
    return client_info["client_id"], client_info["client_secret"]

def _load_token():
    with open(TOKEN_FILE) as f:
        return json.load(f)

def _save_token(token_data):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

def _do_refresh(refresh_token, client_id, client_secret):
    """Scambia il refresh_token con un nuovo access_token.
    Lancia RuntimeError se il refresh_token e' revocato/scaduto.
    """
    data = urllib.parse.urlencode({
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data, method="POST"
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if "invalid_grant" in body:
            raise RuntimeError(
                "Il refresh_token e' scaduto o revocato da Google.\n"
                "Devi rigenerare il token OAuth eseguendo il flusso setup.py.\n"
                f"Dettaglio: {body}"
            )
        raise RuntimeError(f"Errore OAuth {e.code}: {body}")

def get_access_token():
    """Restituisce un access_token valido.
    - Se il token in cache e' ancora valido (con 60 s di margine), lo riusa.
    - Altrimenti fa refresh e aggiorna il file JSON.
    """
    token_data = _load_token()
    client_id, client_secret = _load_creds()

    # Controlla se il token in cache e' ancora buono
    expires_at = token_data.get("expires_at", 0)
    if token_data.get("access_token") and time.time() < expires_at - 60:
        return token_data["access_token"]

    # Fai refresh
    resp = _do_refresh(token_data["refresh_token"], client_id, client_secret)

    # Aggiorna il file preservando il refresh_token (Google a volte ne emette uno nuovo)
    token_data["access_token"] = resp["access_token"]
    token_data["expires_at"]   = time.time() + resp.get("expires_in", 3600)
    if "refresh_token" in resp:
        token_data["refresh_token"] = resp["refresh_token"]
    _save_token(token_data)

    return token_data["access_token"]

# ─────────────────────────────────────────────
# HTTP helper con auto-retry su 401
# ─────────────────────────────────────────────

def _api_request(method, url, access_token, body=None, _retry=True):
    """Esegue una chiamata HTTP alle API Google.
    Se riceve 401 (token scaduto lato server) fa un refresh e riprova una volta.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }
    data = json.dumps(body).encode() if body else None
    req  = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read()), access_token
    except urllib.error.HTTPError as e:
        if e.code == 401 and _retry:
            # Token rifiutato dal server: invalida la cache locale e riprova
            token_data = _load_token()
            token_data.pop("expires_at", None)
            token_data.pop("access_token", None)
            _save_token(token_data)
            new_token = get_access_token()
            return _api_request(method, url, new_token, body=body, _retry=False)
        body_text = e.read()[:1000]
        raise RuntimeError(f"HTTP Error {e.code}: {body_text}")

# ─────────────────────────────────────────────
# Validazione
# ─────────────────────────────────────────────

def validate_data(data):
    """Verifica che la stringa rispetti il formato gg/mm/aaaa (es. 01/09/2026)."""
    if not isinstance(data, str) or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", data):
        return False
    try:
        datetime.strptime(data, "%d/%m/%Y")
        return True
    except ValueError:
        return False


def validate_tipo(tipo):
    """Verifica che la stringa sia esattamente 'Entrata' o 'Uscita'."""
    return tipo in ("Entrata", "Uscita")


def validate_categoria(categoria):
    """Verifica che la stringa sia il nome esatto di una categoria in tassonomia.yaml."""
    with open(TASSONOMIA_FILE, encoding="utf-8") as f:
        contenuto = f.read()
    nomi_categorie = re.findall(r'^  - nome:\s*"(.*)"\s*$', contenuto, re.MULTILINE)
    return isinstance(categoria, str) and categoria in nomi_categorie

# ─────────────────────────────────────────────
# Operazioni sullo sheet
# ─────────────────────────────────────────────

def read_categories(access_token):
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
        f"/values/{urllib.parse.quote('Categorie!A:B')}"
    )
    result, _ = _api_request("GET", url, access_token)
    rows = result.get("values", [])
    categories = {}
    current_cat = None
    for row in rows[1:]:  # salta intestazione
        cat = row[0].strip() if len(row) > 0 else ""
        sub = row[1].strip() if len(row) > 1 else ""
        if cat:
            current_cat = cat
            if current_cat not in categories:
                categories[current_cat] = []
        if current_cat and sub and sub != "—":
            categories[current_cat].append(sub)
    return categories


def append_row(access_token, data, tipo, categoria, sottocategoria, importo, descrizione, note):
    row = [[data, tipo, categoria, sottocategoria, float(importo), descrizione, note]]
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}"
        f"/values/{urllib.parse.quote(SHEET_NAME)}!A:G:append"
        f"?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS"
    )
    result, _ = _api_request("POST", url, access_token, body={"values": row})
    return result.get("updates", {}).get("updatedRange", "?")

# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Budget Familiare — CLI per Google Sheets"
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("read-categories", help="Leggi categorie/sottocategorie dal foglio")

    p_append = subparsers.add_parser("append", help="Aggiungi una transazione")
    p_append.add_argument("--data",           required=True,  help="Data DD/MM/YYYY")
    p_append.add_argument("--tipo",           required=True,  help="Entrata o Uscita")
    p_append.add_argument("--categoria",      required=True)
    p_append.add_argument("--sottocategoria", default="")
    p_append.add_argument("--importo",        required=True,  help="Importo positivo (es. 23.50)")
    p_append.add_argument("--descrizione",    default="")
    p_append.add_argument("--note",           default="")

    args = parser.parse_args()

    try:
        token = get_access_token()
    except RuntimeError as e:
        print(f"ERRORE autenticazione:\n{e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERRORE autenticazione: {e}", file=sys.stderr)
        sys.exit(1)

    if args.command == "read-categories":
        cats = read_categories(token)
        print(json.dumps(cats, ensure_ascii=False, indent=2))

    elif args.command == "append":
        try:
            updated = append_row(
                token,
                args.data, args.tipo, args.categoria,
                args.sottocategoria, args.importo, args.descrizione, args.note
            )
            print(f"OK:{updated}")
        except RuntimeError as e:
            print(f"ERRORE scrittura: {e}", file=sys.stderr)
            sys.exit(2)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
