# 📚 Registro Elettronico — Versione CLOUD v2.0 (con utenti)

Versione **multi-utente sincronizzata** con sistema di accesso tramite **link magici personali**.

## 👥 Cosa cambia rispetto alla v1

- **Un super-utente "Preside"** (Gian Lorenzo La Marca) gestisce tutti gli altri utenti
- **Tre ruoli**:
  - **Preside** — crea/modifica/elimina maestri e allievi
  - **Maestro** — inserisce voti, note, presenze, compiti, comunicazioni
  - **Allievo** — vede tutto in sola lettura
- **Accesso via link personale** — niente password, ogni utente ha un suo link tipo `https://...onrender.com/#/login/abc123xyz`
- **QR code stampabile** per ogni utente — comodo per i bambini

---

## 🚀 Setup passo-passo

### **PASSO 1 — MongoDB Atlas** (5 min)
Identico alla guida precedente. Crea cluster M0 free, utente DB, IP `0.0.0.0/0`, copia la connection string.

### **PASSO 2 — GitHub** (3 min)
1. Crea repo `registro-elettronico` (privato)
2. Carica TUTTO il contenuto della cartella `registro-elettronico-cloud` (server.py, requirements.txt, Procfile, render.yaml, static/, ecc.) alla radice del repo

### **PASSO 3 — Render Web Service** (5 min)
1. New + → Web Service → collega `registro-elettronico`
2. Runtime: **Python 3**
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
5. Instance: **Free**
6. Environment Variables (clicca "Add Environment Variable" 4 volte):
   | Key | Value |
   |-----|-------|
   | `MONGO_URL` | la stringa MongoDB del Passo 1 |
   | `DB_NAME` | `registro_elettronico` |
   | `CORS_ORIGINS` | `*` |
   | `PRESIDE_TOKEN` | **scegli tu un codice segreto** (es. `gianlorenzo-presi-2026-segreto`) |
7. **"Deploy Web Service"**

⏳ Aspetta 5-8 minuti per il primo deploy.

### **PASSO 4 — Ottieni il link del Preside**

Quando Render mostra **"Live"** in verde:

**Opzione A — Tramite PRESIDE_TOKEN**: il link è semplicemente:
```
https://<TUO-URL>.onrender.com/#/login/<IL-VALORE-DI-PRESIDE_TOKEN>
```
Esempio: se hai messo `PRESIDE_TOKEN=gianlorenzo-presi-2026-segreto` e l'URL è `https://registro-abc.onrender.com`, il link è:
```
https://registro-abc.onrender.com/#/login/gianlorenzo-presi-2026-segreto
```

**Opzione B — Dai log Render**: Render dashboard → tuo servizio → **"Logs"** → cerca:
```
PRESIDE LOGIN LINK (Gian Lorenzo La Marca):
  /#/login/abc123xyz
```
Combina con il dominio `https://<TUO-URL>.onrender.com` per ottenere il link completo.

### **PASSO 5 — Primo accesso del Preside**

1. Apri il link del Preside nel browser
2. Sarai automaticamente dentro come Gian Lorenzo La Marca
3. Vai a **"Gestione Utenti"** dalla sidebar
4. Crea i primi maestri (es. "Maria Rossi", ruolo: maestro)
5. Crea gli allievi (es. "Marco Bianchi", ruolo: allievo)
6. Per ogni utente, clicca **"Link / QR"** → copia il link da inviare o stampa il QR

### **PASSO 6 — Inviare i link**

- **Maestri**: invii il link via WhatsApp/email
- **Allievi**: stampi il QR e lo dai al bambino (può scansionarlo con la fotocamera del tablet)

Ogni utente, al primo click, è automaticamente loggato nel proprio ruolo. **Tutti vedono lo stesso registro** in tempo reale.

---

## 🔧 Cose utili da sapere

### Cambiare nome o link a un utente
Sei dentro come Preside → Gestione Utenti → per ogni utente:
- **Rinomina** — cambia il nome
- **Nuovo Link** — genera un nuovo link (il vecchio smette di funzionare; utile se il link è stato condiviso per sbaglio)
- **Cestino** — elimina l'utente (e tutti i suoi dati se è un allievo)

### Hai perso il link del Preside?
Vai su Render → Environment → controlla `PRESIDE_TOKEN`. Il link è `https://<url>/#/login/<token>`. Se non lo hai impostato, vai nei Logs e cerca "PRESIDE LOGIN LINK".

### Resettare tutti i dati
Su MongoDB Atlas → Browse Collections → elimina il database `registro_elettronico` → riavvia il servizio Render (Manual Deploy → Deploy latest commit). Il preside e i dati di esempio vengono ricreati automaticamente.

### Limite Render Free
Il server "dorme" dopo 15 min di inattività. Il primo accesso impiega ~30 sec a svegliarlo. Usi successivi sono istantanei.

---

## ⚠️ Note sulla sicurezza

Il sistema usa **token di accesso non crittografati** trasmessi via URL. **NON è progettato per dati sensibili reali** — è pensato per il gioco "alla scuola" tra bambini. Per uso reale serve aggiungere:
- Token expiration
- Rate limiting
- HTTPS-only cookies
- Password vere

Se in futuro vuoi proteggere meglio l'app, torna pure qui e lo aggiungiamo.

---

Buon gioco! 🎓🎵
