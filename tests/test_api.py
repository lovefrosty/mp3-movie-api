"""Tests for movie persistence, retrieval, processing, and caching."""

import csv

import pytest

from src import MovieStorage


def test_upload_csv(client, sample_csv_bytes):
    response = client.post(
        "/upload",
        files={
            "file": (
                "sample_movies.csv",
                sample_csv_bytes,
                "text/csv",
            )
        },
    )
    assert response.status_code == 200
    dataset = response.json()
    assert dataset["rows"] == 20
    assert dataset["columns"] == 4
    assert dataset["filename"] == "sample_movies.csv"
    assert dataset["column_names"] == ["title", "release_year", "rating", "genre"]


def test_process_and_retrieve(client, uploaded_movies):
    process_response = client.post(
        "/movies/process",
        json={},
    )
    assert process_response.status_code == 200
    report = process_response.json()
    assert report["validation_rows_removed"] == 0
    assert report["cleaning_report"] == {
        "rows_before": 20,
        "rows_after": 18,
        "rows_removed": 2,
        "columns_before": 4,
        "columns_after": 4,
        "columns_removed": 0,
    }

    retrieve_response = client.get("/movies")
    assert retrieve_response.status_code == 200
    dataset = retrieve_response.json()
    assert dataset["total_rows"] == 18
    assert len(dataset["data"]) == 18
    assert [movie["title"] for movie in dataset["data"]] == [
        f"Movie {letter}" for letter in "ABCDEFGHIJKLMNOPQR"
    ]
    assert dataset["data"][:2] == [
        {"id": 1, "title": "Movie A", "release_year": 2020, "rating": 8.0, "genre": "Drama"},
        {"id": 2, "title": "Movie B", "release_year": 2021, "rating": 8.5, "genre": "Comedy"},
    ]


def test_retrieve_empty_collection(client):
    response = client.get("/movies")
    assert response.status_code == 200
    assert response.json() == {"data": [], "total_rows": 0}


def test_movies_persist(client, test_storage, uploaded_movies, sample_csv_bytes):
    reopened_storage = MovieStorage(test_storage.db_path)
    movies = reopened_storage.get()
    expected_titles = [
        row["title"] for row in csv.DictReader(sample_csv_bytes.decode("utf-8").splitlines())
    ]
    assert reopened_storage.count_movies() == 20
    assert len(movies) == 20
    assert movies.columns.tolist() == ["title", "release_year", "rating", "genre"]
    assert movies["title"].tolist() == expected_titles

    response = client.get("/movies", params={"limit": 100})
    assert response.status_code == 200
    stored_movies = reopened_storage.select_columns(["title"], limit=100)
    expected_ids = list(range(1, 21))
    assert [movie["id"] for movie in stored_movies] == expected_ids
    assert [movie["id"] for movie in response.json()["data"]] == expected_ids


def test_cache_and_processing(client, uploaded_movies, processing_body):
    import main

    first = client.get("/movies", params={"limit": 100})
    limited = client.get("/movies", params={"limit": 1})
    assert first.status_code == limited.status_code == 200
    assert first.json()["total_rows"] == limited.json()["total_rows"] == 20
    assert len(first.json()["data"]) == 20
    assert limited.json()["data"] == first.json()["data"][:1]
    assert main.cache.get(100) == first.json()
    assert main.cache.get(1) == limited.json()

    repeated = client.get("/movies", params={"limit": 100})
    assert repeated.status_code == 200
    assert repeated.json() == first.json()

    processed = client.post("/movies/process", json=processing_body)
    assert processed.status_code == 200
    assert processed.json() == {
        "validation_rows_removed": 0,
        "cleaning_report": {
            "rows_before": 20,
            "rows_after": 16,
            "rows_removed": 4,
            "columns_before": 4,
            "columns_after": 4,
            "columns_removed": 0,
        },
    }
    assert main.cache.get(100) is None
    assert main.cache.get(1) is None

    refreshed = client.get("/movies", params={"limit": 100})
    assert refreshed.status_code == 200
    result = refreshed.json()
    assert result["total_rows"] == 16
    assert [movie["title"] for movie in result["data"]] == [
        f"Movie {letter}" for letter in "ABCDEFGHIJKLMNOP"
    ]
    assert [movie["id"] for movie in result["data"]] == list(range(1, 17))
    assert main.cache.get(100) == result


def test_cache_hit_skips_database(client, uploaded_movies, monkeypatch):
    import main

    first = client.get("/movies", params={"limit": 100})
    assert first.status_code == 200

    def unexpected_database_read(*args, **kwargs):
        pytest.fail("A cache hit should skip SQLite reads.")

    monkeypatch.setattr(main.storage, "select_columns", unexpected_database_read)
    monkeypatch.setattr(main.storage, "count_movies", unexpected_database_read)

    repeated = client.get("/movies", params={"limit": 100})
    assert repeated.status_code == 200
    assert repeated.json() == first.json()
