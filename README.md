# Uporedni benchmark REST, GraphQL i gRPC protokola za prenos senzorskih podataka pod jednakim uslovima

Ovaj projekat predstavlja kompletan istraživački i praktični rad na temu evaluacije performansi tri dominantna sinhrona komunikaciona modela (**REST**, **GraphQL** i **gRPC**) u kontekstu Interneta stvari (IoT). Projekat analizira latenciju, mrežni saobraćaj (payload size) i procesorske resurse pod različitim opterećenjima u kontejnerizovanom okruženju.

---

## 🛠️ Tehnološki Stek i Arhitektura Sistema

Sistem se sastoji od pet kontejnera povezanih u zajedničku Docker mrežu:

1.  **Baza podataka (PostgreSQL 15)**: Centralno skladište optimizovano za rad sa vremenskim serijama (Time-Series) i senzorima.
2.  **Seeder (Python)**: Ingestuje preko 66MB realnih IoT podataka iz `dataset.csv` u bazu prilikom prvog pokretanja.
3.  **REST API (Node.js + Express)**: Servis koji komunicira JSON formatom i poseduje interaktivnu OpenAPI (Swagger) dokumentaciju.
4.  **GraphQL API (Node.js + Apollo Server)**: Omogućava fleksibilno dobavljanje podataka i rešavanje problema over-fetching-a.
5.  **gRPC API (Python + gRPC)**: Visoko-performantni binarni servis zasnovan na `.proto` ugovorima i ThreadPoolExecutor-u za maksimalnu brzinu.

---

## 💾 1. Optimizacija i Seeding Baze Podataka

Baza podataka koristi PostgreSQL 15 sa tabelom `sensor_data` koja mapira 5 ključnih senzorskih podataka i metapodatke:
```sql
CREATE TABLE IF NOT EXISTS sensor_data (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    air_temp REAL,
    sea_temp REAL,
    humidity REAL,
    pressure REAL,
    wind_speed REAL
);
```

### ⚡ Optimizacija Indeksima
Pošto sva tri scenarija filtriraju po `device_id`, koristi se **jedan kompozitni indeks** koji indeksira i ID uređaja i vreme:
*   `idx_sensor_data_device_time` ON `sensor_data (device_id, timestamp DESC)` — pokriva i Scenario B (point-read poslednjih očitavanja uređaja: `WHERE device_id=? ORDER BY timestamp DESC LIMIT N`) i Scenario C (agregacija nad redovima jednog uređaja).

> **Napomena (ispravka):** zaseban indeks samo po vremenu (`(timestamp)`) namerno je uklonjen. Pošto su podaci svake M-stanice vremenski grupisani, indeks samo po vremenu je navodio planer da skenira celu tabelu (najnovije prvo) i filtrira po `device_id`, zbog čega je point-read u Scenariju B bio ~400× sporiji (≈365 ms umesto ≈0,1 ms). Kompozitni indeks rešava i taj problem i zadovoljava zahtev „indeksiranje po vremenu i ID-u uređaja“.

---

## 💻 2. Opis Implementiranih Servisa

### 📡 A. REST API (Node.js / Express)
REST servis je implementiran u Node.js okruženju. Nudi standardne rute za komunikaciju u JSON formatu i koristi `swagger-ui-express` za dinamičku dokumentaciju na `/api-docs`.

*   **Scenario A (Upis)**: `POST /api/sensor-data`
    Prati REST smernice, prima kompletan JSON objekat merenja i vraća `201 Created` sa jedinstvenim ID-jem novog zapisa.
*   **Scenario B (Selektivno čitanje)**: `GET /api/sensor-data/selective/:device_id?limit=10`
    *Namerno* je implementiran sa `SELECT *` upitom nad bazom i vraća kompletne redove kako bi se empirijski prikazao problem **over-fetching-a** (prekomernog slanja podataka sa servera na klijenta) koji je inherentan tradicionalnom REST-u.
*   **Scenario C (Agregacija)**: `GET /api/sensor-data/aggregate?device_id=M1&start_time=...&end_time=...`
    Izvršava SQL agregacije (`AVG`, `MAX`, `MIN`, `COUNT`) i vraća rezultate grupisane po uređaju.

---

### 🕸️ B. GraphQL API (Node.js / Apollo Server)
Implementiran pomoću Apollo Server-a, GraphQL servis nudi fleksibilnu šemu gde klijent eksplicitno definiše polja koja želi da dobije nazad, čime se u potpunosti eliminiše prekomerni mrežni overhead.

*   **Šema i Tipovi (`typeDefs`)**:
    ```graphql
    type SensorData {
      id: ID!
      device_id: String!
      timestamp: String!
      air_temp: Float
      sea_temp: Float
      humidity: Float
      pressure: Float
      wind_speed: Float
    }

    type AggregatedData {
      device_id: String!
      avg_air_temp: Float
      max_air_temp: Float
      min_air_temp: Float
      avg_humidity: Float
      total_readings: Int
    }

    type Query {
      getSensorData(device_id: String!, limit: Int): [SensorData]
      getAggregatedData(device_id: String, start_time: String, end_time: String): [AggregatedData]
    }

    type Mutation {
      ingestSensorData(
        device_id: String!
        timestamp: String!
        air_temp: Float
        sea_temp: Float
        humidity: Float
        pressure: Float
        wind_speed: Float
      ): SensorData
    }
    ```
*   **Rešavači (Resolvers)**:
    Mapiraju GraphQL upite i mutacije na PostgreSQL `pg` drajver, omogućavajući klijentu da u Scenariju B zatraži samo `timestamp`, `air_temp` i `humidity`, dok server šalje isključivo ta polja.

---

### ⚡ C. gRPC API (Python)
gRPC servis je napisan u Python-u i oslanja se na visoko-performantni `grpcio` paket. Definisana je stroga binarna šema u `sensor.proto` fajlu.

*   **Proto Definicija (`sensor.proto`)**:
    ```protobuf
    syntax = "proto3";
    package sensor;

    service SensorService {
      rpc IngestSensorData (SensorData) returns (IngestResponse);
      rpc GetSelectiveData (SelectiveRequest) returns (SelectiveResponse);
      rpc GetAggregatedData (AggregateRequest) returns (AggregateResponse);
    }

    message SensorData {
      string device_id = 1;
      string timestamp = 2;
      float air_temp = 3;
      float sea_temp = 4;
      float humidity = 5;
      float pressure = 6;
      float wind_speed = 7;
    }

    message IngestResponse {
      string message = 1;
      string id = 2;
    }

    message SelectiveRequest {
      string device_id = 1;
      int32 limit = 2;
    }

    message SelectiveData {
      string timestamp = 1;
      float air_temp = 2;
      float humidity = 3;
    }

    message SelectiveResponse {
      repeated SelectiveData data = 1;
    }

    message AggregateRequest {
      string device_id = 1;
      string start_time = 2;
      string end_time = 3;
    }

    message AggregatedData {
      string device_id = 1;
      float avg_air_temp = 2;
      float max_air_temp = 3;
      float min_air_temp = 4;
      float avg_humidity = 5;
      int32 total_readings = 6;
    }

    message AggregateResponse {
      repeated AggregatedData data = 1;
    }
    ```
*   **Python Server**:
    Koristi `ThreadedConnectionPool` za efikasno upravljanje konekcijama sa bazom i `sensor_pb2_grpc` klase generisane iz protokola. Zahvaljujući serijalizaciji u Protocol Buffers (binarni format), mrežni overhead je sveden na minimum.

---

## 🧪 3. Validacioni IoT Scenariji

Merenja su izvedena kroz tri specifična scenarija koji simuliraju realne situacije u IoT sistemima:

1.  **Scenario A (High-Frequency Ingestion)**: Ingestija podataka. Simulacija edge uređaja koji šalje kontinuirana merenja sa 7 parametara brzim tempom na server.
2.  **Scenario B (Selective Monitoring)**: Selektivno čitanje. Klijentska aplikacija (npr. mobilna aplikacija preko loše mobilne mreže) preuzima istoriju očitavanja sa zahtevom za samo 2 senzora (temperatura vazduha i vlažnost) od ukupno 10 dostupnih vrednosti.
3.  **Scenario C (Heavy Querying)**: Složene agregacije. Izračunavanje prosečnih, maksimalnih i minimalnih temperatura vazduha, prosečne vlažnosti i ukupnog broja merenja u određenom vremenskom opsegu.

---

## 📊 4. Rezultati Analize i Evaluacije Performansi

Merenja se rade nad sistemom u Docker Compose-u, kroz tri grupe: latencija i propusnost (k6), velicina odgovora (payload) i zauzece resursa (`docker stats`). Svi protokoli se mere pod istim uslovima: isti profil opterecenja (10/100/500 VU, faze po 30s), isto vreme izmedju zahteva (0,1s), jedan zahtev po iteraciji i jednak broj DB konekcija (500). Skripta `validate.py` proverava da su ovi uslovi ispunjeni.

### 💾 A. Veličina Odgovora (Payload Size) — IZMERENO

Mereno uzivo nad pokrenutim sistemom: za isti upit nad istim podacima (uredjaj M1) izmeren je tacan broj bajtova koji servis vrati — duzina HTTP odgovora (REST/GraphQL) i tacan Protobuf `ByteSize` (gRPC). Odgovor servera po scenariju:

| Scenario | REST (JSON) | GraphQL (JSON) | gRPC (Protobuf) |
| :--- | :---: | :---: | :---: |
| **A — Ingestion (ACK odgovor)** | 53 B | 47 B | **18 B** |
| **B — Selective (1 zapis)** | 149 B | 89 B | **39 B** |
| **C — Aggregate (1 uredjaj)** | 149 B | 181 B | **30 B** |

Velicina zahteva pri ingestiji (isti logicki zapis, kanonske vrednosti):

| Ingestija — zahtev | REST (JSON) | GraphQL (JSON) | gRPC (Protobuf) |
| :--- | :---: | :---: | :---: |
| **Telo zahteva** | 147 B | 540 B (uklj. tekst mutacije) | **61 B** |

> **Zaključak**: binarni Protobuf (gRPC) daje najmanji saobracaj u svim scenarijima jer ne salje nazive polja ni separatore. U Scenariju B REST vraca svih 8 kolona (`SELECT *`, over-fetching = 149 B), dok GraphQL (89 B) i gRPC (39 B) salju samo 3 trazena polja. U Scenariju C pravi agregat vraca brojeve u punoj preciznosti, pa JSON raste (REST 149 B, GraphQL 181 B zbog `data` omotaca i naziva), dok je Protobuf float fiksno 4 B — gRPC odgovor je samo 30 B. Zahtev pri ingestiji je najveci kod GraphQL-a (540 B, ceo tekst mutacije), a najmanji kod gRPC-a (61 B).
>
> Napomena: gRPC vrednost je velicina Protobuf poruke; na zici se dodaje jos 5 B gRPC okvira po poruci plus HPACK-kompresovana HTTP/2 zaglavlja (amortizovana kroz konekciju).

### 📈 B. Latencija i Propusnost (k6) — IZMERENO

Profil opterećenja 10 → 100 → 500 VU (faze po 30 s), `sleep(0.1)` po iteraciji, jedan zahtev po iteraciji, identično za sva tri protokola. Metrika: `http_req_duration` (REST/GraphQL) / `grpc_req_duration` (gRPC). Svi testovi: **100% uspešnih zahteva**.

**Scenario A — High-Frequency Ingestion (upis)**

| Protokol | Uspešni zahtevi | RPS | avg | p(95) |
| :--- | :---: | :---: | :---: | :---: |
| REST | 79976 | 666 | 129 ms | 325 ms |
| GraphQL | 68320 | 569 | 168 ms | 422 ms |
| gRPC | 14584 | 121 | 1,18 s | 3,05 s |

**Scenario B — Selective Monitoring (selektivno čitanje)**

| Protokol | Uspešni zahtevi | RPS | avg | p(95) |
| :--- | :---: | :---: | :---: | :---: |
| REST | 91449 | 762 | 100 ms | 273 ms |
| GraphQL | 76020 | 633 | 141 ms | 374 ms |
| gRPC | 15468 | 129 | 1,11 s | 2,85 s |

**Scenario C — Heavy Querying (agregacija)**

| Protokol | Uspešni zahtevi | RPS | avg | p(95) |
| :--- | :---: | :---: | :---: | :---: |
| REST | 22024 | 183 | 746 ms | 2,46 s |
| GraphQL | 21549 | 180 | 764 ms | 2,58 s |
| gRPC | 10801 | 90 | 1,65 s | 5,05 s |

Redosled po brzini je očekivan: **B (indeksirani point-read) > A (upis) > C (agregacija)** za Node servise. gRPC (Python) je u svim scenarijima na ~120–130 RPS jer je server GIL-ograničen na jedno jezgro (vidi CPU pik ispod); prednost gRPC-a je veličina poruke i memorija, ne sirova propusnost.

### 🖥️ C. Zauzeće Resursa (CPU i RAM) — IZMERENO

Praćeno preko `docker stats` tokom celog k6 testa (pik po kontejneru).

| Kontejner | RAM (mirovanje) | RAM (pik) | CPU (pik) |
| :--- | :---: | :---: | :---: |
| REST API (Node.js) | 42 MiB | 138 MiB | 232 % |
| GraphQL API (Node.js) | 50 MiB | 186 MiB | 193 % |
| gRPC API (Python) | 93 MiB | 107 MiB | 97 % |
| PostgreSQL 15 | 181 MiB | 1284 MiB (~1,28 GiB) | 1162 % |

> CPU je % jednog jezgra (>100% = više jezgara). **gRPC pik ~97% = jedno zasićeno jezgro (Python GIL)**, uz najmanji RAM otisak (107 MiB) — idealno za edge/M2M. Node servisi koriste 2+ jezgra. **PostgreSQL je najteži** (~11,6 jezgara, 1,28 GiB) i pravo je usko grlo u Scenariju C.

---

## 🚀 Kako Pokrenuti Projekat i Pokrenuti Testove

### 1. Pokretanje Kompletnog Okruženja
Uđite u direktorijum `IoT_Project` i pokrenite Docker Compose:
```bash
docker-compose up --build -d
```
*Ova komanda će podići bazu, pokrenuti seeder koji će učitati podatke, i startovati sva tri mikroservisa.*

### 2. Provera Servisa
*   **REST API Swagger**: [http://localhost:3000/api-docs](http://localhost:3000/api-docs)
*   **GraphQL Playground**: [http://localhost:4000/](http://localhost:4000/)
*   **gRPC endpoint**: `localhost:50051`

### 3. Automatsko Pokretanje Benchmark k6 Testova
Da biste pokrenuli sve k6 load testove automatski i izmerili latencije, pokrenite Python skriptu:
```bash
py run_tests.py
```

Svaki k6 test ispisuje svoj zavrsni summary u terminal (za screenshot), a masinski citljiv summary se cuva u `results/scenario_<x>_<protokol>.json`.
