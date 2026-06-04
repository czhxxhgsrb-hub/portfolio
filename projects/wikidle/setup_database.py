import os
import csv
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "dbname": os.getenv("DB_NAME", "wikipedia_articles"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "")
}

CSV_FILE = "WIKIDLE_REPO/wiki_articles.csv"

def main():
    connection = psycopg2.connect(**DB_CONFIG)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS wikipedia_articles (
            title TEXT PRIMARY KEY,
            summary TEXT NOT NULL,
            category TEXT,
            picture TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_results (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            article_title TEXT NOT NULL REFERENCES wikipedia_articles(title) ON DELETE CASCADE,
            guesses INTEGER NOT NULL CHECK (guesses > 0),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_game_results_article_title
        ON game_results(article_title);
    """)

    with open(CSV_FILE, "r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            cursor.execute("""
                INSERT INTO wikipedia_articles (title, summary, category, picture)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (title) DO NOTHING;
            """, (
                row["title"],
                row["summary"],
                row["category"],
                row["image"]
            ))

    connection.commit()

    cursor.execute("SELECT COUNT(*) FROM wikipedia_articles;")
    count = cursor.fetchone()[0]

    cursor.close()
    connection.close()

    print(f"Database setup complete. {count} articles are available.")

if __name__ == "__main__":
    main()