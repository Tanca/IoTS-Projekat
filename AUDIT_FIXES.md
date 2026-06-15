# Metodologija i validacija merenja (REST vs GraphQL vs gRPC)

Student: Nikola Tancic 19425 — Internet Stvari (IoT), Elektronski Fakultet, 2026.

Cilj ovog dokumenta je da pokaze da su sva tri protokola merena pod **istim, kontrolisanim uslovima**, tako da je poredjenje posteno i ponovljivo. Pre konacnih merenja sprovedena je revizija test-skripti i servisa, a sve uocene nejednakosti su ispravljene i dokumentovane ispod. Ovim je obezbedjeno da izmerene razlike poticu od samih protokola (i runtime-a), a ne od razlika u uslovima testiranja.

## 1. Uslovi koji su izjednaceni za sva tri protokola

- **Profil opterecenja:** `10 -> 100 -> 500 -> 0` virtuelnih korisnika, faze po 30 s, u svih 9 skripti.
- **Vreme razmisljanja (think-time):** jedan `sleep(0.1)` po iteraciji, identicno svuda.
- **Posao po iteraciji:** tacno jedan zahtev/poziv (bez skrivenih unutrasnjih petlji).
- **Konkurentnost ka bazi:** pul od 500 konekcija za REST, GraphQL i gRPC.
- **Tip polja u agregatu:** numericke vrednosti u sva tri protokola (bez mesanja string/broj).

## 2. Korekcije sprovedene radi postenog poredjenja

Tokom pripreme merenja uocene su i otklonjene sledece nejednakosti. Bez njih bi poredjenje bilo pristrasno, pa su konacne tabele generisane tek posle ovih ispravki.

### 2.1. REST Scenario A je radio samo na 10 VU (ostali do 500)
U `k6/scenario_a_rest.js` faze 100/500/ramp-down bile su zakomentarisane, pa je REST ingestija bila testirana na 10 VU tokom 30 s, dok su GraphQL i gRPC isli `10 -> 100 -> 500` kroz 2 minuta.
**Ispravka:** vracen pun profil `10/100/500/0`.

### 2.2. REST Scenario B je gadjao pogresnu putanju (404)
U `k6/scenario_b_rest.js` putanja je sadrzala gresku (`…/api/sensork6 -data/…`), pa je vracala 404 i nije pogadjala pravi endpoint.
**Ispravka:** putanja ispravljena na `/api/sensor-data/selective/M1?limit=1`.

### 2.3. gRPC k6 skripte su koristile anti-obrazac klijenta
Sve tri gRPC skripte otvarale su **novu konekciju u svakoj iteraciji** (uz `client.close()`) i imale skrivenu unutrasnju petlju od 50 serijskih poziva sa `sleep(0.05)`, dok su REST/GraphQL radili jedan zahtev po iteraciji. Otvaranje/zatvaranje konekcije po iteraciji i serijski fan-out vestacki obaraju propusnost gRPC-a.
**Ispravka:** konekcija se otvara **jednom po VU** (`if (__ITER === 0) client.connect(...)`), jedan poziv po iteraciji i `sleep(0.1)` — isti posao i think-time kao REST/GraphQL.

### 2.4. Asimetrija pulova konekcija ka bazi
gRPC je imao `ThreadedConnectionPool(1, 500)`, dok su REST i GraphQL koristili `new Pool()` bez `max`, sto pada na podrazumevanih **10** konekcija u node-postgres-u. Pod 100–500 VU Node servisi su bili ograniceni na 10 konekcija, pa su delovali sporije iskljucivo zbog manjeg pula.
**Ispravka:** postavljeno `max: 500` na oba Node pula (Postgres je startovan sa `max_connections=1000`, pa je bezbedno).

### 2.5. REST agregat je vracao brojeve kao stringove
REST agregatni upit nije kastovao `AVG(...)`/`COUNT(*)`, pa je PostgreSQL vracao `numeric`/`bigint` koji se serijalizuju kao stringovi, dok su GraphQL i gRPC kastovali u `::float`/`::int`.
**Ispravka:** dodati `::float`/`::int` kastovi u `rest/server.js` radi identicnog tipa odgovora.

### 2.6. Scenario B point-read je bio ~400x sporiji (pogresan indeks)
Selektivni upit `WHERE device_id=? ORDER BY timestamp DESC LIMIT N` trajao je ~365 ms jer je zaseban indeks po `(timestamp)` navodio planer da skenira celu tabelu (najnovije prvo) i filtrira po `device_id`. Posto su podaci svake stanice vremenski grupisani, taj indeks je bio stetan i nijedan scenario ga nije koristio (sva tri filtriraju po `device_id`).
**Ispravka:** uklonjen zaseban indeks po vremenu; zadrzan jedan kompozitni `(device_id, timestamp DESC)` u `db/init.sql`. Point-read je pao na ~0,1 ms i Scenario B je postao najbrzi (kako se i ocekuje). Pre merenja uklonjeni su i nakupljeni redovi ingestije, tako da baza odgovara `dataset.csv` (613392 redova / 9 stanica).

## 3. Provera (validate.py)

Skripta `validate.py` automatski proverava da gornji uslovi vaze:

```bash
python validate.py --static    # logicke provere postenosti, bez pokretanja sistema
python validate.py             # uz pokrenut Docker stack: provera parnosti medju
                               # protokolima (iste agregatne vrednosti, ispravni
                               # tipovi polja, izmerene velicine payload-a)
```

Staticke provere postenosti prolaze; parnost u izvrsavanju (REST == GraphQL agregati, numericki tipovi, velicine payload-a) potvrdjena je sa pokrenutim sistemom (vidi `validate_report.txt`).

## 4. Konacno stanje

1. `docker-compose up --build -d` (ili ponovna upotreba seedovanog `pgdata` volumena).
2. Svih 9 k6 scenarija pokrenuto kroz `python run_tests.py` (jedan dosledan prolaz, 100% uspeha), uz uzorkovanje `docker stats` za pik CPU/RAM.
3. `python validate.py` potvrdjuje da uslovi postenosti vaze.
4. Tabele rezultata u `README.md`, `final_report.md` i `projekat-iots.docx` popunjene su svezim, sada uporedivim brojevima. Sirova evidencija je u `results/` (9 `scenario_*.json`).
