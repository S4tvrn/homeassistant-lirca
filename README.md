# Home Assistant - LIRCA

Integrazione custom per Home Assistant che legge le letture dei contatori
calore/acqua dal portale clienti [LIRCA](https://utenti.lirca.it) e le espone
come sensori.

## Installazione

### Tramite HACS (repository custom)
1. HACS → Integrazioni → menu (⋮) → **Repository personalizzati**
2. Aggiungi `https://github.com/S4tvrn/homeassistant-lirca`, tipo **Integrazione**
3. Cerca "LIRCA" e installa
4. Riavvia Home Assistant

### Manuale
1. Copia la cartella `custom_components/lirca` dentro `config/custom_components/`
2. Riavvia Home Assistant

## Configurazione

**Impostazioni → Dispositivi e servizi → Aggiungi integrazione** → cerca **LIRCA**,
inserisci email e password del portale clienti.

Viene creato un sensore per ogni contatore trovato, con l'ultima lettura disponibile
e la relativa data.

## Note

- Polling ogni 6 ore (il portale non aggiorna i dati in tempo reale)
- Integrazione non ufficiale, non affiliata a LIRCA S.r.l.
- Basata sull'analisi del traffico del portale web; potrebbe smettere di
  funzionare se LIRCA modifica la struttura del sito

## Licenza

MIT
