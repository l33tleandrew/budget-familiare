#!/usr/bin/env python3
"""
budget_sheets.py — Interfaccia CLI per Budget Familiare Google Sheets

Comandi:
  read-taxonomy      Dump JSON della tassonomia locale (offline, nessuna rete)
  validate           Valida i campi di una transazione contro la tassonomia (offline)
  read-categories    Legge categorie/sottocategorie dal foglio Google (rete)
  append             Valida e scrive una transazione sul foglio (rete)

Esempi:
  python3 budget_sheets.py read-taxonomy
  python3 budget_sheets.py validate --data "01/09/2026" --tipo "Uscita" \
    --categoria "Salute" --sottocategoria "" --importo "12,50"
  python3 budget_sheets.py append --data "01/09/2026" --tipo "Uscita" \
    --categoria "Salute" --sottocategoria "Medicine" \
    --importo 12.50 --descrizione "Farmacia, antibiotico" --note ""

Exit code:
  0  ok
  1  errore di autenticazione
  2  errore di scrittura sul foglio
  3  validazione fallita (nessuna scrittura effettuata)
  4  tassonomia non trovata o illeggibile
"""
import json, os, sys, argparse, urllib.request, urllib.parse, time, re, difflib
from datetime import datetime, date, timedelta

PROFILE_DIR    = "/opt/data/profiles/budgetingagent"
TOKEN_FILE     = f"{PROFILE_DIR}/google_token.json"
CRED_FILE      = f"{PROFILE_DIR}/google_client_secret.json"
SPREADSHEET_ID = "1iDYzjzyu_du_axBmzOzI6k4DrzV2Y52_UZTFMtM6JB0"
SHEET_NAME     = "Transazioni 2026"

TIPI_VALIDI       = ("Entrata", "Uscita")
CARATTERI_VIETATI = ('"', "`", "$", "\\")
IMPORTO_SOGLIA_AVVISO = 2000.0

# ─────────────────────────────────────────────
# Tassonomia
# ─────────────────────────────────────────────

def _candidate_taxonomy_paths(explicit=None):
    here = os.path.dirname(os.path.abspath(__file__))
    paths = []
    if explicit:
        paths.append(explicit)
    if os.environ.get("BUDGET_TASSONOMIA"):
        paths.append(os.environ["BUDGET_TASSONOMIA"])
    paths += [
        os.path.join(here, "..", "references", "tassonomia.yaml"),
        os.path.join(here, "tassonomia.yaml"),
        f"{PROFILE_DIR}/references/tassonomia.yaml",
        f"{PROFILE_DIR}/tassonomia.yaml",
    ]
    return [os.path.normpath(p) for p in paths]


def _unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _parse_taxonomy_minimal(text):
    """Parser YAML minimale per il solo schema di tassonomia.yaml.

    Serve a non introdurre PyYAML come dipendenza: lo script gira anche in venv
    con sola stdlib. Se PyYAML c'e', viene usato quello (piu' permissivo).
    """
    categorie = []
    corrente  = None
    in_sub    = False
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line   = raw.strip()

        if line.startswith("- "):
            corpo = line[2:].strip()
            key, _, val = corpo.partition(":")
            if key.strip() != "nome":
                continue
            nome = _unquote(val)
            if in_sub and indent >= 4 and corrente is not None:
                corrente["sottocategorie"].append({"nome": nome})
            else:
                corrente = {"nome": nome, "tipo": "uscita", "sottocategorie": []}
                categorie.append(corrente)
                in_sub = False
            continue

        key, sep, val = line.partition(":")
        if not sep or corrente is None:
            continue
        key = key.strip()
        val = val.strip()
        if key == "tipo":
            corrente["tipo"] = _unquote(val).lower()
            in_sub = False
        elif key == "sottocategorie":
            corrente["sottocategorie"] = []
            in_sub = val == ""  # "[]" chiude la lista sulla stessa riga
    return {"categorie": categorie}


def load_taxonomy(explicit=None):
    """Carica la tassonomia. Solleva FileNotFoundError se nessun path esiste."""
    tried = _candidate_taxonomy_paths(explicit)
    for path in tried:
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        try:
            import yaml  # opzionale
            data = yaml.safe_load(text)
        except ImportError:
            data = _parse_taxonomy_minimal(text)
        categorie = []
        for c in (data or {}).get("categorie", []) or []:
            nome = (c.get("nome") or "").strip()
            if not nome:
                continue
            subs = []
            for s in c.get("sottocategorie") or []:
                sn = (s.get("nome") if isinstance(s, dict) else str(s)) or ""
                sn = sn.strip()
                if sn:
                    subs.append(sn)
            categorie.append({
                "nome": nome,
                "tipo": (c.get("tipo") or "uscita").strip().lower(),
                "sottocategorie": subs,
            })
        if not categorie:
            continue
        return {"path": path, "categorie": categorie}
    raise FileNotFoundError("; ".join(tried))


def _find_category(tax, nome):
    for c in tax["categorie"]:
        if c["nome"] == nome:
            return c
    return None


def _find_category_loose(tax, nome):
    """Match tollerante (case/spazi/typo) per proporre un suggerimento."""
    target = re.sub(r"\s+", " ", (nome or "")).strip().casefold()
    if not target:
        return None
    for c in tax["categorie"]:
        if re.sub(r"\s+", " ", c["nome"]).strip().casefold() == target:
            return c
    nomi = [c["nome"] for c in tax["categorie"]]
    vicini = difflib.get_close_matches(nome or "", nomi, n=1, cutoff=0.85)
    return _find_category(tax, vicini[0]) if vicini else None

# ─────────────────────────────────────────────
# Normalizzazione dei valori
# ─────────────────────────────────────────────

def normalize_importo(raw):
    """Restituisce (valore_normalizzato|None, nota|None).

    Applica le regole dei separatori italiani. None se non interpretabile.
    """
    if raw is None:
        return None, None
    s = str(raw).strip()
    s = re.sub(r"(?i)\s*(?:€|eur|euro)\s*", "", s)
    s = s.replace(" ", "").replace("\u00a0", "")
    negativo = s.startswith("-")
    s = s.lstrip("+-")
    if not s or not re.fullmatch(r"[\d.,]+", s):
        return None, None

    if "," in s and "." in s:
        dec_sep = "," if s.rfind(",") > s.rfind(".") else "."
        mig_sep = "." if dec_sep == "," else ","
        s = s.replace(mig_sep, "").replace(dec_sep, ".")
    elif "," in s:
        if s.count(",") > 1:
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif "." in s:
        parti = s.split(".")
        if s.count(".") > 1 or (len(parti) == 2 and len(parti[1]) == 3 and parti[0]):
            s = s.replace(".", "")  # separatore di migliaia

    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None, None
    valore = round(float(s), 2)
    nota = "segno rimosso: il verso lo porta --tipo" if negativo else None
    return f"{valore:.2f}", nota


def normalize_data(raw):
    """Restituisce (dd/mm/yyyy|None, valida_bool)."""
    if raw is None:
        return None, False
    s = str(raw).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%d/%m/%Y"), True
        except ValueError:
            continue
    return None, False

# ─────────────────────────────────────────────
# Validazione
# ─────────────────────────────────────────────

def _err(campo, codice, messaggio, richiede_utente=False, **extra):
    e = {
        "campo": campo,
        "codice": codice,
        "messaggio": messaggio,
        "richiede_utente": richiede_utente,
    }
    e.update(extra)
    return e


def validate_fields(tax, data=None, tipo=None, categoria=None, sottocategoria=None,
                    importo=None, descrizione=None, note=None):
    """Valida i campi di una transazione contro la tassonomia.

    Restituisce un dict serializzabile con: ok, valori, errori, avvisi.
    Ogni errore dichiara se e' risolvibile in autonomia (`suggerimento`) o se
    serve una scelta dell'utente (`richiede_utente`, con `opzioni`).
    """
    errori, avvisi = [], []
    tutte_le_categorie = [c["nome"] for c in tax["categorie"]]

    # ── data ──────────────────────────────────
    data_norm = None
    if data is None or str(data).strip() == "":
        errori.append(_err("data", "data_mancante",
            "Campo --data assente. Leggila dal sistema con `date +%d/%m/%Y`."))
    else:
        data_norm, valida = normalize_data(data)
        if not valida:
            errori.append(_err("data", "data_non_valida",
                f"'{data}' non e' una data valida nel formato gg/mm/aaaa."))
        elif data_norm != str(data).strip():
            errori.append(_err("data", "data_formato",
                "Formato non conforme: atteso gg/mm/aaaa.", suggerimento=data_norm))
        else:
            giorno = datetime.strptime(data_norm, "%d/%m/%Y").date()
            if giorno > date.today() + timedelta(days=1):
                avvisi.append({"campo": "data", "codice": "data_futura",
                               "messaggio": f"{data_norm} e' nel futuro: verifica con l'utente."})

    # ── importo ───────────────────────────────
    importo_norm = None
    if importo is None or str(importo).strip() == "":
        errori.append(_err("importo", "importo_mancante",
            "Campo --importo assente. Chiedilo all'utente: non dedurlo dal contesto.",
            richiede_utente=True))
    else:
        grezzo = str(importo).strip()
        importo_norm, nota = normalize_importo(grezzo)
        # Forma canonica accettata: cifre, punto decimale, max 2 decimali.
        canonico = bool(re.fullmatch(r"\d+(\.\d{1,2})?", grezzo))
        if importo_norm is None:
            errori.append(_err("importo", "importo_non_interpretabile",
                f"'{grezzo}' non e' un importo leggibile. Ammessi solo cifre e separatori.",
                richiede_utente=True))
        elif float(importo_norm) <= 0:
            errori.append(_err("importo", "importo_non_positivo",
                "L'importo deve essere maggiore di zero.", richiede_utente=True))
        elif not canonico:
            msg = f"Riscrivi l'importo come {importo_norm}: punto decimale, senza valuta."
            if nota:
                msg += f" ({nota})"
            errori.append(_err("importo", "importo_formato", msg, suggerimento=importo_norm))
        elif float(importo_norm) >= IMPORTO_SOGLIA_AVVISO:
            avvisi.append({"campo": "importo", "codice": "importo_elevato",
                           "messaggio": f"{importo_norm} e' un importo alto: conferma la cifra."})

    # ── categoria ─────────────────────────────
    cat = None
    if categoria is None or str(categoria).strip() == "":
        errori.append(_err("categoria", "categoria_mancante",
            "Campo --categoria assente. Mostra l'elenco numerato e chiedi all'utente.",
            richiede_utente=True, opzioni=tutte_le_categorie))
    else:
        cat = _find_category(tax, categoria)
        if cat is None:
            vicina = _find_category_loose(tax, categoria)
            if vicina is not None:
                errori.append(_err("categoria", "categoria_non_esatta",
                    f"'{categoria}' non combacia carattere per carattere con la tassonomia.",
                    suggerimento=vicina["nome"]))
                cat = vicina  # prosegui i controlli sulla candidata
            else:
                errori.append(_err("categoria", "categoria_inesistente",
                    f"'{categoria}' non esiste nella tassonomia. Mostra l'elenco e chiedi all'utente.",
                    richiede_utente=True, opzioni=tutte_le_categorie))

    # ── sottocategoria ────────────────────────
    if cat is not None:
        subs    = cat["sottocategorie"]
        sub_val = "" if sottocategoria is None else str(sottocategoria).strip()
        if subs and sub_val == "":
            errori.append(_err("sottocategoria", "sottocategoria_mancante",
                f"La categoria '{cat['nome']}' prevede sottocategorie: mostra l'elenco "
                "numerato e chiedi all'utente. Non lasciarla vuota.",
                richiede_utente=True, opzioni=subs))
        elif subs and sub_val not in subs:
            vicine = difflib.get_close_matches(sub_val, subs, n=1, cutoff=0.85)
            if vicine:
                errori.append(_err("sottocategoria", "sottocategoria_non_esatta",
                    f"'{sub_val}' non combacia con la tassonomia di '{cat['nome']}'.",
                    suggerimento=vicine[0]))
            else:
                errori.append(_err("sottocategoria", "sottocategoria_inesistente",
                    f"'{sub_val}' non e' una sottocategoria di '{cat['nome']}'.",
                    richiede_utente=True, opzioni=subs))
        elif not subs and sub_val != "":
            errori.append(_err("sottocategoria", "sottocategoria_non_prevista",
                f"La categoria '{cat['nome']}' non prevede sottocategorie: usa \"\".",
                suggerimento=""))
    elif sottocategoria not in (None, ""):
        errori.append(_err("sottocategoria", "sottocategoria_non_verificabile",
            "Sottocategoria non verificabile finche' la categoria non e' valida."))

    # ── tipo ──────────────────────────────────
    tipo_val    = None if tipo is None else str(tipo).strip()
    tipo_atteso = None
    if cat is not None and cat["tipo"] in ("entrata", "uscita"):
        tipo_atteso = cat["tipo"].capitalize()

    if not tipo_val:
        errori.append(_err("tipo", "tipo_mancante",
            "Campo --tipo assente. Deve valere Entrata o Uscita, coerente con la categoria.",
            **({"suggerimento": tipo_atteso} if tipo_atteso else {})))
    elif tipo_val not in TIPI_VALIDI:
        corretto = next((t for t in TIPI_VALIDI if t.casefold() == tipo_val.casefold()), None)
        errori.append(_err("tipo", "tipo_non_valido",
            f"'{tipo_val}' non e' valido: ammessi solo Entrata e Uscita.",
            **({"suggerimento": corretto} if corretto
               else {"richiede_utente": True, "opzioni": list(TIPI_VALIDI)})))
    elif cat is not None:
        if cat["tipo"] == "entrata" and tipo_val != "Entrata":
            errori.append(_err("tipo", "tipo_incoerente",
                f"La categoria '{cat['nome']}' e' di tipo entrata: --tipo deve essere Entrata. "
                "Se l'operazione e' un'uscita, e' la categoria a essere sbagliata.",
                suggerimento="Entrata"))
        elif cat["tipo"] == "uscita" and tipo_val != "Uscita":
            errori.append(_err("tipo", "tipo_incoerente",
                f"La categoria '{cat['nome']}' e' di tipo uscita: --tipo deve essere Uscita. "
                "Se l'operazione e' un'entrata, e' la categoria a essere sbagliata.",
                suggerimento="Uscita"))

    # ── descrizione / note ────────────────────
    for campo, valore in (("descrizione", descrizione), ("note", note)):
        testo   = "" if valore is None else str(valore)
        trovati = [c for c in CARATTERI_VIETATI if c in testo]
        if trovati:
            pulito = testo
            for c in CARATTERI_VIETATI:
                pulito = pulito.replace(c, "")
            pulito = re.sub(r"\s{2,}", " ", pulito).strip()
            errori.append(_err(campo, f"{campo}_caratteri_vietati",
                "Contiene caratteri che rompono il comando shell: " + " ".join(trovati),
                suggerimento=pulito))

    if note not in (None, ""):
        errori.append(_err("note", "note_non_vuota",
            "Il campo --note resta sempre vuoto.", suggerimento=""))

    valori = {
        "data":           data_norm or (str(data) if data is not None else ""),
        "tipo":           tipo_val or "",
        "categoria":      cat["nome"] if cat is not None else (categoria or ""),
        "sottocategoria": "" if sottocategoria is None else str(sottocategoria).strip(),
        "importo":        importo_norm or (str(importo) if importo is not None else ""),
        "descrizione":    "" if descrizione is None else str(descrizione),
        "note":           "" if note is None else str(note),
    }
    return {
        "ok":         not errori,
        "tassonomia": tax["path"],
        "valori":     valori,
        "errori":     errori,
        "avvisi":     avvisi,
    }

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

    expires_at = token_data.get("expires_at", 0)
    if token_data.get("access_token") and time.time() < expires_at - 60:
        return token_data["access_token"]

    resp = _do_refresh(token_data["refresh_token"], client_id, client_secret)

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
            token_data = _load_token()
            token_data.pop("expires_at", None)
            token_data.pop("access_token", None)
            _save_token(token_data)
            new_token = get_access_token()
            return _api_request(method, url, new_token, body=body, _retry=False)
        body_text = e.read()[:1000]
        raise RuntimeError(f"HTTP Error {e.code}: {body_text}")

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

def _emit(payload, exit_code=0):
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(exit_code)


def _add_transaction_args(p):
    """Campi transazione: mai `required`, li controlla il validatore.

    Cosi' un campo mancante torna come errore JSON dentro il loop, invece di
    far uscire argparse con un messaggio non parsabile.
    """
    p.add_argument("--data",           default=None, help="Data gg/mm/aaaa")
    p.add_argument("--tipo",           default=None, help="Entrata o Uscita")
    p.add_argument("--categoria",      default=None)
    p.add_argument("--sottocategoria", default=None)
    p.add_argument("--importo",        default=None, help="Positivo, punto decimale")
    p.add_argument("--descrizione",    default=None)
    p.add_argument("--note",           default=None)
    p.add_argument("--tassonomia",     default=None, help="Path di tassonomia.yaml")
    return p


_VALUE_FLAGS = ("--data", "--tipo", "--categoria", "--sottocategoria",
                "--importo", "--descrizione", "--note", "--tassonomia")


def _fix_negative_values(argv):
    """Unisce `--flag -40,30` in `--flag=-40,30`.

    argparse leggerebbe `-40,30` come un'opzione e uscirebbe con un usage su
    stderr: non parsabile dal loop. Meglio farlo arrivare al validatore, che
    lo segnala come segno da togliere.
    """
    out, i = [], 0
    while i < len(argv):
        tok = argv[i]
        if (tok in _VALUE_FLAGS and i + 1 < len(argv)
                and re.fullmatch(r"-[\d.,]+", argv[i + 1])):
            out.append(f"{tok}={argv[i + 1]}")
            i += 2
            continue
        out.append(tok)
        i += 1
    return out


def main():
    parser = argparse.ArgumentParser(description="Budget Familiare — CLI per Google Sheets")
    sub = parser.add_subparsers(dest="command")

    p_tax = sub.add_parser("read-taxonomy", help="Dump JSON della tassonomia locale")
    p_tax.add_argument("--tassonomia", default=None)

    _add_transaction_args(sub.add_parser("validate", help="Valida i campi (offline)"))
    _add_transaction_args(sub.add_parser("append",   help="Valida e scrive la transazione"))

    sub.add_parser("read-categories", help="Leggi categorie/sottocategorie dal foglio")

    args = parser.parse_args(_fix_negative_values(sys.argv[1:]))
    cmd  = args.command

    if cmd is None:
        parser.print_help()
        sys.exit(1)

    # ── comandi offline ───────────────────────
    esito = None
    if cmd in ("read-taxonomy", "validate", "append"):
        try:
            tax = load_taxonomy(getattr(args, "tassonomia", None))
        except FileNotFoundError as e:
            _emit({"ok": False, "comando": cmd, "errori": [_err(
                "tassonomia", "tassonomia_non_trovata",
                f"tassonomia.yaml non trovata. Path tentati: {e}. "
                "Passa --tassonomia con il path corretto.")]}, 4)

    if cmd == "read-taxonomy":
        _emit({"ok": True, "comando": cmd, "tassonomia": tax["path"],
               "categorie": tax["categorie"]})

    if cmd in ("validate", "append"):
        esito = validate_fields(
            tax,
            data=args.data, tipo=args.tipo, categoria=args.categoria,
            sottocategoria=args.sottocategoria, importo=args.importo,
            descrizione=args.descrizione, note=args.note,
        )
        esito["comando"] = cmd
        if cmd == "validate":
            _emit(esito, 0 if esito["ok"] else 3)
        if not esito["ok"]:
            esito["scritto"] = False
            _emit(esito, 3)

    # ── comandi con rete ──────────────────────
    try:
        token = get_access_token()
    except RuntimeError as e:
        _emit({"ok": False, "comando": cmd, "scritto": False,
               "errori": [_err("auth", "auth_fallita", str(e))]}, 1)
    except Exception as e:
        _emit({"ok": False, "comando": cmd, "scritto": False,
               "errori": [_err("auth", "auth_fallita", f"{type(e).__name__}: {e}")]}, 1)

    if cmd == "read-categories":
        cats = read_categories(token)
        print(json.dumps(cats, ensure_ascii=False, indent=2))
        sys.exit(0)

    if cmd == "append":
        v = esito["valori"]
        try:
            updated = append_row(
                token, v["data"], v["tipo"], v["categoria"],
                v["sottocategoria"], v["importo"], v["descrizione"], v["note"],
            )
        except RuntimeError as e:
            _emit({"ok": False, "comando": cmd, "scritto": False,
                   "errori": [_err("foglio", "scrittura_fallita", str(e))]}, 2)
        _emit({"ok": True, "comando": cmd, "scritto": True,
               "riga": updated, "valori": v, "avvisi": esito["avvisi"]})


if __name__ == "__main__":
    main()