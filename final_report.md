# Uporedni benchmark REST, GraphQL i gRPC protokola za prenos senzorskih podataka pod jednakim uslovima

Student: Nikola Tancic 19425 — Internet Stvari (IoT), Elektronski Fakultet, 2026.

Poredjenje REST, GraphQL i gRPC protokola nad istom PostgreSQL bazom, kroz tri IoT scenarija (ingestija, selektivno citanje, agregacija). Sva tri servisa se mere pod istim uslovima da bi poredjenje bilo posteno.

## Metodologija (ujednacena za sva tri protokola)

- Profil opterecenja: 10 -> 100 -> 500 virtuelnih korisnika, faze po 30 sekundi.
- Vreme izmedju zahteva: 0,1 s.
- Jedan zahtev po iteraciji (bez skrivenih unutrasnjih petlji).
- Jednak broj DB konekcija: 500 za REST, GraphQL i gRPC.
- Provera: `python validate.py` (staticki proverava da su uslovi isti, a uz pokrenut sistem proverava i da odgovori protokola daju iste vrednosti).

## 1. Velicina odgovora (payload) — IZMERENO (uzivo)

Mereno nad pokrenutim sistemom: za isti upit nad istim podacima (uredjaj M1) izmeren je tacan broj bajtova koji svaki servis vrati — duzina HTTP odgovora za REST/GraphQL, tacan Protobuf `ByteSize` za gRPC.

Odgovor servera po scenariju:

| Scenario | REST (JSON) | GraphQL (JSON) | gRPC (Protobuf) |
| :--- | :---: | :---: | :---: |
| A — Ingestion (ACK odgovor) | 53 B | 47 B | 18 B |
| B — Selective (1 zapis) | 149 B | 89 B | 39 B |
| C — Aggregate (1 uredjaj) | 149 B | 181 B | 30 B |

Zahtev pri ingestiji (isti logicki zapis, kanonske vrednosti):

| Ingestija — zahtev | REST (JSON) | GraphQL (JSON) | gRPC (Protobuf) |
| :--- | :---: | :---: | :---: |
| Telo zahteva | 147 B | 540 B | 61 B |

Zapazanja:
- gRPC (binarni Protobuf) ima najmanji payload u svim scenarijima jer ne salje nazive polja ni separatore.
- Scenario B: REST koristi `SELECT *` i vraca svih 8 kolona (over-fetching) = 149 B, dok GraphQL (89 B) i gRPC (39 B) salju samo 3 trazena polja.
- Scenario C: pravi agregat vraca brojeve u punoj preciznosti (npr. `avg_air_temp = 11,678116179460275`), pa JSON raste (REST 149 B, GraphQL 181 B zbog `data` omotaca i naziva polja). Protobuf float je fiksno 4 B, pa je gRPC odgovor samo 30 B.
- Ingestija: GraphQL zahtev je najveci (540 B) jer u telo ukljucuje ceo tekst mutacije; gRPC je najmanji (61 B).
- Napomena: gRPC broj je velicina Protobuf poruke; na zici se dodaje jos 5 B gRPC okvira po poruci + HTTP/2 zaglavlja (HPACK kompresovana).

## 2. Latencija i propusnost (k6) — IZMERENO

Mereno k6 alatom, profil 10 -> 100 -> 500 VU (faze po 30 s), `sleep(0.1)` po iteraciji, jedan zahtev po iteraciji, identicno za sva tri protokola. Za REST/GraphQL metrika je `http_req_duration`, za gRPC `grpc_req_duration`. Svi testovi: 100% uspesnih zahteva.

**Scenario A — High-Frequency Ingestion (upis)**

| Protokol | Uspesni zahtevi | RPS | avg | p(95) |
| :--- | :---: | :---: | :---: | :---: |
| REST | 79976 | 666 | 129 ms | 325 ms |
| GraphQL | 68320 | 569 | 168 ms | 422 ms |
| gRPC | 14584 | 121 | 1,18 s | 3,05 s |

**Scenario B — Selective Monitoring (selektivno citanje)**

| Protokol | Uspesni zahtevi | RPS | avg | p(95) |
| :--- | :---: | :---: | :---: | :---: |
| REST | 91449 | 762 | 100 ms | 273 ms |
| GraphQL | 76020 | 633 | 141 ms | 374 ms |
| gRPC | 15468 | 129 | 1,11 s | 2,85 s |

**Scenario C — Heavy Querying (agregacija)**

| Protokol | Uspesni zahtevi | RPS | avg | p(95) |
| :--- | :---: | :---: | :---: | :---: |
| REST | 22024 | 183 | 746 ms | 2,46 s |
| GraphQL | 21549 | 180 | 764 ms | 2,58 s |
| gRPC | 10801 | 90 | 1,65 s | 5,05 s |

Zapazanja:
- Redosled po brzini je logican: B (indeksirani point-read) je najbrzi, A (upis) sredina, C (agregacija nad ~51k redova) najsporiji.
- Node servisi (REST, GraphQL) drze 570-760 RPS jer event loop dobro podnosi 500 paralelnih I/O zahteva. REST je nesto brzi od GraphQL-a jer nema parsiranje/validaciju GraphQL upita.
- gRPC (Python) je ogranicen na ~120-130 RPS u svim scenarijima. Razlog je implementacija: sinhroni psycopg2 + `ThreadPoolExecutor` pod Python GIL-om, sto se vidi i u zauzecu CPU (tacka 3): gRPC kontejner dostize tek ~97% (jedno jezgro), dok Node servisi koriste 2+ jezgra. Ovo je svojstvo Python runtime-a, ne protokola — prednost gRPC-a je u velicini poruke i memoriji, ne u sirovoj propusnosti naspram Node-a.

## 3. Zauzece resursa (CPU/RAM) — IZMERENO

Praceno preko `docker stats` tokom celog k6 testa (pik po kontejneru).

| Kontejner | RAM (mirovanje) | RAM (pik) | CPU (pik) |
| :--- | :---: | :---: | :---: |
| REST API (Node.js) | 42 MiB | 138 MiB | 232 % |
| GraphQL API (Node.js) | 50 MiB | 186 MiB | 193 % |
| gRPC API (Python) | 93 MiB | 107 MiB | 97 % |
| PostgreSQL 15 | 181 MiB | 1284 MiB (~1,28 GiB) | 1162 % |

Zapazanja:
- CPU se prikazuje kao % jednog jezgra, pa vrednosti > 100% znace vise jezgara (npr. 232% ≈ 2,3 jezgra).
- gRPC (Python) pik CPU ~97% = jedno zasiceno jezgro (GIL), uz najmanju memoriju (107 MiB) — odlican otisak za edge/M2M uredjaje.
- Node servisi koriste 2+ jezgra i vise RAM-a (V8 heap).
- PostgreSQL je najtezi: pik ~1162% CPU (~11,6 jezgara) i 1,28 GiB RAM pod 500 konekcija. U Scenariju C baza je usko grlo, pa je tu izbor protokola najmanje bitan.

## 4. Zakljucak

Nema univerzalno najboljeg protokola:
- **REST** — standardan, najlaksi za integraciju, najveca propusnost na Node-u; mana je najveci payload uz `SELECT *` (over-fetching u Scenariju B).
- **GraphQL** — salje samo trazena polja (resava over-fetching), idealan za klijente na losoj vezi; nesto sporiji od REST-a zbog obrade upita.
- **gRPC** — najmanji payload (binarni Protobuf) i najmanji RAM otisak; pogodan za M2M i edge. U ovoj postavci propusnost je nizja jer je Python server GIL-ogranicen na jedno jezgro.
- **Scenario C (agregacije)** — usko grlo je PostgreSQL (CPU/RAM), pa je izbor protokola tu najmanje vazan.

Metodologija je ujednacena za sva tri protokola; istorija ispravki je u `AUDIT_FIXES.md`. Kljucna ispravka baze: indeks `(device_id, timestamp DESC)` (umesto zasebnog indeksa po vremenu) ubrzao je Scenario B point-read sa ~365 ms na ~0,1 ms.
