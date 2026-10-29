#!/usr/bin/env python3
"""
budget_sheets.py — Interfaccia CLI per Budget Familiare Google Sheets

Lo script conduce il dialogo e ne conserva lo stato in una bozza su disco: chi
lo chiama non deve ricordare niente fra un turno e l'altro.

  # primo turno di una transazione nuova
  python3 budget_sheets.py append --nuova --importo 30.00 \
      --categoria "Cibo fuori / bevute" --descrizione "Trattoria da Nino"

  # ogni turno successivo: solo quello che ha risposto l'utente
  python3 budget_sheets.py append --risposta "5"
  python3 budget_sheets.py append --risposta "si"

Ogni invocazione stampa su stdout un solo JSON con le stesse chiavi. Le due che
contano sono "messaggio" (il testo completo da mostrare all'utente, elenco
numerato e riepilogo inclusi: non c'e' niente da comporre) e "stato". Si continua
a chiamare finche' "stato" inizia per "chiedi_".

Exit code:
  0   scritto            riga sul foglio, bozza cancellata
  3   in dialogo         (chiedi_*) oppure stato terminale benigno
                         (annullata, bozza_scaduta, bozza_assente,
                          scrittura_in_corso)
  1   errore_auth        bozza conservata
  2   errore_scrittura   bozza conservata
  5   errore_tassonomia  tipo non ricavabile: niente e' stato scritto
  6   errore_bozza       non si riesce a salvare lo stato del dialogo
  7   errore_anno        anno civile diverso da ANNO_BUDGET: niente scritto
  8   errore_configurazione
                         manca GOOGLE_SPREADSHEET_ID o ANNO_BUDGET: niente scritto
  64  errore d'uso       argomenti sbagliati o sottocomando mancante
"""
import json, os, re, sys, argparse, urllib.request, urllib.parse, time
import contextlib, fcntl, tempfile, unicodedata
from datetime import datetime, timedelta

# Il profilo Hermes dell'istanza e' la cartella in cui il plugin e' installato:
# Hermes lo mette in <profilo>/plugins/<nome>/, ed e' li' che stanno credenziali,
# token, .env e bozza. Niente in questo file nomina un'istanza: tutto quello che
# cambia da una famiglia all'altra si legge dal profilo.
#
# abspath e non realpath: un plugin collegato con un symlink appartiene al
# profilo in cui sta il link, non a quello in cui sta il checkout.
PLUGIN_DIR        = os.path.dirname(os.path.abspath(__file__))


def _profilo():
    """La cartella del profilo su cui il plugin e' installato.

    Non si legge HERMES_HOME: dipende da come e' stato avviato il processo, e nel
    container vale /opt/data anche quando il plugin sta in un profilo. La
    posizione del plugin invece non sbaglia.

    BUDGET_PROFILE_DIR la impone, ed e' per i test: sul server la suite gira
    dentro il profilo vero, e non deve vederlo. Un checkout che non sta sotto
    `plugins/` non e' installato in nessun profilo, e vale il default di Hermes.
    """
    imposto = os.environ.get("BUDGET_PROFILE_DIR")
    if imposto:
        return imposto
    plugins = os.path.dirname(PLUGIN_DIR)
    if os.path.basename(plugins) == "plugins":
        return os.path.dirname(plugins)
    return os.path.expanduser("~/.hermes")


PROFILE_DIR       = _profilo()
TOKEN_FILE        = f"{PROFILE_DIR}/google_token.json"
CRED_FILE         = f"{PROFILE_DIR}/google_client_secret.json"
TASSONOMIA_FILE   = os.path.join(PLUGIN_DIR, "tassonomia.yaml")


def _env_del_profilo():
    """Le variabili del .env del profilo su cui il plugin e' installato.

    E' li' che `hermes plugins install` salva le risposte a `requires_env`.
    Hermes lo carica nell'ambiente solo se il processo e' avviato su quel
    profilo: da una shell, o con HERMES_HOME su un'altra cartella, senza questo
    lo script si fermerebbe su una configurazione che esiste, e cosi'
    setup_google.py.

    Il parser e' il minimo: CHIAVE=valore, commenti, `export`, apici. Un file
    assente o illeggibile vale come vuoto.
    """
    valori = {}
    try:
        with open(os.path.join(PROFILE_DIR, ".env"), encoding="utf-8") as f:
            righe = f.readlines()
    except OSError:
        return valori
    for riga in righe:
        riga = riga.strip()
        if not riga or riga.startswith("#") or "=" not in riga:
            continue
        chiave, _, valore = riga.removeprefix("export ").partition("=")
        valore = valore.strip()
        if len(valore) >= 2 and valore[0] == valore[-1] and valore[0] in "'\"":
            valore = valore[1:-1]
        valori[chiave.strip()] = valore
    return valori


_ENV_PROFILO = _env_del_profilo()


def _config(nome):
    """L'ambiente prima, il .env del profilo poi; "" se non c'e' in nessuno dei due.

    La stringa vuota vale come "non impostato" in entrambi: `ANNO_BUDGET=` nel
    .env non deve vincere su niente.
    """
    return (os.environ.get(nome) or _ENV_PROFILO.get(nome) or "").strip()


def _anno(valore):
    """L'anno se `valore` e' di quattro cifre, altrimenti None.

    Un valore storto non fa fallire l'import, ed e' deliberato: un import
    fallito lascia Hermes senza il tool, e a "benzina 50" risponderebbe il
    modello per conto suo. Un anno mancante lo ferma configurazione_mancante(),
    all'inizio del turno, con un messaggio dello script.
    """
    return int(valore) if re.fullmatch(r"\d{4}", valore) else None


# Le impostazioni per-istanza. Ognuna si legge dalla variabile che porta il suo
# stesso nome: e' quello che permette a configurazione_mancante() di trovarle
# per nome, e a plugin.yaml di dichiararle in `requires_env`.
GOOGLE_SPREADSHEET_ID = _config("GOOGLE_SPREADSHEET_ID")
ANNO_BUDGET           = _anno(_config("ANNO_BUDGET"))
GOOGLE_SHEET_NAME     = _config("GOOGLE_SHEET_NAME") or f"Transazioni {ANNO_BUDGET}"
CONFIGURAZIONE        = ("GOOGLE_SPREADSHEET_ID", "ANNO_BUDGET")


def _bozza_predefinita():
    """La bozza sta in PROFILE_DIR, FUORI dal worktree git.

    sync_budget_skill.sh fa `git add -A` dentro la directory del plugin: un
    percorso fuori dal worktree e' irraggiungibile, non solo ignorato. E' una
    garanzia piu' forte di una riga in .gitignore, che un `git add -f` o un
    merge sbagliato vanificherebbero — e qui dentro c'e' lo storico di spesa
    della famiglia.

    C'e' una seconda ragione, arrivata col plugin: Hermes *sostituisce* la
    directory del plugin a ogni update. Lo stato di un dialogo a meta' scritto
    li' dentro sparirebbe insieme alla vecchia versione.
    """
    if os.path.isdir(PROFILE_DIR):
        return os.path.join(PROFILE_DIR, "bozza_transazione.json")
    return os.path.join(tempfile.gettempdir(), "budget_bozza_transazione.json")


BOZZA_FILE     = os.environ.get("BUDGET_BOZZA_FILE") or _bozza_predefinita()
try:
    BOZZA_TTL = int(os.environ.get("BUDGET_BOZZA_TTL_MIN", "15")) * 60
except ValueError:
    BOZZA_TTL = 15 * 60  # un env var storto non deve far esplodere l'import
BOZZA_VERSIONE = 1

CAMPI = ("data", "importo", "categoria", "sottocategoria", "descrizione", "note", "conferma")

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
                "Il consenso va rifatto: `python3 setup_google.py url`, poi `codice --force`.\n"
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
# Tassonomia
# ─────────────────────────────────────────────

_TASSONOMIA_CACHE = None


def leggi_tassonomia():
    """Legge tassonomia.yaml una volta sola e la tiene in cache.

    Niente PyYAML: sul server la skill gira con un interprete dove non si
    possono installare pacchetti, quindi si parsano le righe grezze. Di
    conseguenza l'indentazione del file e' significativa: 2 spazi per la
    categoria, 4 per i suoi attributi, 6 per la sottocategoria, 8 per i suoi.

    [{"id": 3, "nome": "Cibo fuori / bevute", "tipo": "uscita",
      "sottocategorie": [{"id": 1, "nome": "Asporto", "tipo": None}, ...]}, ...]
    """
    global _TASSONOMIA_CACHE
    if _TASSONOMIA_CACHE is not None:
        return _TASSONOMIA_CACHE

    with open(TASSONOMIA_FILE, encoding="utf-8") as f:
        righe = f.readlines()

    categorie = []
    for riga in righe:
        m = re.match(r'^  - nome:\s*"(.*)"\s*$', riga)
        if m:
            categorie.append({"nome": m.group(1), "id": None, "tipo": "uscita",
                              "sottocategorie": []})
            continue
        if not categorie:
            continue
        cat = categorie[-1]

        m = re.match(r'^      - nome:\s*"(.*)"\s*$', riga)
        if m:
            cat["sottocategorie"].append({"nome": m.group(1), "id": None, "tipo": None})
            continue

        # Gli attributi a 8 spazi appartengono all'ultima sottocategoria vista,
        # quelli a 4 alla categoria. L'ordine dei controlli conta: la regex a 4
        # spazi non deve catturare una riga indentata di 8.
        m = re.match(r'^        id:\s*(\d+)\s*$', riga)
        if m and cat["sottocategorie"]:
            cat["sottocategorie"][-1]["id"] = int(m.group(1))
            continue
        m = re.match(r'^        tipo:\s*(\w+)\s*$', riga)
        if m and cat["sottocategorie"]:
            cat["sottocategorie"][-1]["tipo"] = m.group(1)
            continue
        m = re.match(r'^    id:\s*(\d+)\s*$', riga)
        if m:
            cat["id"] = int(m.group(1))
            continue
        m = re.match(r'^    tipo:\s*(\w+)\s*$', riga)
        if m:
            cat["tipo"] = m.group(1)

    _TASSONOMIA_CACHE = categorie
    return categorie


def _piatto(s):
    """Minuscolo e senza accenti, per confrontare quello che scrive l'utente.

    "Sì", "SI", "si " diventano tutti "si"; "Cura / Benessere" diventa
    "cura / benessere". Serve sia per la conferma sia per i nomi di categoria.
    """
    s = unicodedata.normalize("NFD", str(s).strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def trova_categoria(valore):
    """Categoria per id numerico o per nome (tollerante su accenti e maiuscole)."""
    if valore is None:
        return None
    valore = str(valore).strip()
    if not valore:
        return None
    categorie = leggi_tassonomia()
    if re.fullmatch(r"\d+", valore):
        return next((c for c in categorie if c["id"] == int(valore)), None)
    piatto = _piatto(valore)
    return next((c for c in categorie if _piatto(c["nome"]) == piatto), None)


def trova_sottocategoria(categoria, valore):
    """Sottocategoria dentro una categoria, per id o per nome. L'id e' relativo
    alla categoria: il "5" di Cibo fuori non e' il "5" di Auto / Moto."""
    if categoria is None or valore is None:
        return None
    valore = str(valore).strip()
    if not valore:
        return None
    sotto = categoria["sottocategorie"]
    if re.fullmatch(r"\d+", valore):
        return next((s for s in sotto if s["id"] == int(valore)), None)
    piatto = _piatto(valore)
    return next((s for s in sotto if _piatto(s["nome"]) == piatto), None)


def tipo_di(categoria, sottocategoria=None):
    """'Entrata' | 'Uscita' | None.

    None significa tassonomia incoerente (tipo 'entrambi' senza un tipo sulla
    sottocategoria): non e' un valore da scrivere sul foglio, e' un errore di
    configurazione. Prima questa funzione restituiva False, che finiva in
    colonna B come la stringa "False".
    """
    if categoria is None:
        return None
    if sottocategoria and sottocategoria.get("tipo") in ("entrata", "uscita"):
        return sottocategoria["tipo"].capitalize()
    if categoria["tipo"] in ("entrata", "uscita"):
        return categoria["tipo"].capitalize()
    return None


# Wrapper sottili sulla tassonomia: l'interfaccia storica, usata dai test.

def get_taxonomy_map():
    """{categoria: [sottocategorie]}, nell'ordine del file."""
    return {c["nome"]: [s["nome"] for s in c["sottocategorie"]] for c in leggi_tassonomia()}


def find_categoria_by_id(categoria_id):
    cat = next((c for c in leggi_tassonomia() if c["id"] == int(categoria_id)), None)
    return cat["nome"] if cat else False


def find_sottocategoria_by_id(categoria, sottocategoria_id):
    cat = next((c for c in leggi_tassonomia() if c["nome"] == categoria), None)
    sotto = trova_sottocategoria(cat, str(sottocategoria_id)) if cat else None
    return sotto["nome"] if sotto else False


def validate_categoria(categoria):
    cat = trova_categoria(categoria)
    return cat["nome"] if cat else False


def validate_sottocategoria(categoria, sottocategoria):
    """Nome canonico, "" se la categoria non ne prevede, False se non si risolve.

    Una categoria senza sottocategorie restituisce "" qualunque cosa le si
    passi: e' un fatto della tassonomia, non qualcosa che chi chiama debba
    dichiarare. Cosi' lo script non puo' piu' chiedere una sottocategoria che
    non esiste — la domanda senza risposta che mandava il dialogo in loop.
    """
    cat = trova_categoria(categoria)
    if cat is None:
        return False
    if not cat["sottocategorie"]:
        return ""
    sotto = trova_sottocategoria(cat, sottocategoria)
    return sotto["nome"] if sotto else False


def get_tipo(categoria, sottocategoria=""):
    cat = trova_categoria(categoria)
    sotto = trova_sottocategoria(cat, sottocategoria) if sottocategoria else None
    tipo = tipo_di(cat, sotto)
    return tipo if tipo is not None else False

# ─────────────────────────────────────────────
# Validazione
# ─────────────────────────────────────────────

def validate_data(data):
    """Verifica che la stringa rispetti il formato gg/mm/aaaa.

    Solo il formato: l'anno del budget non lo guarda, ed e' deliberato. Qui
    "31/12/1999" e' e resta valido; la regola secondo cui il foglio ne tiene uno
    solo sta in _nell_anno(), che e' una regola e non una sintassi.
    """
    if not isinstance(data, str) or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", data):
        return False
    try:
        datetime.strptime(data, "%d/%m/%Y")
        return True
    except ValueError:
        return False


def _nell_anno(data):
    """True se la data gg/mm/aaaa e' dentro l'anno del budget.

    Sta qui e non in validate_data di proposito: quella verifica il formato, e
    il formato di "10/09/2025" e' ineccepibile. Questa e' la regola secondo cui
    il foglio tiene un anno solo.

    Non va confusa con anno_disallineato() qui sotto: le guardie d'anno sono
    due e guardano cose diverse. Quella presidia la *configurazione* e ferma il
    turno prima che cominci; questa presidia *una data* e vive dentro
    normalizza(), accanto agli altri campi.

    `endswith` e non uno strptime: la stringa arriva gia' validata, quindi e'
    gg/mm/aaaa e il suffisso e' l'anno. Rileggere con un parser quello che e'
    appena stato verificato aggiunge un modo di fallire, non sicurezza.
    """
    return data.endswith(f"/{ANNO_BUDGET}")


def anno_disallineato():
    """True se l'anno civile e quello configurato non combaciano.

    L'orologio si accorge del cambio d'anno, la costante e' la presa d'atto:
    finche' le due non combaciano non si scrive niente, perche' la scheda
    dell'anno nuovo potrebbe non esistere e le date senza anno finirebbero
    tutte in quello vecchio.

    E' `!=` e non `>` di proposito: chi porta avanti ANNO_BUDGET in anticipo —
    scheda del 2027 creata a dicembre — con `>` vedrebbe le spese di dicembre
    finire in silenzio sulla scheda dell'anno dopo. Bloccarsi e' rumoroso e si
    annulla riportando indietro la costante; una riga sul foglio sbagliato no.

    Niente `oggi` iniettabile, al contrario di normalizza_data_relativa(): li'
    l'orologio e' l'unico ingresso, qui i lati del confronto sono due e la
    costante si patcha. Un parametro che la produzione non passa mai sarebbe solo
    un modo per far dire due anni diversi a questa funzione e al messaggio, che
    legge now() per conto suo. I test che provano il confine di mezzanotte
    spostano l'orologio.
    """
    return datetime.now().year != ANNO_BUDGET


def configurazione_mancante():
    """I nomi delle impostazioni obbligatorie che mancano o non valgono.

    E' la guardia che viene prima di anno_disallineato(): senza foglio non c'e'
    dove scrivere, e senza anno quella non ha uno dei due lati del confronto —
    direbbe "impostato sul None". Si cercano per nome perche' ogni costante si
    chiama come la variabile da cui si legge (vedi CONFIGURAZIONE).
    """
    return [nome for nome in CONFIGURAZIONE if not globals()[nome]]


_GIORNI =("lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica")

_GIORNI_FA = {"oggi": 0, "ieri": 1, "altro ieri": 2, "avantieri": 2, "avant ieri": 2}


def normalizza_data_relativa(testo, oggi=None):
    """"ieri", "lunedi scorso" e simili diventano gg/mm/aaaa. Il resto passa intatto.

    Questa regola stava nel prompt, sotto forma di `date -d yesterday` fatto
    shellare al modello: una regola in piu' che puo' saltare, e che saltando non
    fa rumore. Qui c'e' un posto solo e un test accanto.

    `oggi` e' iniettabile perche' un test che dipende dall'orologio fallisce a
    mezzanotte e nessuno capisce perche'. Non si guarda avanti: una spesa la si
    registra dopo averla fatta, e "domani" in un messaggio di spesa e' quasi
    sempre un errore di battitura, non una data.
    """
    if not isinstance(testo, str):
        return testo
    oggi = oggi or datetime.now()

    piatto = _piatto(testo).replace("'", " ")
    piatto = re.sub(r"^(l|lo|il|la) ", "", re.sub(r"\s+", " ", piatto).strip())

    if piatto in _GIORNI_FA:
        return (oggi - timedelta(days=_GIORNI_FA[piatto])).strftime("%d/%m/%Y")

    giorni = "|".join(_GIORNI)
    m = re.fullmatch(rf"(?:scorso |ultimo )?({giorni})(?: (?:scorso|passato))?", piatto)
    if m:
        # "lunedi scorso" detto di lunedi e' quello di sette giorni fa, non oggi.
        indietro = (oggi.weekday() - _GIORNI.index(m.group(1))) % 7 or 7
        return (oggi - timedelta(days=indietro)).strftime("%d/%m/%Y")

    return testo


def validate_tipo(tipo):
    """Verifica che la stringa sia esattamente 'Entrata' o 'Uscita'."""
    return tipo in ("Entrata", "Uscita")


def validate_importo(importo):
    """Verifica che l'importo sia un numero positivo, senza simboli di valuta.
    Riconosce il formato inglese (punto decimale), quello italiano (virgola
    decimale, punto delle migliaia facoltativo) e un intero senza virgola né
    punto (es. 1200 => 1200.00), e lo restituisce sempre come float in formato
    inglese. Il segno lo porta il tipo, non il numero: valori negativi non
    sono validi. Restituisce False se l'importo non è un numero valido."""
    if isinstance(importo, (int, float)) and not isinstance(importo, bool):
        return float(importo) if importo > 0 else False
    if not isinstance(importo, str):
        return False
    s = importo.strip()

    if re.fullmatch(r"\d{1,3}(\.\d{3})*,\d+", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+,\d+", s):
        s = s.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        # 1.500 → 1500, 1.200.000 → 1200000. Senza questo ramo cadrebbe nel
        # fallback qui sotto e varrebbe 1.5: e' il motivo per cui in SKILL.md
        # c'era una tabella delle migliaia che il modello applicava a memoria.
        # In assoluto "1.500" resta ambiguo (potrebbe essere 1,5 all'inglese),
        # ma e' un'ambiguita' irriducibile: il punto e' che ora sta in un posto
        # solo, con un test accanto.
        s = s.replace(".", "")
    elif re.fullmatch(r"\d+", s):
        pass
    elif not re.fullmatch(r"\d+\.\d+", s):
        return False

    valore = float(s)
    return valore if valore > 0 else False


_SI = {"si", "s", "ok", "okay", "yes", "y", "va bene", "vabene", "certo",
       "conferma", "confermo", "esatto", "giusto", "perfetto", "procedi", "vai"}
_NO = {"no", "n", "annulla", "no grazie", "sbagliato", "negativo", "lascia perdere"}


def interpreta_conferma(testo):
    """'Si' | 'No' | '' (non capito: si rimostra il riepilogo).

    "1" e "2" sono deliberatamente fuori da entrambi gli insiemi: sarebbero
    ambigui contro un numero di categoria se lo stato andasse alla deriva.
    """
    p = _piatto(testo)
    if p in _SI:
        return "Si"
    if p in _NO:
        return "No"
    return ""

# ─────────────────────────────────────────────
# Bozza: lo stato del dialogo, su disco
# ─────────────────────────────────────────────

@contextlib.contextmanager
def _bozza_lock():
    """Serializza il ciclo leggi-fondi-scrivi sulla bozza.

    Senza, due invocazioni ravvicinate leggono la stessa bozza e la seconda
    scrittura perde il campo della prima: lo stesso sintomo che tutta questa
    riscrittura elimina, ma da un'altra causa. Non va mai tenuto durante la
    chiamata HTTP a Google, o una richiesta appesa blocca ogni turno successivo.
    """
    percorso = BOZZA_FILE + ".lock"
    try:
        fd = os.open(percorso, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        yield  # senza lock si va avanti lo stesso: meglio degradati che fermi
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def campi_vuoti():
    return {c: "" for c in CAMPI}


def carica_bozza(ora=None):
    """La bozza viva, la stringa "scaduta", oppure None.

    Qualunque anomalia — file assente, JSON rotto, versione ignota — vale come
    "nessuna bozza": chi sta registrando una spesa non deve mai vedere un
    traceback.
    """
    ora = time.time() if ora is None else ora
    try:
        with open(BOZZA_FILE, encoding="utf-8") as f:
            bozza = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(bozza, dict) or bozza.get("versione") != BOZZA_VERSIONE:
        cancella_bozza()
        return None
    if ora - bozza.get("aggiornato", 0) > BOZZA_TTL:
        cancella_bozza()
        return "scaduta"
    campi = campi_vuoti()
    campi.update({k: v for k, v in (bozza.get("campi") or {}).items() if k in CAMPI})
    bozza["campi"] = campi
    return bozza


def salva_bozza(stato, campi, ora=None):
    """Scrittura atomica: un lettore vede la bozza vecchia o la nuova, mai meta'."""
    tmp = f"{BOZZA_FILE}.{os.getpid()}.tmp"
    payload = {
        "versione": BOZZA_VERSIONE,
        "aggiornato": time.time() if ora is None else ora,
        "stato": stato,
        "campi": campi,
    }
    try:
        # O_NOFOLLOW e 0600: il fallback in /tmp e' un percorso prevedibile e
        # condiviso, e qui dentro c'e' quanto e dove spende una famiglia.
        fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, BOZZA_FILE)
    except OSError:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def cancella_bozza():
    with contextlib.suppress(OSError):
        os.unlink(BOZZA_FILE)

# ─────────────────────────────────────────────
# Logica del dialogo
# ─────────────────────────────────────────────

def _stessa_categoria(a, b):
    """Confronto in forma canonica: "3", "supermercato" e "Supermercato" sono la
    stessa categoria. Confrontare le stringhe grezze farebbe decadere una
    sottocategoria gia' scelta solo perche' l'utente ha ridetto la categoria in
    un altro modo."""
    ca, cb = trova_categoria(a), trova_categoria(b)
    if ca is None or cb is None:
        return str(a) == str(b)
    return ca["nome"] == cb["nome"]


def unisci(campi, nuovi):
    """Fonde nella bozza i campi nuovi, ignorando quelli non passati (None).

    Regola d'oro: nel dubbio si fonde e si richiede conferma, mai si scarta. La
    conferma e' la rete di sicurezza — niente arriva sul foglio senza che
    l'utente abbia letto la riga intera — quindi una fusione sbagliata e'
    visibile e si annulla in un turno, mentre uno scarto automatico sarebbe
    silenzioso e distruggerebbe quello che l'utente aveva gia' detto.
    """
    campi = dict(campi)
    cambiato = False
    for chiave, valore in nuovi.items():
        if valore is None or chiave not in CAMPI:
            continue
        if chiave == "categoria" and not _stessa_categoria(valore, campi.get("categoria")):
            campi["sottocategoria"] = ""  # appartiene alla categoria di prima
        campi[chiave] = valore
        if chiave != "conferma":
            cambiato = True
    if cambiato:
        campi["conferma"] = ""  # ogni modifica invalida una conferma gia' data
    return campi


def normalizza(campi):
    """Normalizza i campi e dice qual e' il primo che manca o non va.

    Ritorna (campi, stato, rifiutato). `stato` e' None quando e' tutto a posto;
    `rifiutato` e' il valore grezzo che non si e' capito, per poterlo citare nel
    messaggio. Solo il campo incriminato viene azzerato: quelli a valle restano,
    che e' la differenza con il vecchio gateway — li cancellava tutti e il
    chiamante doveva ricordarseli.
    """
    campi = dict(campi)

    if not campi.get("data"):
        campi["data"] = datetime.now().strftime("%d/%m/%Y")
    campi["data"] = normalizza_data_relativa(campi["data"])
    # E' l'unico punto da cui ogni data passa: relativa, parlata o in cifre.
    # Il formato prima dell'anno, e l'ordine non e' indifferente: "31/02/2025"
    # non e' una data di un altro anno, e' una data che non esiste.
    if not validate_data(campi["data"]) or not _nell_anno(campi["data"]):
        rifiutato, campi["data"] = campi["data"], ""
        return campi, "chiedi_data", rifiutato

    importo = validate_importo(campi.get("importo", ""))
    if importo is False:
        rifiutato, campi["importo"] = campi.get("importo", ""), ""
        return campi, "chiedi_importo", rifiutato
    campi["importo"] = importo

    cat = trova_categoria(campi.get("categoria"))
    if cat is None:
        rifiutato, campi["categoria"] = campi.get("categoria", ""), ""
        campi["sottocategoria"] = ""
        return campi, "chiedi_categoria", rifiutato
    campi["categoria"] = cat["nome"]

    if not cat["sottocategorie"]:
        # La categoria non ne prevede: lo decide la tassonomia, non chi chiama.
        campi["sottocategoria"] = ""
        sotto = None
    else:
        sotto = trova_sottocategoria(cat, campi.get("sottocategoria"))
        if sotto is None:
            rifiutato, campi["sottocategoria"] = campi.get("sottocategoria", ""), ""
            return campi, "chiedi_sottocategoria", rifiutato
        campi["sottocategoria"] = sotto["nome"]

    if tipo_di(cat, sotto) is None:
        return campi, "errore_tassonomia", ""

    if campi.get("conferma") != "Si":
        return campi, "chiedi_conferma", ""

    return campi, None, ""


def risolvi_risposta(stato, testo):
    """Il testo dell'utente diventa il campo che lo script stava aspettando.

    Lo script sa che domanda ha fatto: chi lo chiama non deve indovinare a quale
    campo appartenga la risposta. E' l'instradamento che prima toccava al
    modello, ed e' dove sbagliava.
    """
    testo = testo.strip()
    campo = {
        "chiedi_data": "data",
        "chiedi_importo": "importo",
        "chiedi_categoria": "categoria",
        "chiedi_sottocategoria": "sottocategoria",
    }.get(stato)
    if campo:
        return {campo: testo}
    if stato == "chiedi_conferma":
        return {"conferma": interpreta_conferma(testo)}
    return {}

# ─────────────────────────────────────────────
# Messaggi: il testo completo da mostrare all'utente
# ─────────────────────────────────────────────

ETICHETTE = (("Importo", "importo"), ("Data", "data"), ("Tipo", "tipo"),
             ("Categoria", "categoria"), ("Sottocategoria", "sottocategoria"),
             ("Descrizione", "descrizione"), ("Note", "note"))


def riepilogo(campi, tipo):
    righe = []
    for etichetta, chiave in ETICHETTE:
        if chiave == "tipo":
            valore = tipo
        elif chiave == "importo":
            valore = f"{campi['importo']:.2f} €" if campi.get("importo") != "" else ""
        else:
            valore = campi.get(chiave, "")
        righe.append(f"{etichetta + ':':<16}{valore or '—'}")
    return "\n".join(righe)


def _elenco(voci):
    """Numerato con l'id della tassonomia, non con la posizione: cosi' il
    contratto regge anche se un giorno gli id avranno dei buchi."""
    return "\n".join(f"{v['id']}. {v['nome']}" for v in voci)


def componi_messaggio(stato, campi, rifiutato="", tipo="", dettaglio=""):
    """Il testo intero da mostrare: elenco numerato e riepilogo gia' dentro.

    Chi chiama deve avere esattamente una cosa da stampare, e stamparla deve
    essere la strada facile. Per lo stesso motivo i messaggi sono battute
    complete e non frammenti da modulo: "Confermi?" da solo non e' una frase che
    si possa ripetere, e chi la riceve fa la cosa ragionevole — la riscrive.
    """
    if stato == "chiedi_data":
        if rifiutato and validate_data(rifiutato):
            # Formato giusto, anno sbagliato: dirgli che non si e' capito
            # sarebbe falso, e lo manderebbe a riscrivere la stessa data nello
            # stesso formato. Niente esempio: il formato lo conosce gia'.
            return (f"Questo budget tiene solo il {ANNO_BUDGET}, e «{rifiutato}» è di un "
                    f"altro anno. Non posso registrarla qui. Di che giorno del "
                    f"{ANNO_BUDGET} si tratta?")
        # L'esempio e' oggi e non un 01/09 fisso: un letterale sarebbe una data
        # che _nell_anno finisce per rifiutare appena ANNO_BUDGET si muove, e il
        # plugin arriverebbe a suggerire una data che poi rifiuta. Che oggi sia
        # dentro l'anno lo garantisce anno_disallineato(), che quando non lo e'
        # ferma il turno prima e qui non ci si arriva.
        esempio = datetime.now().strftime("%d/%m/%Y")
        if rifiutato:
            return (f"Non ho capito la data «{rifiutato}». Scrivila come gg/mm/aaaa, "
                    f"per esempio {esempio}.")
        return f"Di che giorno è? Scrivilo come gg/mm/aaaa, per esempio {esempio}."

    if stato == "chiedi_importo":
        if rifiutato:
            return (f"Non ho capito l'importo «{rifiutato}». Scrivi solo la cifra, "
                    "per esempio 12,50.")
        return "Qual è l'importo? Scrivi solo la cifra, per esempio 12,50."

    if stato == "chiedi_categoria":
        testa = f"Non ho trovato la categoria «{rifiutato}».\n\n" if rifiutato else ""
        return (f"{testa}Quale categoria? Rispondi con il numero.\n\n"
                + _elenco(leggi_tassonomia()))

    if stato == "chiedi_sottocategoria":
        cat = trova_categoria(campi.get("categoria"))
        testa = f"Non ho trovato la sottocategoria «{rifiutato}».\n\n" if rifiutato else ""
        return (f"{testa}Quale sottocategoria di «{cat['nome']}»? Rispondi con il numero.\n\n"
                + _elenco(cat["sottocategorie"]))

    if stato == "chiedi_conferma":
        testa = "Non ho capito. Rispondi sì o no.\n\n" if rifiutato else ""
        return f"{testa}{riepilogo(campi, tipo)}\n\nConfermi?"

    if stato == "scritto":
        return f"Registrato.\n\n{riepilogo(campi, tipo)}"

    if stato == "annullata":
        return "Ok, lascio perdere. Non ho registrato niente."

    if stato in ("bozza_scaduta", "bozza_assente"):
        return ("Non sto registrando niente al momento. Dimmi cosa devo registrare: "
                "quanto hai speso e per cosa.")

    if stato == "errore_auth":
        return ("Non riesco ad accedere al foglio: le credenziali Google vanno "
                "rigenerate. Non ho registrato niente.")

    if stato == "errore_scrittura":
        return ("Non sono riuscito a scrivere sul foglio. Non ho registrato niente — "
                "rispondi «sì» per riprovare.")

    if stato == "scrittura_in_corso":
        return "Sto già registrando questa transazione: dammi un secondo."

    if stato == "errore_bozza":
        return ("Non riesco a tenere nota di questa transazione: c'è un problema sul "
                "server. Non ho registrato niente.")

    if stato == "errore_anno":
        return (f"Il budget è impostato sul {ANNO_BUDGET}, ma siamo nel "
                f"{datetime.now().year}. Non registro niente finché non viene "
                "aggiornato: serve la scheda del nuovo anno sul foglio e l'anno "
                "nuovo nella configurazione.")

    if stato == "errore_configurazione":
        mancanti = configurazione_mancante()
        verbo = "va impostato" if len(mancanti) == 1 else "vanno impostati"
        return (f"Il budget non è configurato su questa istanza: nel file .env del "
                f"profilo Hermes {verbo} {' e '.join(mancanti)}. Non ho registrato niente.")

    if stato == "errore_tassonomia":
        dove = f"{campi.get('categoria')} / {campi.get('sottocategoria')}".strip(" /")
        return (f"Non riesco a capire se «{dove}» è un'entrata o un'uscita: la "
                "tassonomia va corretta. Non ho registrato niente.")

    return dettaglio

# ─────────────────────────────────────────────
# Operazioni sullo sheet
# ─────────────────────────────────────────────

def append_row(access_token, data, tipo, categoria, sottocategoria, importo, descrizione, note):
    row = [[data, tipo, categoria, sottocategoria, float(importo), descrizione, note]]
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{GOOGLE_SPREADSHEET_ID}"
        f"/values/{urllib.parse.quote(GOOGLE_SHEET_NAME)}!A:G:append"
        f"?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS"
    )
    result, _ = _api_request("POST", url, access_token, body={"values": row})
    return result.get("updates", {}).get("updatedRange", "?")

# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

EXIT = {
    "scritto": 0,
    "errore_auth": 1,
    "errore_scrittura": 2,
    "errore_tassonomia": 5,
    "errore_bozza": 6,
    "errore_anno": 7,
    "errore_configurazione": 8,
}


class _Risultato(Exception):
    """Il payload di un turno, sollevato per srotolare fin fuori dai lock.

    Qui prima c'era sys.exit(): perfetto per la CLI, e rendeva lo script
    inutilizzabile da dentro un processo che non deve morire — l'handler di un
    tool, per dire. Un'eccezione srotola le `with _bozza_lock()` esattamente
    come faceva SystemExit, quindi il lock si rilascia come prima.
    """

    def __init__(self, payload):
        super().__init__(payload["stato"])
        self.payload = payload


def _emetti(stato, campi, rifiutato="", tipo="", intervallo="", opzioni=None):
    """L'unico payload del turno. Sempre le stesse chiavi, sempre lo stato completo."""
    payload = {
        "stato": stato,
        "messaggio": componi_messaggio(stato, campi, rifiutato, tipo),
        "data": campi.get("data", ""),
        "importo": campi.get("importo", ""),
        "categoria": campi.get("categoria", ""),
        "sottocategoria": campi.get("sottocategoria", ""),
        "tipo": tipo,
        "descrizione": campi.get("descrizione", ""),
        "note": campi.get("note", ""),
        "conferma": campi.get("conferma", ""),
        "opzioni": opzioni or [],
        "intervallo": intervallo,
    }
    raise _Risultato(payload)


def _opzioni_per(stato, campi):
    """Nel payload solo per test e diagnostica: il testo da mostrare e' gia'
    tutto dentro "messaggio"."""
    if stato == "chiedi_categoria":
        return [c["nome"] for c in leggi_tassonomia()]
    if stato == "chiedi_sottocategoria":
        cat = trova_categoria(campi.get("categoria"))
        return [s["nome"] for s in cat["sottocategorie"]] if cat else []
    return []


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"ERRORE uso: {message}", file=sys.stderr)
        sys.exit(64)


def stato_corrente():
    """Lo stato della bozza su disco, o "" se non ce n'e' una viva.

    Serve a chi deve decidere qualcosa *prima* di chiamare `esegui()` — se il
    turno e' una continuazione o una transazione nuova, per esempio: la risposta
    e' sempre qui, non nella memoria di chi chiama. Prende il lock e lo rilascia
    prima di ritornare: `_bozza_lock` apre un fd nuovo a ogni chiamata e usa
    flock, quindi una riacquisizione annidata nello stesso processo si
    impianterebbe.
    """
    with _bozza_lock():
        bozza = carica_bozza()
    return bozza["stato"] if isinstance(bozza, dict) else ""


def in_dialogo():
    """C'e' una transazione a meta'?

    E' l'unica domanda che serve per instradare un turno, e la risposta sta sul
    disco: non la si chiede a chi chiama e non la si tiene in sessione.
    """
    return stato_corrente().startswith("chiedi_")


def esegui(*, nuova=False, annulla=False, risposta=None, data=None, importo=None,
           categoria=None, sottocategoria=None, descrizione=None, note=None):
    """Un turno di dialogo. Ritorna il payload: non stampa e non esce.

    E' il punto d'ingresso per chi chiama lo script da dentro un processo. La
    CLI ci passa sopra come chiunque altro, cosi' non ci sono due strade che
    possono divergere.
    """
    try:
        _turno(nuova=nuova, annulla=annulla, risposta=risposta, data=data,
               importo=importo, categoria=categoria, sottocategoria=sottocategoria,
               descrizione=descrizione, note=note)
    except _Risultato as risultato:
        return risultato.payload
    raise AssertionError("_turno finisce sempre con _emetti")


def _turno(*, nuova, annulla, risposta, data, importo, categoria,
           sottocategoria, descrizione, note):
    passati = {"data": data, "importo": importo, "categoria": categoria,
               "sottocategoria": sottocategoria, "descrizione": descrizione,
               "note": note}

    with _bozza_lock():
        if annulla:
            cancella_bozza()
            _emetti("annullata", campi_vuoti())

        if configurazione_mancante():
            # Dopo `annulla` per la stessa ragione della guardia d'anno, e prima
            # di quella perche' con ANNO_BUDGET mancante non avrebbe senso.
            _emetti("errore_configurazione", campi_vuoti())

        if anno_disallineato():
            _emetti("errore_anno", campi_vuoti())

        if nuova:
            cancella_bozza()

        bozza = carica_bozza()
        if isinstance(bozza, dict) and bozza["stato"] == "scrittura_in_corso":
            # Un'altra invocazione ha gia' mandato questa riga a Google e sta
            # aspettando la risposta: scriverla di nuovo farebbe un doppione, e
            # un doppione su un foglio di spese non lo nota nessuno.
            _emetti("scrittura_in_corso", bozza["campi"])

        if risposta is not None and not isinstance(bozza, dict):
            _emetti("bozza_scaduta" if bozza == "scaduta" else "bozza_assente", campi_vuoti())

        campi = bozza["campi"] if isinstance(bozza, dict) else campi_vuoti()
        nuovi = {c: passati.get(c) for c in CAMPI if c != "conferma"}
        if risposta is not None:
            nuovi.update(risolvi_risposta(bozza["stato"], risposta))

        conferma_rifiutata = (risposta is not None
                              and bozza["stato"] == "chiedi_conferma"
                              and nuovi.get("conferma") == "")
        if nuovi.get("conferma") == "No":
            # "No" non annulla: tiene data e importo e rifa' la domanda sulla
            # categoria, che e' l'errore piu' probabile in un riepilogo rifiutato.
            nuovi.update({"categoria": "", "sottocategoria": "", "conferma": ""})

        campi = unisci(campi, nuovi)
        campi, stato, rifiutato = normalizza(campi)

        if stato == "chiedi_conferma" and conferma_rifiutata:
            rifiutato = risposta

        def _salva(nuovo_stato):
            try:
                salva_bozza(nuovo_stato, campi)
            except OSError as e:
                # Senza bozza il dialogo non puo' proseguire: la risposta al turno
                # dopo non avrebbe piu' un contesto a cui attaccarsi. Meglio dirlo
                # che fare una domanda di cui si perdera' la risposta.
                print(f"ERRORE bozza: {e}", file=sys.stderr)
                _emetti("errore_bozza", campi)

        cat = trova_categoria(campi["categoria"])
        sotto = trova_sottocategoria(cat, campi["sottocategoria"])
        tipo = tipo_di(cat, sotto) or ""

        if stato == "errore_tassonomia":
            # Non e' una domanda ma un errore di configurazione: salvarlo come
            # stato lascerebbe la bozza in un punto a cui nessuna risposta sa
            # rispondere. La bozza di prima resta dov'era.
            _emetti(stato, campi, rifiutato, tipo)

        if stato is not None:
            _salva(stato)
            _emetti(stato, campi, rifiutato, tipo, opzioni=_opzioni_per(stato, campi))

        # La riga e' pronta. Si marca la bozza prima di uscire dal lock: se
        # arrivasse un secondo turno mentre Google risponde, trovera' il marcatore
        # invece di mandare la stessa riga una seconda volta.
        _salva("scrittura_in_corso")

    # Fuori dal lock: la chiamata a Google puo' essere lenta, e tenerlo bloccato
    # qui fermerebbe ogni turno successivo per tutto il TTL.
    def _fallita(stato_errore, eccezione):
        print(f"ERRORE {stato_errore.removeprefix('errore_')}: {eccezione}", file=sys.stderr)
        with _bozza_lock():
            # Riportata alla conferma, senza il "Si": si riprende con una parola
            # invece di ridettare tutto, ma la scrittura non riparte da sola.
            campi["conferma"] = ""
            with contextlib.suppress(OSError):
                salva_bozza("chiedi_conferma", campi)
        _emetti(stato_errore, campi, tipo=tipo)

    try:
        token = get_access_token()
    except Exception as e:
        _fallita("errore_auth", e)

    try:
        intervallo = append_row(token, campi["data"], tipo, campi["categoria"],
                                campi["sottocategoria"], campi["importo"],
                                campi["descrizione"], campi["note"])
    except Exception as e:
        _fallita("errore_scrittura", e)

    with _bozza_lock():
        cancella_bozza()
    _emetti("scritto", campi, tipo=tipo, intervallo=intervallo)


def main():
    """La CLI: parsing, un JSON su stdout, un exit code. Nient'altro."""
    parser = _Parser(description="Budget Familiare — CLI per Google Sheets")
    subparsers = parser.add_subparsers(dest="command")

    p = subparsers.add_parser("append", help="Registra una transazione, un turno alla volta")
    p.add_argument("--nuova",   action="store_true", help="Scarta la bozza in corso e ricomincia")
    p.add_argument("--annulla", action="store_true", help="Abbandona la transazione in corso")
    p.add_argument("--risposta",       default=None, help="Quello che ha scritto l'utente")
    p.add_argument("--data",           default=None, help="Data gg/mm/aaaa, o \"ieri\" (default: oggi)")
    p.add_argument("--categoria",      default=None, help="Nome o id da references/tassonomia.yaml")
    p.add_argument("--sottocategoria", default=None)
    p.add_argument("--importo",        default=None, help="Importo positivo (es. 23.50)")
    p.add_argument("--descrizione",    default=None)
    p.add_argument("--note",           default=None)

    args = parser.parse_args()
    if args.command != "append":
        parser.print_usage(sys.stderr)
        print("ERRORE uso: serve un sottocomando (append)", file=sys.stderr)
        sys.exit(64)

    payload = esegui(nuova=args.nuova, annulla=args.annulla, risposta=args.risposta,
                     data=args.data, importo=args.importo, categoria=args.categoria,
                     sottocategoria=args.sottocategoria, descrizione=args.descrizione,
                     note=args.note)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(EXIT.get(payload["stato"], 3))


if __name__ == "__main__":
    main()
