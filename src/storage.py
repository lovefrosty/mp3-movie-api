"""SQLite storage for the movie collection."""

import logging
import sqlite3

import pandas as pd

from .database import get_connection, initialize_database

logger = logging.getLogger(__name__)
MOVIE_COLUMNS = ["title", "release_year", "rating", "genre"]


class MovieStorage:
    def __init__(self, db_path="data/movies.db"):
        self.db_path = db_path
        initialize_database(self.db_path)

    def save(self, df):
        """Replace all movie rows in one transaction."""
        movie_data = df[MOVIE_COLUMNS].astype(object)
        movie_data = movie_data.where(movie_data.notna(), None)
        rows = movie_data.itertuples(index=False, name=None)

        connection = get_connection(self.db_path)
        try:
            connection.execute("DELETE FROM movies")
            connection.executemany(
                """
                INSERT INTO movies (title, release_year, rating, genre)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )
            connection.commit()
        except sqlite3.Error:
            connection.rollback()
            raise
        finally:
            connection.close()

        logger.debug("Stored movies in SQLite: rows=%d", len(movie_data))

    def get(self):
        """Return the four movie columns as a DataFrame, ordered by id."""
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                "SELECT title, release_year, rating, genre FROM movies ORDER BY id"
            ).fetchall()
        finally:
            connection.close()

        return pd.DataFrame.from_records(rows, columns=MOVIE_COLUMNS)

    def select_columns(self, columns, limit=5):
        """Return id plus the requested movie columns, ordered by id."""
        if not columns:
            logger.error("Select at least one column")
            raise ValueError("Select at least one column")

        for column in columns:
            if column not in MOVIE_COLUMNS:
                logger.error("Unsupported column: %s", column)
                raise ValueError(f"Unsupported column: {column}")

        selected_columns = ", ".join(["id", *columns])
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                f"SELECT {selected_columns} FROM movies ORDER BY id LIMIT ?",
                (limit,),
            ).fetchall()
        finally:
            connection.close()

        logger.debug("Selected movies: columns=%s, returned_rows=%d", columns, len(rows))
        return [dict(row) for row in rows]

    def count_movies(self):
        """Return the number of stored movies using SQL COUNT(*)."""
        connection = get_connection(self.db_path)
        try:
            row = connection.execute("SELECT COUNT(*) AS total FROM movies").fetchone()
            return row["total"]
        finally:
            connection.close()

    def query_movies(self, columns, min_rating, limit):
        """Return selected fields from matching movies using SQL."""
        if not columns:
            logger.error("Select at least one column")
            raise ValueError("Select at least one column")

        for column in columns:
            if column not in MOVIE_COLUMNS:
                logger.error("Unsupported column: %s", column)
                raise ValueError(f"Unsupported column: {column}")

        selected_columns = ", ".join(["id", *columns])
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                f"""
                SELECT {selected_columns}
                FROM movies
                WHERE rating >= ?
                ORDER BY rating DESC, id ASC
                LIMIT ?
                """,
                (min_rating, limit),
            ).fetchall()
        finally:
            connection.close()

        logger.debug(
            "Queried movies: columns=%s, min_rating=%s, returned_rows=%d",
            columns,
            min_rating,
            len(rows),
        )
        return [dict(row) for row in rows]
