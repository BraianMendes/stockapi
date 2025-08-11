# Stocks API

This FastAPI service, built with Python 3.11+, provides a REST API that retrieves stock data from **Polygon.io**, scrapes performance and competitor data from **MarketWatch**, caches results, and allows recording of purchased amounts.

---

## Running the API

**With Docker Compose:**

```bash
docker compose up --build
```

Access the interactive docs at: [http://localhost:8000/docs](http://localhost:8000/docs)

**Direct Docker run:**

```bash
docker run -d -p 8000:8000 \
  --name stocks-api \
  -e POLYGON_API_KEY=YOUR_KEY \
  -e DATABASE_URL= \
  -e REDIS_URL= \
  stocks-api
```

---

## Stock Data Model

**Top-level fields:**

* `status` *(string)*
* `purchased_amount` *(integer)*
* `purchased_status` *(string)*
* `request_data` *(date: YYYY-MM-DD)*
* `company_code` *(string)*
* `company_name` *(string)*
* `Stock_values` *(object)*
* `performance_data` *(object)*
* `Competitors` *(array of objects)*

**Stock\_values:**

* `open`, `high`, `low`, `close` *(float)*
* `volume` *(float, optional)*
* `afterHours` *(float, optional)*
* `preMarket` *(float, optional)*

**performance\_data:**

* `five_days`, `one_month`, `three_months`, `year_to_date`, `one_year` *(float)*

**Competitors item:**

* `name` *(string)*
* `market_cap` *(object)*

  * `Currency` *(string)*
  * `Value` *(float)*

---

## Endpoints

### Stock

* **GET** `/stock/{symbol}`

  * Optional `request_date` query param (YYYY-MM-DD)
  * Defaults to last business day if missing
  * Cached per symbol and date

* **POST** `/stock/{symbol}`

  * Body: `{ "amount": 3 }`
  * Saves purchased amount and clears related cache entries

### Health

* **GET** `/health` – Basic status
* **GET** `/ready` – Checks Polygon and MarketWatch readiness
* **GET** `/debug/env` – Shows env flags if `DEBUG_ENV` is true
* **GET** `/ping` – Returns `pong`

---

## Tests (pytest)

- Install: `pip install -r requirements.txt`
- Run all tests: `python -m pytest`
- No Docker required (uses in-memory SQLite and mocked externals).