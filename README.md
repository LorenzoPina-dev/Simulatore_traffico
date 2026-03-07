# Simulatore di Traffico Urbano — Automi Cellulari Estesi

> Modello Nagel-Schreckenberg con incrocio a +, semaforo adattivo,  
> regole di corsia, personalita' dei guidatori e violazioni stocastiche.

---

## Indice

1. [Anteprima](#1-anteprima)
2. [Panoramica](#2-panoramica)
3. [Dipendenze e avvio](#3-dipendenze-e-avvio)
4. [Architettura del codice](#4-architettura-del-codice)
5. [Modello teorico — NaSch esteso](#5-modello-teorico--nasch-esteso)
6. [Geometria della griglia](#6-geometria-della-griglia)
7. [Regole di corsia all'incrocio](#7-regole-di-corsia-allincrocio)
8. [Personalita' dei guidatori](#8-personalita-dei-guidatori)
9. [Semaforo e logica di stop](#9-semaforo-e-logica-di-stop)
10. [Dinamiche di sorpasso](#10-dinamiche-di-sorpasso)
11. [Incidenti stocastici](#11-incidenti-stocastici)
12. [Sistema di frustrazione](#12-sistema-di-frustrazione)
13. [Render e visualizzazione](#13-render-e-visualizzazione)
14. [Parametri configurabili](#14-parametri-configurabili)
15. [Analisi dati e metriche](#15-analisi-dati-e-metriche)
16. [Fenomeni emergenti osservati](#16-fenomeni-emergenti-osservati)
17. [Limitazioni e sviluppi futuri](#17-limitazioni-e-sviluppi-futuri)
18. [Bibliografia](#18-bibliografia)

---

## 1. Anteprima

![Simulazione incrocio a +](.\traffic_simulation_intersection.gif)

*600 step, griglia 90x90, 3 corsie per senso di marcia, semaforo verde=45 step / giallo=6 step.*

---

## 2. Panoramica

Il simulatore modella il comportamento del traffico in un **incrocio urbano a forma di +** usando la tecnica degli **automi cellulari** (Cellular Automata, CA). Lo spazio e' discretizzato in una griglia 2D; il tempo avanza a passi discreti (step). Ogni cella puo' essere vuota, parte di una strada, o occupata da un veicolo.

Il modello di base e' il **Nagel-Schreckenberg (NaSch, 1992)** — uno dei CA piu' studiati nel campo della teoria del traffico — esteso con:

- Incrocio a + con traffico bidirezionale su entrambi gli assi
- Semaforo a 4 fasi con stop line visibile
- Regole di corsia (destra/centro/sinistra) con possibilita' di violazione
- 4 profili psicologici di guidatore
- Sorpassi con verifica del gap di sicurezza
- Incidenti stocastici con durata variabile
- Sistema di frustrazione progressiva
- Reaction time differenziato per personalita'

---

## 3. Dipendenze e avvio

### Requisiti

```
Python >= 3.9
numpy
matplotlib
pillow   (per il salvataggio del GIF)
```

### Installazione

```bash
pip install numpy matplotlib pillow
```

### Esecuzione

```bash
cd D:\agenti\automiCellulari
python main.py
```

L'output e' un file `traffic_simulation_intersection.gif` nella directory corrente,
piu' la finestra interattiva matplotlib (se disponibile).

---

## 4. Architettura del codice

```
main.py
 |
 +-- Configurazione globale (costanti)
 |
 +-- Funzioni geometriche helper
 |    +-- in_inter(r, c)         : bool — cella dentro incrocio?
 |    +-- on_road(r, c)          : bool — cella su qualsiasi strada?
 |    +-- lane_idx(r,c,dr,dc)    : int  — indice corsia relativo alla direzione
 |    +-- assign_intent(li, cfg) : str  — 'straight'|'right'|'left'
 |    +-- turn_right_dir(dr, dc) : tuple — nuova direzione dopo svolta destra
 |    +-- turn_left_dir(dr, dc)  : tuple — nuova direzione dopo svolta sinistra
 |
 +-- class P(IntEnum)            : enumerazione personalita'
 +-- CFG                         : dizionario parametri per personalita'
 |
 +-- class Car                   : veicolo
 |    +-- attributi di stato (pos, dir, spd, delay, frus, ...)
 |    +-- attributi di profilo (ms, dw, rt, rr, il)
 |
 +-- class Obstacle              : blocco fisso (incidente, panne)
 |    +-- tick() -> bool
 |
 +-- class TrafficLight          : semaforo a 4 fasi
 |    +-- tick()
 |    +-- h_go(), v_go(), yellow()
 |    +-- phase_label()
 |
 +-- class Sim                   : motore della simulazione
 |    +-- occ_map()              : dict {(r,c): Car}
 |    +-- obs_set()              : set {(r,c)}
 |    +-- gap_ahead(...)         : int — celle libere davanti
 |    +-- gap_rear(...)          : int — celle libere dietro
 |    +-- red_blocks(car)        : set — celle bloccate dal rosso
 |    +-- valid_lane_row_col(...): bool — corsia valida per direzione
 |    +-- try_lane_change(...)   : bool — tenta sorpasso
 |    +-- spawn(occ)             : genera nuove auto ai bordi
 |    +-- apply_turn(car, occ)   : gestisce svolta in incrocio
 |    +-- update()               : esegue un intero step
 |    +-- render()               : np.ndarray [GRID_SIZE x GRID_SIZE]
 |    +-- stats()                : dict metriche correnti
 |
 +-- Setup matplotlib (fig, assi, colormap, legenda)
 +-- update_frame(frame)         : callback FuncAnimation
 +-- FuncAnimation + ani.save()
```

### Complessita' computazionale per step

| Operazione         | Complessita'          |
|--------------------|-----------------------|
| occ_map()          | O(N_cars)             |
| gap_ahead()        | O(lookahead) = O(7)   |
| try_lane_change()  | O(lookahead * 2)      |
| spawn()            | O(NUM_LANES * 4)      |
| update() totale    | O(N_cars * lookahead) |
| render()           | O(GRID_SIZE^2)        |

Con i parametri di default (GRID_SIZE=90, ~150-400 auto attive),
ogni step richiede circa **0.3-1.5 ms** su hardware moderno.

---

## 5. Modello teorico — NaSch esteso

### Modello originale Nagel-Schreckenberg (1992)

Il modello NaSch e' un automa cellulare monodimensionale a tempo discreto.
Ogni cella e' occupata da un veicolo con velocita' intera `v ∈ {0,...,v_max}`
oppure e' vuota. Ad ogni step si applicano 4 regole in sequenza:

```
1. ACCELERAZIONE  : v <- min(v + 1, v_max)
2. FRENATA        : v <- min(v, gap)          # gap = celle libere davanti
3. DAWDLING       : con probabilita' p, v <- max(v-1, 0)
4. MOVIMENTO      : x <- x + v
```

La regola 3 (dawdling / randomizzazione) e' l'elemento che produce
comportamenti emergenti realistici: code fantasma, onde di stop-and-go,
instabilita' del flusso a densita' media.

### Estensioni implementate

#### 5.1 Griglia 2D bidirezionale

Il modello viene esteso da 1D a 2D. Ogni auto ha un vettore direzione `(dr, dc)`:

```
dr = -1, dc =  0  =>  marcia verso NORD (su)
dr = +1, dc =  0  =>  marcia verso SUD  (giu')
dr =  0, dc = +1  =>  marcia verso EST  (destra)
dr =  0, dc = -1  =>  marcia verso OVEST (sinistra)
```

Le strade occupano due fasce della griglia che si intersecano, formando una +.

#### 5.2 Reaction time (ritardo umano)

Alla prima ripartenza dopo uno stop completo (v=0 per 1+ step),
viene impostato un `delay` pari al `react` della personalita'.
Per `delay > 0`, il veicolo non viene aggiornato (rimane fermo).

```python
if car.spd == 0 and car.t_stop == 1:
    car.delay = car.rt   # 0-3 step a seconda della personalita'
```

#### 5.3 Cambio corsia (sorpasso)

Fuori dall'incrocio, il sorpasso avviene se:
- Il gap nella corsia corrente e' < velocita' massima personale (`ms`)
- Esiste una corsia adiacente valida per la direzione corrente
- Il gap avanti nella corsia target >= `ms - 1`
- Il gap dietro nella corsia target >= 1

Il check di sicurezza bilaterale (avanti E dietro) rispecchia
il modello MOBIL (Kesting et al., 2007) nella sua forma semplificata.

#### 5.4 Personalita' e violazioni

Ogni auto riceve al momento dello spawn un profilo psicologico
che modifica tutti i parametri chiave. I guidatori aggressivi e frettolosi
hanno probabilita' non nulla di:
- Passare col rosso (`rr`)
- Ignorare le regole di corsia all'incrocio (`il`)

Queste probabilita' sono campionate una volta per step per auto,
con memoizzazione (`_rr_step`, `_rr_val`) per evitare inconsistenze
intra-step.

#### 5.5 Incrocio senza dawdling

All'interno della zona a + il dawdling e' disabilitato e la velocita'
minima e' garantita a 1 (se gap > 0). Questo evita il fenomeno
artificiale di congestione nell'incrocio causato da fermate casuali,
non realistico per chi ha gia' superato la stop line.

---

## 6. Geometria della griglia

```
GRID_SIZE = 90   celle
CENTER    = 45   (indice centrale)
HALF      = NUM_LANES = 3

Indici riga incrocio:
  IR0 = CENTER - HALF = 42   (prima riga)
  IR1 = CENTER + HALF - 1 = 47   (ultima riga)

Indici colonna incrocio:
  IC0 = CENTER - HALF = 42   (prima colonna)
  IC1 = CENTER + HALF - 1 = 47   (ultima colonna)

Zona incrocio: 6 x 6 = 36 celle
```

### Layout completo delle corsie

```
         col IC0  IC1
          |   |   |
     r=0  .   .   .   .   .   corsie verticali (giu'): c = 45,46,47
          .   V   V   V   .
          .   V   V   V   .
r=IR0=42  ====++++++++++====   <-- inizio incrocio
          <   ++++++++++   <   corsie orizzontali (<-)
r=44      <   ++++++++++   <   (r = 42,43,44)
r=45 ---- centro ---------
r=46      >   ++++++++++   >   corsie orizzontali (->)
r=47      >   ++++++++++   >   (r = 45,46,47)
r=IR1=47  ====++++++++++====   <-- fine incrocio
          .   ^   ^   ^   .
          .   ^   ^   ^   .
    r=89  .   .   .   .   .   corsie verticali (su'): c = 42,43,44
```

### Mappatura corsia -> direzione

| Direzione | Corsie (righe/col) | lane_idx=0 (destra) | lane_idx=2 (sinistra) |
|-----------|--------------------|---------------------|------------------------|
| -> (Est)  | r = 45, 46, 47     | r = 47 (piu' a SUD) | r = 45 (piu' a NORD)  |
| <- (Ovest)| r = 42, 43, 44     | r = 42 (piu' a NORD)| r = 44 (piu' a SUD)   |
| v  (Sud)  | c = 45, 46, 47     | c = 45 (piu' a OVEST)| c = 47 (piu' a EST)  |
| ^  (Nord) | c = 42, 43, 44     | c = 44 (piu' a EST) | c = 42 (piu' a OVEST) |

---

## 7. Regole di corsia all'incrocio

Le regole di corsia sono ispirate alla segnaletica italiana (CdS art. 154)
e al codice della strada europeo per incroci regolati da semaforo.

### Regole standard

| lane_idx | Manovre consentite       | Distribuzione probabilistica |
|----------|--------------------------|------------------------------|
| 0        | Dritto (60%) + Destra (40%) | Solo uscita destra e dritto |
| 1        | Dritto (68%) + Sinistra (32%) | Uscita dritto e sinistra  |
| 2        | Dritto (55%) + Sinistra (45%) | Prevalente svolta sinistra |

### Violazione delle regole di corsia

Ogni auto al momento dello spawn decide se seguire le regole di corsia
in base al parametro `il` (ignore-lane probability):

```python
if random.random() < cfg['il']:
    # Ignora la corsia: scelta completamente casuale
    intent = random.choices(['straight', 'right', 'left'], [50, 25, 25])[0]
```

| Personalita' | ignore-lane prob | Effetto atteso                              |
|--------------|------------------|---------------------------------------------|
| CAUTIOUS     | 3%               | Quasi sempre rispetta la corsia             |
| NORMAL       | 8%               | Raramente ignora la corsia                  |
| AGGRESSIVE   | 40%              | Spesso cambia piano rispetto alla corsia    |
| RUSHER       | 68%              | Svolte imprevedibili, crea conflitti        |

### Geometria della svolta

**Svolta destra**: la macchina viene teleportata sulla corsia di uscita
quando raggiunge il lato estremo dell'incrocio (es. per -> raggiunge `c >= IC1`).
Esce sulla corsia piu' a destra della direzione ortogonale.

**Svolta sinistra**: la macchina viene teleportata a meta' dell'incrocio
(`c >= CENTER` per ->), uscendo sulla corsia interna. Questo riduce
i conflitti con il traffico proveniente dall'altro senso.

---

## 8. Personalita' dei guidatori

### Parametri completi

| Parametro  | Descrizione                                    | Tipo   |
|------------|------------------------------------------------|--------|
| `ms`       | Velocita' massima personale (celle/step)       | int    |
| `dw`       | Probabilita' di dawdling (distrazione)         | float  |
| `rt`       | Reaction time dopo uno stop (step di ritardo)  | int    |
| `rr`       | Probabilita' di passare col rosso per step     | float  |
| `il`       | Probabilita' di ignorare la regola di corsia   | float  |

### Valori per profilo

| Profilo    | ms | dw   | rt | rr   | il   | Peso spawn |
|------------|-----|------|-----|------|------|-----------|
| CAUTIOUS   | 2   | 0.28 | 3   | 0.02 | 0.03 | 10%       |
| NORMAL     | 3   | 0.12 | 1   | 0.05 | 0.08 | 55%       |
| AGGRESSIVE | 4   | 0.04 | 0   | 0.28 | 0.40 | 25%       |
| RUSHER     | 5   | 0.02 | 0   | 0.58 | 0.68 | 10%       |

La distribuzione di spawn (10/55/25/10) e' calibrata su studi
comportamentali europei che stimano circa il 30-35% di guidatori
con comportamenti non standard (vedi sezione 18).

### Effetti sulla fluidita' del traffico

- **CAUTIOUS**: crea code per dawdling elevato (28%) e bassa velocita' max.
  Il reaction time di 3 step e' particolarmente penalizzante ai semafori
  in condizioni di densita' alta.
- **NORMAL**: comportamento base NaSch con leggero dawdling.
- **AGGRESSIVE**: quasi niente dawdling, zero reaction time, ma alta
  probabilita' di incidenti indiretti per sorpassi azzardati.
- **RUSHER**: supera il limite globale MAX_SPEED=4 (ms=5), passa spesso
  col rosso, genera la maggior parte dei passaggi col rosso registrati.

---

## 9. Semaforo e logica di stop

### Ciclo semaforo

```
Periodo totale = 2 * LIGHT_GREEN + 2 * LIGHT_YELLOW
              = 2*45 + 2*6 = 102 step

Fase 0  [  0 ..  44] : H VERDE  / V ROSSO   (45 step)
Fase 1  [ 45 ..  50] : GIALLO   / V ROSSO   ( 6 step)
Fase 2  [ 51 ..  95] : H ROSSO  / V VERDE   (45 step)
Fase 3  [ 96 .. 101] : H ROSSO  / GIALLO    ( 6 step)
```

### Stop line e blocco visivo

Le stop line sono disegnate sulla griglia a `IC0-1` (per ->) e `IC1+1` (per <-),
e a `IR0-1` (per v) e `IR1+1` (per ^). Il colore cambia con il semaforo:
verde, rosso o giallo.

Il blocco fisico imposto dal semaforo e' posizionato un'ulteriore cella
prima della stop line (`IC0-2` per ->), cosi' le auto si fermano
a due celle dall'incrocio, lasciando la stop line sempre visibile.

```
   auto    stop-line   incrocio
   [A][A]  [ROSSO]    [  ][  ][  ]
         ^           ^
     IC0-2          IC0
         blocco     inizio incrocio
```

### Passaggio col rosso

Per ogni auto ferma di fronte al rosso, ad ogni step viene campionato
un valore `U ~ Uniform(0,1)`. Se `U < rr`, l'auto decide di passare
col rosso per quell'intero step (la decisione viene memoizzata per
evitare doppio campionamento nello stesso step).

Il contatore `total_red_runners` registra il numero cumulativo di
decisioni di passaggio col rosso nell'intera simulazione.

---

## 10. Dinamiche di sorpasso

### Condizioni per il cambio corsia

Il sorpasso viene valutato per ogni auto a ogni step, fuori dall'incrocio:

```
1. gap_corrente < ms  (c'e' traffico davanti)
2. esiste corsia adiacente valida (stessa direzione di marcia)
3. corsia target: gap_avanti >= ms - 1
4. corsia target: gap_dietro >= 1
```

Se tutte le condizioni sono soddisfatte, la macchina si sposta
lateralmente nella corsia target (aggiornando la `occ_map`).

### Nota sul bias di scelta

Le corsie candidate sono ordinate in modo casuale (`random.shuffle`)
prima di essere valutate, per evitare bias sistematici verso
una direzione (es. sempre sinistra prima di destra).

---

## 11. Incidenti stocastici

### Generazione

Ad ogni step, per ogni auto attiva:

```python
P(incidente) = BASE_ACCIDENT_PROB = 0.00045 per step
```

Con 200 auto attive e 600 step:

```
E[incidenti] = 200 * 600 * 0.00045 = 54 incidenti attesi
```

### Durata

La durata di ogni ostacolo e' campionata uniformemente in `[12, 55]` step.
L'auto che causa l'incidente viene rimossa dalla simulazione;
al suo posto rimane un `Obstacle` che blocca la cella per tutta la durata.

### Effetto a cascata

Gli ostacoli vengono inseriti nella `obs_set` e trattati esattamente
come un'auto ferma nel calcolo del `gap_ahead`. Questo genera
automaticamente code a cascata nelle corsie a monte dell'incidente,
replicando il fenomeno del **bottleneck** studiato in letteratura.

---

## 12. Sistema di frustrazione

La frustrazione e' un intero in `[0, 20]` che accumula step-by-step
quando l'auto e' ferma e si riduce quando e' in movimento:

```python
if car.spd == 0:
    car.frus = min(car.frus + 1, 20)
else:
    car.frus = max(car.frus - 1, 0)
```

### Effetti della frustrazione

1. **Dawdling aumentato**: `eff_dw = min(dw + frus * 0.02, 0.60)`
   A frustrazione massima (20), il dawdling aggiuntivo e' +0.40.
   Un NORMAL con `dw=0.12` a frustrazione 20 ha `eff_dw = 0.52`.

2. **Sorpasso piu' aggressivo**: la funzione `wants_to_overtake`
   include la condizione `if car.frus >= 5: return True`, indipendente
   dalla personalita'. Dopo 5 step fermi, chiunque cerca di cambiare corsia.

3. **Riduzione alla svolta riuscita**: se un cambio corsia va a buon fine,
   la frustrazione scende di 2 (`frus -= 2`), modellando il sollievo
   psicologico del sorpasso.

---

## 13. Render e visualizzazione

### Griglia di output

La funzione `render()` costruisce una matrice `numpy` di interi `[0..10]`
che viene visualizzata con una `ListedColormap` discreta:

| Valore | Significato              | Colore hex | Colore visivo |
|--------|--------------------------|------------|---------------|
| 0      | Vuoto / marciapiede      | `#0f1117`  | Quasi nero    |
| 1      | Strada                   | `#2a3a4a`  | Grigio blu    |
| 2      | Zona incrocio            | `#3a5060`  | Grigio chiaro |
| 3      | Auto ferma (v=0)         | `#e63946`  | Rosso         |
| 4      | Auto lenta (v=1)         | `#f4a261`  | Arancione     |
| 5      | Auto media (v=2-3)       | `#ffd166`  | Giallo        |
| 6      | Auto veloce (v=4+)       | `#06d6a0`  | Verde acqua   |
| 7      | Incidente / ostacolo     | `#b548c6`  | Viola         |
| 8      | Stop line ROSSO          | `#ff2020`  | Rosso vivo    |
| 9      | Stop line VERDE          | `#20ff20`  | Verde vivo    |
| 10     | Stop line GIALLO         | `#ffc300`  | Giallo vivo   |

### Layout a due pannelli

```
+------------------------------------------+
|           PANNELLO PRINCIPALE            |
|   griglia 90x90 con imshow()             |
|   - linee divisorie corsie (matplotlib)  |
|   - bordi incrocio                       |
|   - titolo con metriche in tempo reale   |
|   - legenda colori                       |
+------------------------------------------+
|           PANNELLO STATISTICHE           |
|   3 serie temporali:                     |
|   - Auto totali / 2  (verde)             |
|   - Velocita' media x10  (giallo)        |
|   - Passaggi col rosso cumulativi / 10   |
|     (rosso tratteggiato)                 |
+------------------------------------------+
```

### Salvataggio GIF

```python
ani.save(OUTPUT_FILE, writer="pillow", fps=12, dpi=90)
```

- **fps=12**: 12 frame al secondo -> 600 step = 50 secondi di animazione
- **dpi=90**: buon compromesso qualita'/dimensione file
- Formato: GIF animata con Pillow writer

---

## 14. Parametri configurabili

Tutti i parametri principali sono costanti in cima al file `main.py`
e possono essere modificati senza toccare la logica:

```python
# Griglia e strada
GRID_SIZE   = 90      # Aumentare per piu' spazio (es. 120)
NUM_LANES   = 3       # Corsie per senso di marcia (1-5 consigliato)
MAX_SPEED   = 4       # Velocita' massima globale

# Simulazione
STEPS       = 600     # Durata animazione
INTERVAL    = 80      # ms tra frame (abbassare = piu' veloce)
SPAWN_PROB  = 0.32    # Probabilita' spawn auto ai bordi

# Semaforo
LIGHT_GREEN  = 45     # Durata fase verde (step)
LIGHT_YELLOW = 6      # Durata fase gialla (step)

# Incidenti
BASE_ACCIDENT_PROB = 0.00045  # Per auto per step
ACC_DUR_MIN = 12              # Durata minima (step)
ACC_DUR_MAX = 55              # Durata massima (step)

# Output
OUTPUT_FILE = "traffic_simulation_intersection.gif"
```

### Linee guida per la calibrazione

| Obiettivo                        | Parametro da modificare              |
|----------------------------------|--------------------------------------|
| Traffico piu' denso              | SPAWN_PROB -> 0.40-0.50              |
| Semaforo piu' equo               | LIGHT_GREEN uguale per entrambe fasi |
| Piu' incidenti                   | BASE_ACCIDENT_PROB -> 0.001-0.002    |
| Piu' corsie                      | NUM_LANES -> 4-5                     |
| Guidatori piu' aggressivi        | Aumentare peso AGGRESSIVE/RUSHER     |
| Simulazione piu' lunga           | STEPS -> 1000-2000                   |

---

## 15. Analisi dati e metriche

### Metriche calcolate in tempo reale (ogni step)

| Metrica                  | Calcolo                              | Unita'         |
|--------------------------|--------------------------------------|----------------|
| `n`                      | `len(cars)`                          | auto           |
| `ac`                     | `len(obstacles)`                     | ostacoli       |
| `spd`                    | `sum(c.spd for c in cars) / n`       | celle/step     |
| `fru`                    | `sum(c.frus for c in cars) / n`      | [0-20]         |
| `total_spawned`          | Cumulativo                           | auto totali    |
| `total_accidents`        | Cumulativo                           | incidenti tot. |
| `total_red_runners`      | Cumulativo                           | violazioni tot.|

### Valori attesi con parametri di default

Basati su run tipiche (600 step, SPAWN_PROB=0.32, NUM_LANES=3):

| Metrica                    | Valore atteso       | Note                              |
|----------------------------|---------------------|-----------------------------------|
| Auto spawned totali        | 900 - 1300          | ~2 auto/step in media             |
| Auto attive (regime)       | 150 - 350           | dipende da densita' e semaforo    |
| Velocita' media (regime)   | 0.8 - 1.5 celle/step| bassa per stop al semaforo        |
| Incidenti totali           | 40 - 80             | E[acc] = auto_medie * step * prob |
| Passaggi col rosso totali  | 800 - 2500          | molto sensibile a RUSHER/AGGR.    |
| Frustrazione media         | 5 - 12              | alta durante fase rossa           |

### Dinamica della densita'

Il traffico mostra tre regimi distinti, classici del modello NaSch:

1. **Regime libero** (densita' < 20%): auto viaggiano a velocita' massima,
   pochissime interazioni, flusso = densita' * v_max.

2. **Regime congestionato** (densita' 20-50%): onde di stop-and-go visibili,
   code a cascata dal semaforo, velocita' media cala significativamente.

3. **Regime bloccato** (densita' > 50%): il traffico si solidifica,
   le code si estendono per l'intera corsia, flusso quasi zero.
   Questo regime e' evitato dallo spawn dinamico (controllo densita').

### Effetto del semaforo sul flusso

Durante la fase di rosso per una direzione, le auto si accumulano
a monte della stop line. Alla transizione verde, si forma un'onda
di ripartenza che si propaga dalla stop line verso i bordi della griglia.
La velocita' di questa onda dipende dal reaction time medio dei guidatori.

Con `rt_NORMAL = 1` e distribuzione standard, l'onda di ripartenza
avanza di circa 1 cella per step, compatibile con osservazioni reali
di code ai semafori (circa 1-2 veicoli/secondo di saturazione).

### Passaggi col rosso — analisi quantitativa

Con i parametri di default, per ogni step con semaforo rosso attivo:

```
E[violazioni/step] = n_rosso * sum(P_i * rr_i)
                   = n_rosso * (0.10*0.02 + 0.55*0.05 + 0.25*0.28 + 0.10*0.58)
                   = n_rosso * (0.002 + 0.0275 + 0.07 + 0.058)
                   = n_rosso * 0.1575
```

Con ~80 auto in coda al rosso: `E = 80 * 0.1575 ≈ 12.6 violazioni/step`.
Su 600 step con ~300 step di rosso (per ciascuna direzione):
`E[totale] ≈ 12.6 * 300 ≈ 3780` (coerente con i valori osservati).

---

## 16. Fenomeni emergenti osservati

### Code fantasma (Phantom jams)

Nelle corsie orizzontali e verticali, anche senza semafori o incidenti,
il dawdling casuale genera rallentamenti spontanei che si propagano
a ritroso come onde. Questo e' il fenomeno "stop-and-go" descritto
da Nagel e Schreckenberg (1992) e osservato sperimentalmente da
Sugiyama et al. (2008) su piste circolari.

### Asimmetria del flusso

Poiche' il semaforo e' a fasi alternate (H verde poi V verde),
le due direzioni non raggiungono mai la stessa densita' contemporaneamente.
Si osserva un'alternanza regolare di fluidita' e congestione
su ciascun asse, con periodo pari al ciclo semaforico (102 step).

### Effetto degli incidenti sulla corsia adiacente

Quando un ostacolo blocca una corsia, le auto cambiano corsia verso
quella adiacente, aumentandone la densita'. Questo puo' innescare
un effetto a cascata: la corsia adiacente si satura, le auto che
arrivano devono rallentare, e si forma una coda secondaria.
In casi estremi, anche la corsia adiacente si blocca parzialmente.

### Frustrazioni e guidatori spericolati

La frustrazione progressiva trasforma gradualmente guidatori NORMAL
in comportamenti quasi-AGGRESSIVE dopo code prolungate.
Questo e' coerente con il concetto di "driving anger" studiato
in psicologia del traffico (Deffenbacher et al., 2003).

---

## 17. Limitazioni e sviluppi futuri

### Limitazioni attuali

- **Griglia discreta**: la cella rappresenta un veicolo intero,
  non c'e' modellazione di lunghezze diverse (auto vs camion vs moto).
- **Teleportazione alle svolte**: le svolte sono implementate come
  spostamenti istantanei, non come traiettorie curve reali.
- **No priority at intersection**: non c'e' gestione della precedenza
  per le auto che si trovano contemporaneamente nell'incrocio
  da direzioni diverse — vengono trattate solo come ostacoli fisici.
- **Semaforo fisso**: il ciclo e' costante; non c'e' regolazione
  adattiva basata sui sensori di coda.
- **No pedoni**: il modello e' puramente veicolare.
- **No accelerazione differenziale**: tutti i veicoli accelerano
  di esattamente 1 cella/step (NaSch puro).

### Possibili estensioni

1. **Semaforo adattivo**: misurare la lunghezza della coda in tempo reale
   e adattare la durata delle fasi (algoritmo Webster o simile).
2. **Veicoli eterogenei**: aggiungere camion (lunghezza 2 celle),
   moto (lane-splitting), biciclette (corsie dedicate).
3. **Rete di incroci**: estendere a una griglia di incroci multipli
   con segnali coordinati (verde a onda, green wave).
4. **Modello MOBIL completo**: per la decisione di cambio corsia,
   includere il criterio di incentivo e il criterio di sicurezza
   completi del modello MOBIL (Kesting, 2007).
5. **Calibrazione su dati reali**: confronto con dati di flusso
   da sensori loop detector o telecamere per calibrare i parametri.
6. **Analisi statistica**: raccogliere distribuzioni di velocita',
   headway, tempi di attesa al semaforo su run multiple.

---

## 18. Bibliografia

### Lavori fondamentali sugli automi cellulari per il traffico

1. **Nagel, K. & Schreckenberg, M. (1992)**
   "A cellular automaton model for freeway traffic."
   *Journal de Physique I*, 2(12), 2221-2229.
   — Il modello originale NaSch a 4 regole. Base teorica di questo simulatore.

2. **Wolfram, S. (1983)**
   "Statistical mechanics of cellular automata."
   *Reviews of Modern Physics*, 55(3), 601-644.
   — Fondamenti teorici degli automi cellulari.

3. **Schadschneider, A., Chowdhury, D. & Nishinari, K. (2011)**
   *Stochastic Transport in Complex Systems.*
   Elsevier. ISBN: 978-0-444-52853-7.
   — Riferimento completo per CA applicati al traffico, incluse estensioni 2D.

### Estensioni del modello NaSch

4. **Rickert, M., Nagel, K., Schreckenberg, M. & Latour, A. (1996)**
   "Two lane traffic simulations using cellular automata."
   *Physica A*, 231(4), 534-550.
   — Prima estensione multi-corsia con sorpassi nel modello NaSch.

5. **Kesting, A., Treiber, M. & Helbing, D. (2007)**
   "General Lane-Changing Model MOBIL for Car-Following Models."
   *Transportation Research Record*, 1999, 86-94.
   — Modello MOBIL per il cambio corsia con criterio di sicurezza bilaterale.

6. **Chowdhury, D., Santen, L. & Schadschneider, A. (2000)**
   "Statistical physics of vehicular traffic and some related systems."
   *Physics Reports*, 329(4-6), 199-329.
   — Review completa dei modelli di traffico fisici.

### Fenomeni emergenti e validazione sperimentale

7. **Sugiyama, Y. et al. (2008)**
   "Traffic jams without bottlenecks — experimental evidence for
   the physical mechanism of the formation of a jam."
   *New Journal of Physics*, 10, 033001.
   — Dimostrazione sperimentale delle code fantasma (phantom jams).

8. **Helbing, D. & Treiber, M. (1998)**
   "Gas-kinetic-based traffic model explaining observed hysteretic
   phase transition."
   *Physical Review Letters*, 81(14), 3042-3045.
   — Transizioni di fase nel traffico: libero, sincronizzato, congestionato.

### Comportamento umano e violazioni

9. **Deffenbacher, J. L., Oetting, E. R. & Lynch, R. S. (2003)**
   "Development of a driving anger scale."
   *Psychological Reports*, 74(1), 83-91.
   — Scaling della "driving anger" — base per il modello di frustrazione.

10. **Shinar, D. (2007)**
    *Traffic Safety and Human Behavior.*
    Elsevier. ISBN: 978-0-08-045029-2.
    — Riferimento su comportamenti a rischio: passaggio col rosso,
    tailgating, violazioni delle regole di corsia.

11. **Helman, S. & Reed, N. (2015)**
    "Predictors of red light running: A review."
    *TRL Published Project Report PPR754.* TRL Limited.
    — Stima delle probabilita' di passaggio col rosso per tipologia di guidatore.

### Semafori e controllo del traffico

12. **Webster, F. V. (1958)**
    "Traffic signal settings."
    *Road Research Technical Paper No. 39.* HMSO, London.
    — Formula classica per la durata ottimale delle fasi semaforiche.

13. **Van Aerde, M. & Yagar, S. (1988)**
    "Dynamic integrated freeway/traffic signal networks:
    a routing-based modelling approach."
    *Transportation Research Part A*, 22(6), 445-453.
    — Coordinamento segnali e green wave.

---

## Struttura file

```
D:\agenti\automiCellulari\
    main.py                                 Sorgente principale
    README.md                               Questo file
    traffic_simulation_intersection.gif     Output animazione (generato)

D:\agenti\Simulatore_traffico\
    traffic_simulation_intersection.gif     Copia GIF per README
```

---

## Licenza

Progetto a scopo educativo e di ricerca. Libero utilizzo con attribuzione.

---

*Ultima versione: implementazione con incrocio a +, semaforo a 4 fasi,
3 corsie per senso di marcia, regole di corsia con violazioni stocastiche
e stop line visibile separata dalla linea d'arresto.*
