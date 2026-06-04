from flask import Flask, render_template, request, session
from werkzeug.security import generate_password_hash, check_password_hash
import re, random
import psycopg2
from psycopg2.extras import RealDictCursor
from connection import get_connection
import os

# TODO:
# final design touches

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
    connection = get_connection()
    if not get_current_user() or session.get("result_saved"):
        return

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

    # Convert database rows into a dictionary like:
    # {1: 3, 2: 5, 3: 0, ...}
    counts_by_guess = {
        row["guesses"]: row["player_count"]
        for row in rows
    }

    # Always show guesses 1 through 10, even if count is 0
    histogram = []
    max_count = 0

    for guess_number in range(1, 11):
        player_count = counts_by_guess.get(guess_number, 0)
        max_count = max(max_count, player_count)

        histogram.append({
            "guesses": guess_number,
            "player_count": player_count
        })

    # Add a bar height percentage for CSS
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

def mask_title_in_text(text, title): # regex til at erstatte titel i summary med "____"
    if not text:
        return text

    words = title.split()

    for word in words:
        pattern = r'\b' + re.escape(word) + r'\b'
        text = re.sub(pattern, '_____', text, flags=re.IGNORECASE)

    return text


def example_dict():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT title, summary, category, picture
        FROM wikipedia_articles
    """)
    rows = cursor.fetchall()
    cursor.close()
    connection.close()

    articles = {}

    def remove_first_sentence_parentheses(text):
    # fjerner første parantes i første sætning af en artikel.
    # Parantesen indeholder ofte udtalelse af artikel, f.eks (Swedish: [ˈɡrêːta ˈtʉ̂ːnbærj] ; born 3 January 2003).
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
    
    for title, summary, category, picture in rows:
        if not summary or len(summary) < 300: # artikler under 300 tegn bliver fjernet. Artikler over 2000 tegn bliver forkortet til nærmeste punktum
            continue
        if len(summary) > 2000:
            cutoff = summary[:2000].rfind(".")

            if cutoff != -1:
                summary = summary[:cutoff + 1]
            else:
                summary = summary[:2000]
        
        summary = remove_first_sentence_parentheses(summary)

        masked_text = mask_title_in_text(summary, title)

        articles[title] = {
            "wiki_name": title,
            "wiki_category": category,
            "wiki_theme": category,
            "wiki_text": masked_text,
            "wiki_picture": picture,
        }

    return articles


@app.route("/", methods=["GET", "POST"])
def home():
    init_game_tables()

    search_text = "..."
    game_state = session.get("game_state", "not_started")
    articles = example_dict()

    # IMPORTANT: this must come before any POST/action logic
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
    wiki_name = ""
    wiki_text = "..."
    wiki_category = ""
    wiki_theme = ""
    wiki_name_blurred = ""

    #restore current wiki page from session
    if wiki_page in articles:
        wiki_name = articles[wiki_page]["wiki_name"]
        wiki_text = articles[wiki_page]["wiki_text"]
        wiki_category = articles[wiki_page]["wiki_category"]
        wiki_theme = articles[wiki_page]["wiki_theme"]
        wiki_name_blurred = re.sub(r"\S", "_", wiki_name)
        wiki_picture = articles[wiki_page]["wiki_picture"]

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

        elif action == "start" and current_user:
            wiki_page = random.choice(list(articles.keys()))

            session["wiki_page"] = wiki_page
            session["image_revealed"] = False
            session["game_state"] = "playing"
            session["guess_count"] = 0
            session["guesses"] = []
            session["result_saved"] = False

            game_state = "playing"

            wiki_name = articles[wiki_page]["wiki_name"]
            wiki_text = articles[wiki_page]["wiki_text"]
            wiki_category = articles[wiki_page]["wiki_category"]
            wiki_theme = articles[wiki_page]["wiki_theme"]
            wiki_picture = articles[wiki_page]["wiki_picture"]
            wiki_name_blurred = re.sub(r"\S", "_", wiki_name)

        elif action == "reset":
            reset_game_to_start()
            game_state = "not_started"
            search_text = "..."

            wiki_page = None
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
                guess["name"] == search_text for guess in guesses
            )

            if search_text not in articles:
                invalid_guess = True

            elif already_guessed:
                prev_guess = True

            else:
                guess_name = articles[search_text]["wiki_name"]
                guess_category = articles[search_text]["wiki_category"]
                guess_theme = articles[search_text]["wiki_theme"]

                if search_text == wiki_name:
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

                if search_text == wiki_name:
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
        game_won = (wiki_name == guess_name)

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
        autocomplete_options=articles.keys(),
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
        game_won=(wiki_name == guess_name),
        current_user=current_user,
        auth_error=auth_error,
        leaderboard_histogram=leaderboard_histogram,
        leaderboard_top_scores=leaderboard_top_scores
    )


# runs the shit
if __name__ == "__main__":
    init_game_tables()
    app.run(debug=True)