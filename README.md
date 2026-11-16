# MP3 Movie API

This FastAPI application uploads, retrieves, searches, and cleans a collection of movies. The upload route reads a CSV with four movie columns and replaces the collection in one SQLite transaction. The database and storage modules create the table, save rows, and use SQL to filter, order, and count movies. The processing route validates the request settings, runs the reused data pipeline, saves the cleaned collection, and reports how many rows and columns were removed. The cache module uses fakeredis to keep each `GET /movies` response for 90 seconds under a key based on its row limit. Successful uploads and processing clear the cache, so the next retrieval reads the current collection from SQLite. SQLite preserves the movies when the server restarts.

## Run the API and tests

From the project directory, create and activate the virtual environment, install the requirements, and start Uvicorn.

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

Open [Swagger UI](http://127.0.0.1:8000/docs). In a second terminal at the project directory, activate the same environment and run the tests.

```bash
source venv/bin/activate
python -m pytest tests -v
```

## Sample processing request

Upload `fixtures/sample_movies.csv` to `POST /upload`, then send this JSON body to `POST /movies/process`.

```json
{
  "validation": {
    "required_columns": ["title", "release_year", "rating", "genre"],
    "numeric_columns": ["release_year", "rating"]
  },
  "processing": {
    "remove_duplicates": true,
    "missing": {"enabled": true, "axis": "rows"},
    "outliers": {
      "enabled": true,
      "columns": ["rating"],
      "method": "iqr",
      "threshold": 1.5
    }
  }
}
```

A fresh upload contains 20 movies. This request removes two duplicate rows and two rating outliers. The next `GET /movies` returns 16 movies.

```json
{
  "validation_rows_removed": 0,
  "cleaning_report": {
    "rows_before": 20,
    "rows_after": 16,
    "rows_removed": 4,
    "columns_before": 4,
    "columns_after": 4,
    "columns_removed": 0
  }
}
```
