# Tool Definition: YouTube Data API v3 (Search Endpoint)

## Descrizione
Questo strumento interfaccia l'endpoint `search` dell'API ufficiale di YouTube.
Permette di recuperare una lista di video da un canale specifico, applicando filtri opzionali come data di pubblicazione o ordinamento.

**Base URL:** `https://www.googleapis.com/youtube/v3/search`
**Metodo:** `GET`
**Costo Quota:** 100 unità per chiamata.

---

## 1. Parametri di Input (Richiesta)

L'agente deve mappare le richieste dell'utente o dello script sui seguenti parametri API.

### Parametri Fondamentali
* **`key`** (string): API Key di Google (da variabili d'ambiente).
* **`channelId`** (string): L'ID del canale su cui effettuare la ricerca.
* **`part`** (string): Deve essere sempre impostato su `"snippet,id"`.

### Parametri di Filtro e Ordinamento (Configurabili)
* **`publishedAfter`** (string, opzionale): Filtra i risultati per includere solo video creati dopo una specifica data.
    * Formato richiesto: RFC 3339 (es. `2024-01-01T00:00:00Z`).
* **`order`** (string, opzionale): Specifica il metodo di ordinamento delle risorse.
    * Valori accettati: `"date"` (consigliato per nuovi video), `"viewCount"`, `"relevance"`.
* **`maxResults`** (integer, opzionale): Il numero massimo di elementi da restituire (default 5, max 50).
* **`type`** (string): Impostare su `"video"` per escludere playlist e canali dai risultati.

---

## 2. Struttura Output (Interpretazione JSON)

La risposta è un oggetto JSON contenente metadati e una lista di item.

### Campi Chiave da Estrarre
1.  **`items`** (Array): La lista dei risultati.
2.  All'interno di ogni oggetto in `items`:
    * **`id.videoId`** (string): L'identificativo univoco del video (necessario per scaricare poi la trascrizione).
    * **`snippet.title`** (string): Il titolo del video.
    * **`snippet.publishedAt`** (string): La data e ora esatta di pubblicazione.
    * **`snippet.description`** (string): Breve descrizione del video.

---

## 3. Istruzioni Operative

1.  **Formato Data:** Se l'input contiene una data, assicurati che sia convertita rigorosamente nel formato RFC 3339 prima di passarla al parametro `publishedAfter`.
2.  **Mapping Parametri:**
    * Se la richiesta è "cerca gli ultimi video", imposta `order="date"`.
    * Se la richiesta specifica un limite (es. "prendi 10 video"), mappa su `maxResults`.
3.  **Clean Output:** Restituisci allo script chiamante una lista pulita di oggetti contenenti solo `videoId` e `title`, scartando i metadati API non necessari (come `etag` o `kind`).

---

## 4. Esempio di Chiamata

**Input Logico:** "Dammi i video del canale `UC_EXAMPLE` dal 15 Agosto 2024, ordinati per data."

**Configurazione Parametri API:**
```json
{
  "part": "snippet,id",
  "channelId": "UC_EXAMPLE",
  "order": "date",
  "type": "video",
  "publishedAfter": "2024-08-15T00:00:00Z"
}