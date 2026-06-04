from flask import Flask, render_template, request, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import re
import random
import psycopg2
from psycopg2.extras import RealDictCursor
from connection import get_connection
import os

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")


def init_game_tables():
    connection = get_connection()
    cursor = connection.cursor()

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

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_wikipedia_articles_title
        ON wikipedia_articles(title);
    """)

    connection.commit()
    cursor.close()
    connection.close()


def get_current_user():
    if "user_id" not in session:
        return None

    return {
        "id": session["user_id"],
        "username": session.get("username", "")
    }


def create_user(username, password):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "INSERT INTO users (username, password_hash) VALUES (%s, %s) RETURNING id;",
            (username, generate_password_hash(password))
        )

        user_id = cursor.fetchone()[0]
        connection.commit()
        return user_id, None

    except psycopg2.errors.UniqueViolation:
        connection.rollback()
        return None, "That username is already taken."

    finally:
        cursor.close()
        connection.close()


def login_user(username, password):
    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        "SELECT id, username, password_hash FROM users WHERE username = %s;",
        (username,)
    )

    user = cursor.fetchone()

    cursor.close()
    connection.close()

    if not user or not check_password_hash(user["password_hash"], password):
        return False

    session["user_id"] = user["id"]
    session["username"] = user["username"]

    return True


def save_game_result(article_title, guesses):
    if not get_current_user() or session.get("result_saved"):
        return

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO game_results (user_id, article_title, guesses)
        VALUES (%s, %s, %s);
        """,
        (session["user_id"], article_title, guesses)
    )

    connection.commit()
    cursor.close()
    connection.close()

    session["result_saved"] = True


def get_leaderboard(article_title):
    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    cursor.execute(
        """
        SELECT guesses, COUNT(*) AS player_count
        FROM game_results
        WHERE article_title = %s
          AND guesses BETWEEN 1 AND 10
        GROUP BY guesses
        ORDER BY guesses;
        """,
        (article_title,)
    )

    rows = cursor.fetchall()

    counts_by_guess = {
        row["guesses"]: row["player_count"]
        for row in rows
    }

    histogram = []
    max_count = 0

    for guess_number in range(1, 11):
        player_count = counts_by_guess.get(guess_number, 0)
        max_count = max(max_count, player_count)

        histogram.append({
            "guesses": guess_number,
            "player_count": player_count
        })

    for row in histogram:
        if max_count == 0:
            row["height_percent"] = 0
        else:
            row["height_percent"] = round((row["player_count"] / max_count) * 100)

    cursor.execute(
        """
        SELECT u.username, MIN(gr.guesses) AS best_guesses
        FROM game_results gr
        JOIN users u ON u.id = gr.user_id
        WHERE gr.article_title = %s
        GROUP BY u.username
        ORDER BY best_guesses ASC, u.username ASC
        LIMIT 10;
        """,
        (article_title,)
    )

    top_scores = cursor.fetchall()

    cursor.close()
    connection.close()

    return histogram, top_scores


def reset_game_to_start():
    user_id = session.get("user_id")
    username = session.get("username")

    session.clear()

    if user_id:
        session["user_id"] = user_id
        session["username"] = username

    session["game_state"] = "not_started"
    session["image_revealed"] = False
    session["guesses"] = []
    session["wiki_page"] = None
    session["wiki_article"] = None
    session["result_saved"] = False


def mask_title_in_text(text, title):
    if not text:
        return text

    words = title.split()

    for word in words:
        pattern = r"\b" + re.escape(word) + r"\b"
        text = re.sub(pattern, "_____", text, flags=re.IGNORECASE)

    return text


def remove_first_sentence_parentheses(text):
    if not text:
        return text

    start = text.find("(")

    if start == -1:
        return text

    depth = 0

    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1

            if depth == 0:
                return text[:start] + text[i + 1:]

    return text


def format_article(row):
    if not row:
        return None

    title = row["title"]
    summary = row["summary"]
    category = row["category"]
    picture = row["picture"]

    if not summary or len(summary) < 300:
        return None

    if len(summary) > 2000:
        cutoff = summary[:2000].rfind(".")

        if cutoff != -1:
            summary = summary[:cutoff + 1]
        else:
            summary = summary[:2000]

    summary = remove_first_sentence_parentheses(summary)
    masked_text = mask_title_in_text(summary, title)

    return {
        "wiki_name": title,
        "wiki_category": category,
        "wiki_theme": category,
        "wiki_text": masked_text,
        "wiki_picture": picture,
    }


def get_random_article():
    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT title, summary, category, picture
        FROM wikipedia_articles
        WHERE summary IS NOT NULL
          AND length(summary) >= 300
        ORDER BY random()
        LIMIT 1;
    """)

    row = cursor.fetchone()

    cursor.close()
    connection.close()

    return format_article(row)


def get_article_by_title(title):
    connection = get_connection()
    cursor = connection.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT title, summary, category, picture
        FROM wikipedia_articles
        WHERE title = %s
        LIMIT 1;
    """, (title,))

    row = cursor.fetchone()

    cursor.close()
    connection.close()

    return format_article(row)


def search_article_titles(query):
    if not query or len(query.strip()) < 2:
        return []

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT title
        FROM wikipedia_articles
        WHERE title ILIKE %s
        ORDER BY title
        LIMIT 20;
    """, (f"%{query.strip()}%",))

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    return [row[0] for row in rows]


@app.route("/autocomplete")
def autocomplete():
    query = request.args.get("q", "").strip()
    titles = search_article_titles(query)
    return jsonify(titles)


@app.route("/", methods=["GET", "POST"])
def home():
    search_text = "..."
    game_state = session.get("game_state", "not_started")

    current_user = get_current_user()

    invalid_guess = False
    prev_guess = False
    auth_error = None

    leaderboard_histogram = []
    leaderboard_top_scores = []

    image_blur = "blurred"
    wiki_picture = ""

    guess_name = ""
    guess_category = ""
    guess_theme = ""

    guess_color = "white"
    category_color = "white"
    theme_color = "white"

    wiki_page = session.get("wiki_page")
    wiki_article = session.get("wiki_article")

    wiki_name = ""
    wiki_text = "..."
    wiki_category = ""
    wiki_theme = ""
    wiki_name_blurred = ""

    if wiki_article:
        wiki_name = wiki_article["wiki_name"]
        wiki_text = wiki_article["wiki_text"]
        wiki_category = wiki_article["wiki_category"]
        wiki_theme = wiki_article["wiki_theme"]
        wiki_picture = wiki_article["wiki_picture"]
        wiki_name_blurred = re.sub(r"\S", "_", wiki_name)

    if request.method == "POST":
        action = request.form.get("action")

        if action in ["login", "register"]:
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if not username or not password:
                auth_error = "Please enter a username and password."

            elif action == "register":
                user_id, error = create_user(username, password)

                if error:
                    auth_error = error
                else:
                    session["user_id"] = user_id
                    session["username"] = username
                    current_user = get_current_user()

            else:
                if login_user(username, password):
                    current_user = get_current_user()
                else:
                    auth_error = "Wrong username or password."

        elif action == "logout":
            session.clear()
            current_user = None
            game_state = "not_started"
            wiki_article = None
            wiki_page = None
            wiki_name = ""
            wiki_text = "..."
            wiki_category = ""
            wiki_theme = ""
            wiki_picture = ""
            wiki_name_blurred = ""

        elif action == "start" and current_user:
            article = get_random_article()

            if not article:
                return "No valid articles found. Check your Supabase wikipedia_articles table.", 500

            wiki_page = article["wiki_name"]

            session["wiki_page"] = wiki_page
            session["wiki_article"] = article
            session["image_revealed"] = False
            session["game_state"] = "playing"
            session["guess_count"] = 0
            session["guesses"] = []
            session["result_saved"] = False

            game_state = "playing"

            wiki_name = article["wiki_name"]
            wiki_text = article["wiki_text"]
            wiki_category = article["wiki_category"]
            wiki_theme = article["wiki_theme"]
            wiki_picture = article["wiki_picture"]
            wiki_name_blurred = re.sub(r"\S", "_", wiki_name)

        elif action == "reset":
            reset_game_to_start()
            game_state = "not_started"
            search_text = "..."

            wiki_page = None
            wiki_article = None
            wiki_name = ""
            wiki_text = "..."
            wiki_category = ""
            wiki_theme = ""
            wiki_name_blurred = ""
            wiki_picture = ""

            guess_name = ""
            guess_category = ""
            guess_theme = ""

            guess_color = "white"
            category_color = "white"
            theme_color = "white"

        elif action == "reveal_image":
            session["image_revealed"] = True

        elif action == "guess" and session.get("game_state") == "playing":
            search_text = request.form.get("search", "").strip()
            guesses = session.get("guesses", [])

            already_guessed = any(
                guess["name"].lower() == search_text.lower()
                for guess in guesses
            )

            guess_article = get_article_by_title(search_text)

            if not guess_article:
                invalid_guess = True

            elif already_guessed:
                prev_guess = True

            else:
                guess_name = guess_article["wiki_name"]
                guess_category = guess_article["wiki_category"]
                guess_theme = guess_article["wiki_theme"]

                if guess_name == wiki_name:
                    guess_color = "green"
                    wiki_name_blurred = wiki_name
                    session["game_state"] = "finished"
                    game_state = "finished"
                else:
                    guess_color = "red"

                if guess_category == wiki_category:
                    category_color = "green"
                else:
                    category_color = "red"

                if guess_theme == wiki_theme:
                    theme_color = "green"
                else:
                    theme_color = "red"

                guesses.append({
                    "name": guess_name,
                    "category": guess_category,
                    "theme": guess_theme,
                    "guess_color": guess_color,
                    "category_color": category_color,
                    "theme_color": theme_color
                })

                session["guesses"] = guesses
                session["guess_count"] = len(guesses)

                if guess_name == wiki_name:
                    save_game_result(wiki_name, len(guesses))

    guesses = session.get("guesses", [])
    guess_count = len(guesses)

    if guesses:
        latest_guess = guesses[-1]

        guess_name = latest_guess["name"]
        guess_category = latest_guess["category"]
        guess_theme = latest_guess["theme"]

        guess_color = latest_guess["guess_color"]
        category_color = latest_guess["category_color"]
        theme_color = latest_guess["theme_color"]

        if guess_name == wiki_name:
            wiki_name_blurred = wiki_name

    image_revealed = session.get("image_revealed", False)
    game_won = wiki_name == guess_name and wiki_name != ""

    if image_revealed or game_won:
        image_blur = ""
    else:
        image_blur = "blurred"

    if session.get("game_state") == "finished" and wiki_name:
        leaderboard_histogram, leaderboard_top_scores = get_leaderboard(wiki_name)
        game_state = "finished"

    return render_template(
        "index.html",
        wiki_name=wiki_name,
        search_text=search_text,
        guess_name=guess_name,
        wiki_text=wiki_text,
        wiki_category=wiki_category,
        wiki_theme=wiki_theme,
        guess_color=guess_color,
        category_color=category_color,
        theme_color=theme_color,
        guess_theme=guess_theme,
        guess_category=guess_category,
        guesses=guesses,
        guess_count=guess_count,
        wiki_name_blurred=wiki_name_blurred,
        invalid_guess=invalid_guess,
        prev_guess=prev_guess,
        game_state=game_state,
        wiki_page=wiki_page,
        wiki_picture=wiki_picture,
        image_blur=image_blur,
        image_revealed=session.get("image_revealed", False),
        game_won=game_won,
        current_user=current_user,
        auth_error=auth_error,
        leaderboard_histogram=leaderboard_histogram,
        leaderboard_top_scores=leaderboard_top_scores
    )


try:
    init_game_tables()
except Exception as error:
    print("Could not initialize game tables:", error)


if __name__ == "__main__":
    app.run(debug=True)