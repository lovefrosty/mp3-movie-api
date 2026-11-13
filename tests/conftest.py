from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src import MovieStorage


@pytest.fixture
def client(monkeypatch, tmp_path):
    # main initializes its default database on import.
    monkeypatch.chdir(tmp_path)
    import main

    monkeypatch.setattr(main, "storage", MovieStorage(tmp_path / "movies.db"))
    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def sample_csv_bytes():
    filepath = Path(__file__).resolve().parents[1] / "fixtures" / "sample_movies.csv"
    return filepath.read_bytes()


@pytest.fixture
def uploaded_movies(client, sample_csv_bytes):
    response = client.post(
        "/upload",
        files={
            "file": (
                "sample_movies.csv",
                sample_csv_bytes,
                "text/csv"
            )
        }
    )
    assert response.status_code == 200


@pytest.fixture
def processing_body():
    return {
        "validation": {
            "required_columns": ["title", "release_year", "rating", "genre"],
            "numeric_columns": ["release_year", "rating"]
        },
        "processing": {
            "remove_duplicates": True,
            "missing": {
                "enabled": True,
                "axis": "rows"
            },
            "outliers": {
                "enabled": False,
                "columns": [],
                "method": "iqr",
                "threshold": 1.5
            }
        }
    }
