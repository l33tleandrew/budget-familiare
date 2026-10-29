#!/usr/bin/env python3
"""
setup_google.py — il primo consenso OAuth di un'istanza, e la verifica che regga.

Tre passi, con la copia installata nel profilo dell'istanza
(<profilo>/plugins/budget-familiare/): e' da li' che si ricava il profilo.

  python3 setup_google.py url                    # l'indirizzo da aprire nel browser
  python3 setup_google.py codice "<indirizzo>"   # quello su cui il browser e' finito
  python3 setup_google.py verifica               # token, foglio e scheda; non scrive niente

Il browser puo' stare su un'altra macchina: il server non deve ricevere niente,
basta incollargli l'indirizzo. Si chiede un solo scope, `spreadsheets`, quello
dichiarato in privacy.md.

Exit code:
  0   fatto, o tutto a posto
  1   qualcosa non va: il messaggio dice cosa
  64  errore d'uso
"""
import base64
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import budget_sheets as bs

SCOPE        = "https://www.googleapis.com/auth/spreadsheets"
AUTH_URL     = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL    = "https://oauth2.googleapis.com/token"
# Un client "App desktop" accetta qualunque porta di loopback. Sulla 1 non
# ascolta nessuno, ed e' voluto: il browser si ferma su una pagina che non si
# carica, con il codice nella barra degli indirizzi.
REDIRECT_URI = "http://localhost:1"
PENDING_FILE = os.path.join(bs.PROFILE_DIR, "budget_oauth_pending.json")


class Errore(Exception):
    """Qualcosa che chi installa puo' sistemare: il messaggio dice come."""


def _scrivi_privato(percorso, dati):
    """Scrittura atomica, 0600, come la bozza: dentro ci sono segreti.

    Un file nuovo e poi os.replace, e non un O_TRUNC sul vecchio: quello ne
    conserverebbe i permessi, qualunque fossero.
    """
    tmp = f"{percorso}.{os.getpid()}.tmp"
    try:
        fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dati, f, indent=2)
        os.replace(tmp, percorso)
    except OSError:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _client():
    """(client_id, client_secret) del client OAuth del profilo, che deve essere desktop."""
    try:
        with open(bs.CRED_FILE, encoding="utf-8") as f:
            tipo = next(iter(json.load(f)), None)
        client = bs._load_creds()
    except FileNotFoundError:
        raise Errore(f"Manca {bs.CRED_FILE}. Scarica il client OAuth dalla Google Cloud "
                     "Console (Credenziali, tipo «App desktop») e copialo li'.")
    except (ValueError, KeyError, IndexError, AttributeError, TypeError) as e:
        raise Errore(f"{bs.CRED_FILE} non e' un client OAuth valido: {e}")
    if tipo != "installed":
        raise Errore(f"Il client in {bs.CRED_FILE} e' di tipo «{tipo}»: serve un client "
                     "«App desktop», l'unico che accetta il ritorno su localhost.")
    return client


def prepara_url():
    """L'indirizzo del consenso. Il verifier PKCE resta nel profilo per `codice`.

    PKCE perche' il codice passa da un copia-incolla, forse da una chat: senza il
    verifier, che non lascia mai il server, chi lo intercettasse non potrebbe
    scambiarlo.
    """
    client_id, _ = _client()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    _scrivi_privato(PENDING_FILE, {"verifier": verifier, "state": state,
                                   "creato": time.time()})
    return AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",   # senza, niente refresh_token
        "prompt": "consent",        # senza, al secondo giro Google non lo rimanda
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    })


def _estrai(testo):
    """(codice, state) dall'indirizzo incollato; (testo, None) se e' il solo codice."""
    testo = testo.strip()
    if "?" not in testo:
        return testo, None
    query = urllib.parse.parse_qs(urllib.parse.urlparse(testo).query)
    if "error" in query:
        raise Errore(f"Google non ha dato il consenso: {query['error'][0]}. "
                     "Ricomincia da `setup_google.py url`.")
    if "code" not in query:
        raise Errore("Nell'indirizzo non c'e' un codice: copia quello intero dalla barra "
                     "del browser, dopo il consenso.")
    return query["code"][0], query.get("state", [None])[0]


def scambia_codice(testo, forza=False):
    """Scambia il codice con un token e lo scrive nel profilo, nel formato del motore."""
    if os.path.exists(bs.TOKEN_FILE) and not forza:
        # Prima della rete: il codice vale una volta sola, e cosi' non si consuma.
        raise Errore(
            f"{bs.TOKEN_FILE} esiste gia'. Potrebbe servire a un'altra integrazione "
            "Google del profilo — la skill google-workspace di Hermes usa lo stesso "
            "file — e sostituirlo le toglierebbe l'accesso. Se va sostituito davvero, "
            "ripeti con --force.")
    try:
        with open(PENDING_FILE, encoding="utf-8") as f:
            attesa = json.load(f)
    except (OSError, ValueError):
        raise Errore("Non c'e' un consenso in corso: comincia da `setup_google.py url`.")

    codice, state = _estrai(testo)
    if state is not None and state != attesa.get("state"):
        raise Errore("L'indirizzo non viene dall'ultimo `setup_google.py url`: "
                     "ricomincia da li'.")

    client_id, client_secret = _client()
    richiesta = urllib.request.Request(TOKEN_URL, method="POST", data=urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": codice,
        "code_verifier": attesa.get("verifier", ""),
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode())
    try:
        with urllib.request.urlopen(richiesta) as r:
            risposta = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise Errore(f"Google ha rifiutato il codice ({e.code}): {e.read().decode()[:300]}\n"
                     "Il codice scade in pochi minuti e vale una volta sola: ricomincia "
                     "da `setup_google.py url`.")

    if SCOPE not in risposta.get("scope", "").split():
        # Il consenso di Google ha le caselle: si puo' accettare senza spuntarla.
        raise Errore("Nel consenso non e' stato autorizzato l'accesso a Fogli Google. "
                     "Ricomincia da `setup_google.py url` e spunta la casella.")
    if "refresh_token" not in risposta:
        raise Errore("Google non ha mandato un refresh_token. Revoca l'accesso precedente "
                     "da https://myaccount.google.com/permissions e ricomincia da "
                     "`setup_google.py url`.")

    _scrivi_privato(bs.TOKEN_FILE, {
        "access_token": risposta["access_token"],
        "refresh_token": risposta["refresh_token"],
        "expires_at": time.time() + risposta.get("expires_in", 3600),
    })
    os.unlink(PENDING_FILE)


def verifica():
    """[(ok, riga)] per ogni controllo, fermandosi dove i successivi non avrebbero senso.

    Legge titolo e nomi delle schede, e nient'altro: e' la prova che token, id
    e scheda reggono, fatta senza scrivere una riga finta sul foglio di qualcuno.
    """
    esito = []

    mancanti = bs.configurazione_mancante()
    esito.append((not mancanti, f"configurazione in {bs.PROFILE_DIR}: " + (
        "foglio e anno impostati" if not mancanti
        else f"{'manca' if len(mancanti) == 1 else 'mancano'} {' e '.join(mancanti)} nel .env")))
    for percorso, cosa in ((bs.CRED_FILE, "client OAuth"), (bs.TOKEN_FILE, "token")):
        presente = os.path.exists(percorso)
        esito.append((presente, f"{cosa}: {percorso}" + ("" if presente else " — manca")))
    if not all(ok for ok, _ in esito):
        return esito

    try:
        token = bs.get_access_token()
    except Exception as e:                       # noqa: BLE001 — qualunque cosa, la si mostra
        esito.append((False, f"accesso a Google: {e}"))
        return esito
    esito.append((True, "accesso a Google: token valido"))

    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{bs.GOOGLE_SPREADSHEET_ID}"
           "?fields=properties.title,sheets.properties.title")
    try:
        foglio, _ = bs._api_request("GET", url, token)
    except Exception as e:                       # noqa: BLE001
        esito.append((False, f"foglio {bs.GOOGLE_SPREADSHEET_ID}: {e} — controlla l'id, e "
                             "che l'account del consenso possa modificarlo"))
        return esito
    schede = [s.get("properties", {}).get("title") for s in foglio.get("sheets", [])]
    esito.append((True, f"foglio: «{foglio.get('properties', {}).get('title', '?')}»"))

    c_e = bs.GOOGLE_SHEET_NAME in schede
    esito.append((c_e, f"scheda «{bs.GOOGLE_SHEET_NAME}»: " + (
        "c'e'" if c_e else f"non c'e' — ci sono: {', '.join(schede) or 'nessuna'}")))
    esito.append((not bs.anno_disallineato(),
                  f"anno: ANNO_BUDGET={bs.ANNO_BUDGET}, anno civile {datetime.now().year}"))
    return esito


def main():
    parser = bs._Parser(description="Budget Familiare — consenso Google e verifica")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("url", help="Stampa l'indirizzo del consenso")
    p = sub.add_parser("codice", help="Scambia il codice con un token")
    p.add_argument("indirizzo", help="L'indirizzo su cui il browser e' finito, o il solo codice")
    p.add_argument("--force", action="store_true", help="Sostituisce un token gia' presente")
    sub.add_parser("verifica", help="Controlla token, foglio e scheda, senza scrivere")
    args = parser.parse_args()

    try:
        if args.command == "url":
            print("Apri questo indirizzo nel browser, con l'account Google che puo' "
                  "modificare il foglio:\n")
            print(prepara_url())
            print("\nDopo il consenso il browser finisce su una pagina che non si carica "
                  f"({REDIRECT_URI}/…): e' normale.\nCopia l'indirizzo intero dalla barra "
                  "e lancia:\n\n  python3 setup_google.py codice \"<indirizzo>\"")
        elif args.command == "codice":
            scambia_codice(args.indirizzo, forza=args.force)
            print(f"Token salvato in {bs.TOKEN_FILE}. Ora: python3 setup_google.py verifica")
        elif args.command == "verifica":
            esito = verifica()
            for ok, riga in esito:
                print(("✓ " if ok else "✗ ") + riga)
            sys.exit(0 if all(ok for ok, _ in esito) else 1)
        else:
            parser.print_usage(sys.stderr)
            print("ERRORE uso: serve un sottocomando (url, codice, verifica)", file=sys.stderr)
            sys.exit(64)
    except Errore as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
