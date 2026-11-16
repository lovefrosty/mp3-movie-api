"""Application entry point for the MP3 movie API."""

import io
import logging
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from data_pipeline import create_cleaning_report, process_data, validate_dataframe
from src import (
    HealthResponse,
    MovieCache,
    MovieDataResponse,
    MovieProcessingReport,
    MovieStorage,
    MovieUploadInfo,
    ProcessConfig,
    log_requests,
    setup_logging,
)
from src.storage import MOVIE_COLUMNS

setup_logging(verbose=True)
logger = logging.getLogger(__name__)

app = FastAPI(title="Data Processing API", version="1.0.0")
app.middleware("http")(log_requests)
storage = MovieStorage()
cache = MovieCache()


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Return the application status and version."""
    return {"status": "ok", "version": "1.0.0"}


@app.post("/upload", response_model=MovieUploadInfo)
async def upload_movies(file: UploadFile = File(...)):
    """Read a movie CSV and replace the stored collection."""
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    if extension != ".csv":
        logger.warning("Unsupported file format: %s", extension)
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as error:
        logger.warning("Could not read CSV file %s: %s", filename, error)
        raise HTTPException(
            status_code=400,
            detail=f"Could not read CSV file: {error}",
        ) from error

    if set(df.columns) != set(MOVIE_COLUMNS):
        expected_columns = ", ".join(MOVIE_COLUMNS)
        logger.warning("Invalid movie columns: %s", df.columns.tolist())
        raise HTTPException(status_code=400, detail=f"CSV must contain exactly: {expected_columns}.")
    if df.empty:
        logger.warning("Movie CSV contains no data rows: %s", filename)
        raise HTTPException(status_code=400, detail="CSV must contain at least one movie.")

    df = df[MOVIE_COLUMNS]
    storage.save(df)
    cache.invalidate()
    logger.info("Uploaded movies: filename=%s, rows=%s", filename, len(df))
    return MovieUploadInfo(
        filename=filename,
        rows=len(df),
        columns=len(df.columns),
        column_names=df.columns.tolist(),
    )


@app.get("/movies", response_model=MovieDataResponse)
def get_movies(limit: int = Query(default=100, ge=1)):
    """Return a limited set of movies and the total collection size."""
    cached_response = cache.get(limit)
    if cached_response is not None:
        logger.info("Returned cached movies: limit=%s", limit)
        return cached_response

    rows = storage.select_columns(MOVIE_COLUMNS, limit)
    total_rows = storage.count_movies()
    response = {"data": rows, "total_rows": total_rows}
    cache.set(limit, response)
    logger.info("Retrieved movies: returned_rows=%s, total_rows=%s", len(rows), total_rows)
    return response


@app.get("/movies/search", response_model=list[dict])
def query_movies(
    columns: list[str] = Query(default=["title"]),
    min_rating: float = Query(default=0, ge=0, le=10),
    limit: int = Query(default=100, ge=1),
):
    """Return selected fields for movies that meet the rating threshold."""
    try:
        rows = storage.query_movies(columns, min_rating, limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    logger.info(
        "Queried movies: columns=%s, min_rating=%s, returned_rows=%s",
        columns,
        min_rating,
        len(rows),
    )
    return rows


@app.post("/movies/process", response_model=MovieProcessingReport)
def process_movies(config: ProcessConfig):
    """Validate and clean the collection using the MP1 pipeline."""
    df = storage.get()
    if df.empty:
        logger.warning("Cannot process an empty movie collection")
        raise HTTPException(status_code=400, detail="No movies to process.")

    config_dict = config.model_dump()
    validation_settings = config_dict["validation"]
    missing_numeric_columns = [
        column
        for column in validation_settings["numeric_columns"]
        if column not in df.columns
    ]
    if missing_numeric_columns:
        missing_columns = ", ".join(missing_numeric_columns)
        logger.warning("Numeric columns are missing: %s", missing_columns)
        raise HTTPException(
            status_code=400,
            detail=f"Numeric columns are missing: {missing_columns}",
        )

    try:
        validated_df = validate_dataframe(
            df,
            required_columns=validation_settings["required_columns"],
            numeric_columns=validation_settings["numeric_columns"],
        )
        validation_rows_removed = len(df) - len(validated_df)
        processed_df = process_data(validated_df, config_dict)
        cleaning_report = create_cleaning_report(validated_df, processed_df)
    except ValueError as error:
        logger.warning("Movie processing failed: %s", error)
        raise HTTPException(status_code=400, detail=str(error)) from error

    # The SQLite table keeps its columns even when cleaning drops one.
    storage.save(processed_df.reindex(columns=MOVIE_COLUMNS))
    cache.invalidate()
    logger.info(
        "Processed movies: validation_removed=%s, rows_before=%s, rows_after=%s",
        validation_rows_removed,
        cleaning_report["rows_before"],
        cleaning_report["rows_after"],
    )
    return {
        "validation_rows_removed": validation_rows_removed,
        "cleaning_report": cleaning_report,
    }
