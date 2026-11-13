"""Tests for uploading, processing, and retrieving movies."""


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


def test_process_and_retrieve(client, uploaded_movies, processing_body):
    process_response = client.post(
        "/movies/process",
        json=processing_body,
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
