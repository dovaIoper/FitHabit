# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import sqlite3
import json

app = Flask(__name__)
app.secret_key = 'your_secret_key'


# -------------------- Database Helper --------------------
def get_db_connection():
    conn = sqlite3.connect('instance/habit_tracker.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.context_processor
def inject_theme():
    theme = request.cookies.get('theme', 'light')
    return dict(theme=theme)

# -------------------- Helper for Weekly Grouping --------------------
def group_by_week(entries):
    weeks = []
    entries = sorted(entries, key=lambda x: x['date'])
    if not entries:
        return weeks

    start_date = datetime.strptime(entries[0]['date'], "%Y-%m-%d")
    current_week = []
    week_start = start_date - timedelta(days=start_date.weekday())
    week_end = week_start + timedelta(days=6)

    for entry in entries:
        entry_date = datetime.strptime(entry['date'], "%Y-%m-%d")
        if week_start <= entry_date <= week_end:
            current_week.append(entry)
        else:
            weeks.append({
                'start_date': week_start.date(),
                'end_date': week_end.date(),
                'entries': current_week
            })
            current_week = [entry]
            week_start = entry_date - timedelta(days=entry_date.weekday())
            week_end = week_start + timedelta(days=6)

    if current_week:
        weeks.append({
            'start_date': week_start.date(),
            'end_date': week_end.date(),
            'entries': current_week
        })
    return weeks

# -------------------- Routes --------------------
@app.route('/')
def home():
    return render_template("login.html")


@app.route('/toggle_theme')
def toggle_theme():
    current_theme = request.cookies.get('theme', 'light')
    new_theme = 'dark' if current_theme == 'light' else 'light'
    resp = make_response(redirect(request.referrer or url_for('home')))
    resp.set_cookie('theme', new_theme, max_age=30 * 24 * 60 * 60)
    return resp


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        conn = get_db_connection()
        existing_user = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?', (username, email)).fetchone()

        if existing_user:
            flash("Username or email already exists.", "error")
            conn.close()
            return redirect(url_for('register'))

        conn.execute('INSERT INTO users (username, email, password) VALUES (?, ?, ?)', (username, email, password))
        conn.commit()
        conn.close()
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_input = request.form['login']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? OR email = ?', (login_input, login_input)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash("Logged in successfully.", "success")
            return redirect(url_for('input_form'))

        flash("Invalid credentials.", "error")
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for('home'))


@app.route('/input_form', methods=['GET', 'POST'])
def input_form():
    if 'username' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        date = request.form.get('date', datetime.today().strftime('%Y-%m-%d'))
        sleep = request.form.get('sleep')
        eat = request.form.get('eat')
        study = request.form.get('study')
        exercise = request.form.get('exercise')
        notes = request.form.get('notes', '')

        # If any required field is empty, show error and re-render form with previous data
        if not all([sleep, eat, study, exercise]):
            flash("Please fill in all fields.", "error")
            return render_template("input_form.html",
                date=date, sleep=sleep, eat=eat, study=study,
                exercise=exercise, notes=notes
            )

        # Safe conversion now
        sleep = float(sleep)
        eat = float(eat)
        study = float(study)
        exercise = float(exercise)

        conn = get_db_connection()
        conn.execute(
            'INSERT INTO entries (user_id, date, sleep, eat, study, exercise, notes) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (session['user_id'], date, sleep, eat, study, exercise, notes)
        )
        conn.commit()
        conn.close()

        flash("Progress saved successfully.", "success")
        return redirect(url_for('weekly_report'))

    # For GET method, just show the blank form (or today's date by default)
    return render_template("input_form.html", date=datetime.today().strftime('%Y-%m-%d'))


@app.route('/weekly_report')
def weekly_report():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    entries = conn.execute('SELECT * FROM entries WHERE user_id = ? ORDER BY date', (session['user_id'],)).fetchall()
    conn.close()

    weeks = group_by_week(entries)
    weekly_data = []
    for week in weeks:
        if len(week['entries']) < 7:
            feedback = None
        else:
            avg_sleep = sum(e['sleep'] for e in week['entries']) / len(week['entries'])
            avg_eat = sum(e['eat'] for e in week['entries']) / len(week['entries'])
            avg_study = sum(e['study'] for e in week['entries']) / len(week['entries'])
            avg_exercise = sum(e['exercise'] for e in week['entries']) / len(week['entries'])

            score = avg_sleep + avg_eat + avg_study + avg_exercise
            if score > 30:
                feedback = "Excellent job this week! Keep up the balanced lifestyle!"
            elif score > 20:
                feedback = "Good work! Try to improve a bit more next week."
            else:
                feedback = "Don't give up! Small steps lead to big progress."

        weekly_data.append({
            'start_date': week['start_date'],
            'end_date': week['end_date'],
            'entries': week['entries'],
            'feedback': feedback
        })

    return render_template("report.html", weekly_data=weekly_data)


@app.route('/journal')
def journal():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    entries = conn.execute('SELECT date, notes FROM entries WHERE user_id = ? ORDER BY date DESC',
                           (session['user_id'],)).fetchall()
    conn.close()
    return render_template("journal.html", entries=entries)


@app.route('/charts')
def charts():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    data = conn.execute('SELECT date, sleep, eat, study, exercise FROM entries WHERE user_id = ? ORDER BY date',
                        (session['user_id'],)).fetchall()
    conn.close()

    weeks = group_by_week(data)
    weekly_charts = []
    for week in weeks:
        labels = [row['date'] for row in week['entries']]
        datasets = [
            {"label": "Sleep", "data": [row['sleep'] for row in week['entries']], "borderColor": "#A3CEF1",
             "fill": False},
            {"label": "Eat", "data": [row['eat'] for row in week['entries']], "borderColor": "#FFB5A7", "fill": False},
            {"label": "Study", "data": [row['study'] for row in week['entries']], "borderColor": "#BDB2FF",
             "fill": False},
            {"label": "Exercise", "data": [row['exercise'] for row in week['entries']], "borderColor": "#CFF4D2",
             "fill": False},
        ]
        weekly_charts.append({
            'week_label': f"{week['start_date']} to {week['end_date']}",
            'labels': labels,
            'datasets': datasets
        })

    return render_template("charts.html", weekly_charts=weekly_charts,
                           weekly_charts_json=json.dumps(weekly_charts),)


@app.route('/settings')
def settings():
    return render_template("settings.html")


if __name__ == '__main__':
    app.run(debug=True)
