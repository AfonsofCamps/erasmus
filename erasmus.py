import os
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session, send_from_directory

app = Flask(__name__)
app.secret_key = 'erasmus_super_secret_key_2024'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ------------------ Database initialization ------------------
def init_db():
    conn = sqlite3.connect('erasmus.db')
    c = conn.cursor()

    # users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # testimonials table
    c.execute('''
        CREATE TABLE IF NOT EXISTS testimonials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            country TEXT NOT NULL,
            university TEXT NOT NULL,
            year INTEGER NOT NULL,
            testimonial_text TEXT NOT NULL,
            video_url TEXT,
            video_file TEXT,
            tags TEXT,
            is_approved BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # default admin
    admin_exists = c.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
    if not admin_exists:
        password_hash = generate_password_hash('admin123')
        c.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
                  ('admin', password_hash, True))

    conn.commit()
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect('erasmus.db')
    conn.row_factory = sqlite3.Row
    return conn

# ------------------ Authentication decorator ------------------
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('Acesso restrito a administradores!', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# ------------------ Routes ------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/erasmus')
def erasmus():
    return render_template('erasmus.html')

@app.route('/europa')
def europa():
    return render_template('europa.html')

@app.route('/cidadania')
def cidadania():
    return render_template('cidadania.html')

@app.route('/depoimentos')
def depoimentos():
    page = request.args.get('page', 1, type=int)
    per_page = 6
    offset = (page - 1) * per_page

    conn = get_db_connection()

    # Filters
    country_filter = request.args.get('country', '')
    year_filter = request.args.get('year', '')
    tag_filter = request.args.get('tag', '')

    query = "SELECT * FROM testimonials WHERE is_approved = 1"
    params = []
    if country_filter:
        query += " AND country = ?"
        params.append(country_filter)
    if year_filter:
        query += " AND year = ?"
        params.append(int(year_filter))
    if tag_filter:
        query += " AND tags LIKE ?"
        params.append(f'%{tag_filter}%')

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([per_page, offset])
    testimonials = conn.execute(query, params).fetchall()

    # total count
    count_query = "SELECT COUNT(*) FROM testimonials WHERE is_approved = 1"
    count_params = []
    if country_filter:
        count_query += " AND country = ?"
        count_params.append(country_filter)
    if year_filter:
        count_query += " AND year = ?"
        count_params.append(int(year_filter))
    if tag_filter:
        count_query += " AND tags LIKE ?"
        count_params.append(f'%{tag_filter}%')

    total_count = conn.execute(count_query, count_params).fetchone()[0]
    total_pages = (total_count + per_page - 1) // per_page

    # filters options
    countries = conn.execute("SELECT DISTINCT country FROM testimonials WHERE is_approved = 1 ORDER BY country").fetchall()
    years = conn.execute("SELECT DISTINCT year FROM testimonials WHERE is_approved = 1 ORDER BY year DESC").fetchall()

    all_tags = conn.execute("SELECT tags FROM testimonials WHERE is_approved = 1 AND tags IS NOT NULL").fetchall()
    tags_set = set()
    for tag_row in all_tags:
        if tag_row['tags']:
            tags_set.update([t.strip() for t in tag_row['tags'].split(',')])
    tags = sorted(tags_set)

    conn.close()

    return render_template('depoimentos.html',
                           testimonials=testimonials,
                           page=page,
                           total_pages=total_pages,
                           countries=countries,
                           years=years,
                           tags=tags,
                           current_country=country_filter,
                           current_year=year_filter,
                           current_tag=tag_filter)

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    total_testimonials = conn.execute("SELECT COUNT(*) FROM testimonials").fetchone()[0]
    approved_testimonials = conn.execute("SELECT COUNT(*) FROM testimonials WHERE is_approved = 1").fetchone()[0]
    pending_testimonials = conn.execute("SELECT COUNT(*) FROM testimonials WHERE is_approved = 0").fetchone()[0]

    countries_data = conn.execute('''
        SELECT country, COUNT(*) as count
        FROM testimonials
        WHERE is_approved = 1
        GROUP BY country
        ORDER BY count DESC
    ''').fetchall()

    years_data = conn.execute('''
        SELECT year, COUNT(*) as count
        FROM testimonials
        WHERE is_approved = 1
        GROUP BY year
        ORDER BY year DESC
    ''').fetchall()

    monthly_data = conn.execute('''
        SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
        FROM testimonials
        WHERE is_approved = 1
        GROUP BY month
        ORDER BY month
    ''').fetchall()

    conn.close()

    return render_template('dashboard.html',
                           total_testimonials=total_testimonials,
                           approved_testimonials=approved_testimonials,
                           pending_testimonials=pending_testimonials,
                           countries_data=countries_data,
                           years_data=years_data,
                           monthly_data=monthly_data)

# Admin login / logout
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Credenciais inválidas!', 'error')

    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('Logout realizado com sucesso!', 'success')
    return redirect(url_for('index'))

@app.route('/admin/testimonials')
@login_required
def admin_testimonials():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    offset = (page - 1) * per_page

    conn = get_db_connection()
    testimonials = conn.execute('''
        SELECT * FROM testimonials
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    ''', (per_page, offset)).fetchall()

    total_count = conn.execute("SELECT COUNT(*) FROM testimonials").fetchone()[0]
    total_pages = (total_count + per_page - 1) // per_page

    conn.close()
    return render_template('admin_testimonials.html',
                           testimonials=testimonials,
                           page=page,
                           total_pages=total_pages)

# ajax: approve / delete
@app.route('/api/testimonial/approve/<int:testimonial_id>', methods=['POST'])
@login_required
def approve_testimonial(testimonial_id):
    conn = get_db_connection()
    conn.execute('UPDATE testimonials SET is_approved = 1 WHERE id = ?', (testimonial_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/testimonial/delete/<int:testimonial_id>', methods=['POST'])
@login_required
def delete_testimonial(testimonial_id):
    conn = get_db_connection()
    testimonial = conn.execute('SELECT video_file FROM testimonials WHERE id = ?', (testimonial_id,)).fetchone()
    if testimonial and testimonial['video_file']:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], testimonial['video_file']))
        except Exception:
            pass
    conn.execute('DELETE FROM testimonials WHERE id = ?', (testimonial_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

# Add testimonial endpoint
@app.route('/api/testimonial/add', methods=['POST'])
def add_testimonial():
    try:
        student_name = request.form['student_name']
        country = request.form['country']
        university = request.form['university']
        year = int(request.form['year'])
        testimonial_text = request.form['testimonial_text']
        video_url = request.form.get('video_url', '')
        tags = request.form.get('tags', '')

        video_filename = None
        if 'video_file' in request.files:
            video_file = request.files['video_file']
            if video_file and video_file.filename:
                safe_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{video_file.filename}"
                video_file.save(os.path.join(app.config['UPLOAD_FOLDER'], safe_name))
                video_filename = safe_name

        conn = get_db_connection()
        conn.execute('''
            INSERT INTO testimonials (student_name, country, year, testimonial_text, video_url, video_file, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (student_name, country, year, testimonial_text, video_url, video_filename, tags))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Depoimento submetido com sucesso! Aguarde aprovação.'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/add_testimonial', methods=['POST'])
def add_testimonial_route():
    return add_testimonial()

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ------------------ Game route ------------------
@app.route('/jogo')
def jogo():
    return render_template('game.html')

# ------------------ Template generator ------------------
def create_templates():
    templates_dir = 'templates'
    os.makedirs(templates_dir, exist_ok=True)

    # ---------- base.html with updated palette and fixed session checks ----------
    with open(os.path.join(templates_dir, 'base.html'), 'w', encoding='utf-8') as f:
        f.write(r'''<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Erasmus+ - Portal Digital</title>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.11.4/gsap.min.js"></script>
    <style>
        :root {
            --primary: #0066FF;      /* Azul Erasmus */
            --secondary: #FFCC00;    /* Amarelo UE */
            --accent: #00C9A7;       /* Verde moderno */
            --light: #F4F6F9;
            --dark: #1B1F3B;
            --success: #2ECC71;
            --warning: #F39C12;
            --danger: #E74C3C;
        }

        * { box-sizing: border-box; }
        html,body { height: 100%; margin: 0; font-family: 'Poppins', sans-serif; background: linear-gradient(135deg,#e9f2ff 0%, #f7fbff 100%); color: var(--dark); }

        .navbar {
            background: white;
            box-shadow: 0 6px 20px rgba(24,39,75,0.06);
            position: sticky;
            top: 0;
            z-index: 1000;
        }
        .nav-container { max-width: 1200px; margin: 0 auto; padding: 0.75rem 1rem; display:flex; align-items:center; justify-content:space-between; gap:1rem; }
        .logo { font-weight:700; color:var(--dark); text-decoration:none; font-size:1.4rem; }
        .logo span { color: var(--primary); }
        .nav-links { list-style:none; display:flex; gap:1rem; margin:0; padding:0; align-items:center;}
        .nav-links a { text-decoration:none; color:var(--dark); padding:0.5rem 0.75rem; border-radius:8px; font-weight:500; }
        .nav-links a:hover { background: rgba(0,0,0,0.04); color:var(--primary); }
        .nav-links a.active { background: linear-gradient(90deg,var(--primary), #2b8bff); color:white; }

        .main-content { padding: 2rem 1rem; max-width:1200px; margin: 0 auto; min-height: calc(100vh - 80px); }

        .hero { text-align:center; padding: 3rem 1rem; }
        .hero h1 { font-size:2.6rem; margin-bottom:0.5rem; color:var(--dark); }
        .hero p { color: #51607a; margin-bottom:1rem; }

        .btn {
            background: var(--primary);
            color: white;
            padding: 0.6rem 1rem;
            border-radius: 999px;
            border: none;
            cursor: pointer;
            font-weight:600;
            text-decoration: none;
            display:inline-block;
        }
        .btn:hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,102,255,0.12); }

        .btn-secondary { background: var(--secondary); color: var(--dark); }
        .btn-accent { background: var(--accent); color: white; }

        .card {
            background: white;
            border-radius: 12px;
            padding: 1.25rem;
            box-shadow: 0 8px 28px rgba(31,45,80,0.06);
            margin-bottom: 1.25rem;
        }

        .testimonial-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(280px,1fr)); gap:1rem; margin-top:1rem; }
        .testimonial-card { padding:1rem; border-radius:10px; background: linear-gradient(180deg, rgba(255,255,255,1), rgba(250,252,255,1)); border: 1px solid rgba(15,23,42,0.03); }

        .filter-select { padding:0.5rem 0.75rem; border-radius: 999px; border:1px solid rgba(15,23,42,0.06); background: white; }

        .form-control { width:100%; padding:0.65rem 0.9rem; border-radius:8px; border:1px solid rgba(15,23,42,0.06); background:white; }

        .video-container { border-radius:10px; overflow:hidden; margin-bottom:0.75rem; background:#000; display:block; }

        .flash-messages { position: fixed; top: 80px; right: 20px; z-index: 2000; }
        .flash-message { padding: 0.85rem 1rem; border-radius:8px; margin-bottom:0.5rem; box-shadow: 0 6px 20px rgba(8,15,30,0.06); }
        .flash-success { background: rgba(46,204,113,0.12); border:1px solid rgba(46,204,113,0.18); }
        .flash-error { background: rgba(231,76,60,0.08); border:1px solid rgba(231,76,60,0.12); }

        .stats-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); gap:1rem; }

        @media (max-width: 768px) {
            .nav-links { display:none; }
            .nav-container { justify-content:space-between; }
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="nav-container">
            <a href="{{ url_for('index') }}" class="logo">Erasmus<span>+</span></a>
            <ul class="nav-links">
                <li><a href="{{ url_for('erasmus') }}" class="{% if request.endpoint == 'erasmus' %}active{% endif %}">Erasmus</a></li>
                <li><a href="{{ url_for('europa') }}" class="{% if request.endpoint == 'europa' %}active{% endif %}">Europa</a></li>
                <li><a href="{{ url_for('cidadania') }}" class="{% if request.endpoint == 'cidadania' %}active{% endif %}">Cidadania</a></li>
                <li><a href="{{ url_for('depoimentos') }}" class="{% if request.endpoint == 'depoimentos' %}active{% endif %}">Depoimentos</a></li>
                <li><a href="{{ url_for('jogo') }}" class="{% if request.endpoint == 'jogo' %}active{% endif %}">Jogo</a></li>
                {% if session.get('user_id') and session.get('is_admin') %}
                    <li><a href="{{ url_for('dashboard') }}">Dashboard</a></li>
                    <li><a href="{{ url_for('admin_logout') }}">Logout</a></li>
                {% else %}
                    <li><a href="{{ url_for('admin_login') }}" class="{% if request.endpoint == 'admin_login' %}active{% endif %}">Admin</a></li>
                {% endif %}
            </ul>
        </div>
    </nav>

    <div class="main-content">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
            <div class="flash-messages">
                {% for category, message in messages %}
                <div class="flash-message flash-{{ category }} animate__animated animate__fadeInRight">
                    {{ message }}
                </div>
                {% endfor %}
            </div>
            {% endif %}
        {% endwith %}

        {% block content %}{% endblock %}
    </div>

    <script>
        // small animations
        gsap.from('.nav-container', {duration:0.8, y:-20, opacity:0});
    </script>
    {% block scripts %}{% endblock %}
</body>
</html>
''')

    # ---------- index.html ----------
    with open(os.path.join(templates_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(r'''{% extends "base.html" %}
{% block content %}
<div class="hero">
    <h1 class="animate__animated animate__fadeIn">Erasmus+</h1>
    <p class="animate__animated animate__fadeIn">Descobre o mundo, conecta culturas, constrói o futuro da Europa</p>
    <div style="margin-top:1rem;">
        <a href="{{ url_for('depoimentos') }}" class="btn">Ver Depoimentos</a>
        <a href="{{ url_for('erasmus') }}" class="btn btn-secondary">Saber Mais</a>
    </div>
</div>

<div class="main-content">
    <div class="card">
        <h2 style="text-align:center;">Bem-vindo ao Portal Erasmus+</h2>
        <p style="text-align:center; color:#51607a;">Um lugar para partilhar experiências, encontrar recursos e celebrar a mobilidade internacional.</p>

        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px,1fr)); gap:1rem; margin-top:1rem;">
            <div class="card" style="text-align:center;">
                <i class="fas fa-globe-europe" style="font-size:2rem; color:var(--primary);"></i>
                <h3>Mobilidade Internacional</h3>
                <p>Estuda, estagia e vive noutro país europeu.</p>
            </div>
            <div class="card" style="text-align:center;">
                <i class="fas fa-users" style="font-size:2rem; color:var(--accent);"></i>
                <h3>Comunidade</h3>
                <p>Encontra estudantes, partilha dicas e cria laços.</p>
            </div>
            <div class="card" style="text-align:center;">
                <i class="fas fa-graduation-cap" style="font-size:2rem; color:var(--secondary);"></i>
                <h3>Desenvolvimento</h3>
                <p>Ganha competências valiosas em contexto internacional.</p>
            </div>
        </div>
    </div>
</div>
{% endblock %}''')

    # ---------- erasmus.html ----------
    with open(os.path.join(templates_dir, 'erasmus.html'), 'w', encoding='utf-8') as f:
        f.write(r'''{% extends "base.html" %}
{% block content %}
<div class="hero">
    <h1>Programa Erasmus+</h1>
    <p>Transformando vidas, abrindo mentes desde 1987</p>
</div>

<div class="main-content">
    <div class="card">
        <h2>História do Erasmus</h2>
        <p>O Erasmus começou em 1987 e cresceu para abranger diversas áreas da educação, formação, juventude e desporto.</p>

        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr)); gap:1rem; margin-top:1rem;">
            <div class="card"><h4 style="color:var(--primary);">1987</h4><p>Lançamento com 11 países</p></div>
            <div class="card"><h4 style="color:var(--accent);">1995</h4><p>Expansão para o EEE</p></div>
            <div class="card"><h4 style="color:var(--secondary);">2014</h4><p>Transformação em Erasmus+</p></div>
            <div class="card"><h4 style="color:var(--primary);">2021</h4><p>Programa 2021-2027</p></div>
        </div>
    </div>
</div>
{% endblock %}''')

    # ---------- europa.html ----------
    with open(os.path.join(templates_dir, 'europa.html'), 'w', encoding='utf-8') as f:
        f.write(r'''{% extends "base.html" %}
{% block content %}
<div class="hero">
    <h1>A Europa Unida</h1>
    <p>Diversidade na unidade - construindo o futuro em conjunto</p>
</div>

<div class="main-content">
    <div class="card">
        <h2>O Projeto Europeu</h2>
        <p>A União Europeia é um processo de cooperação que promove paz, democracia e prosperidade. Erasmus+ é um dos seus pilares práticos.</p>
    </div>
</div>
{% endblock %}''')

    # ---------- cidadania.html ----------
    with open(os.path.join(templates_dir, 'cidadania.html'), 'w', encoding='utf-8') as f:
        f.write(r'''{% extends "base.html" %}
{% block content %}
<div class="hero">
    <h1>Cidadania Europeia</h1>
    <p>Direitos, responsabilidades e participação ativa na UE</p>
</div>

<div class="main-content">
    <div class="card">
        <h2>O que é a Cidadania Europeia?</h2>
        
        <P>A Cidadania Europeia é um conceito único no mundo que complementa a cidadania nacional sem a substituir. Foi estabelecida pelo Tratado de Maastricht em 1992 e representa um marco histórico na construção do projeto europeu.

        <P>📜 Origem e Fundamentos<P>
        Criada em: 1992 (Tratado de Maastricht)

        Entrou em vigor: 1 de novembro de 1993

        Base legal: Artigo 9º do Tratado da União Europeia

        Princípio fundamental: "É cidadão da União toda a pessoa que tenha a nacionalidade de um Estado-Membro"</p>
    </div>
</div>
{% endblock %}''')

    # ---------- depoimentos.html ----------
    with open(os.path.join(templates_dir, 'depoimentos.html'), 'w', encoding='utf-8') as f:
        f.write(r'''{% extends "base.html" %}
{% block content %}
<div class="hero">
    <h1>Depoimentos Erasmus</h1>
    <p>Experiências reais de estudantes</p>
</div>

<div class="main-content">
    <div class="card">
        <h3>Filtrar Depoimentos</h3>
        <form method="GET" class="card" style="display:flex; gap:0.5rem; flex-wrap:wrap; align-items:center;">
            <select name="country" class="filter-select" onchange="this.form.submit()">
                <option value="">Todos os Países</option>
                {% for country in countries %}
                <option value="{{ country.country }}" {% if current_country == country.country %}selected{% endif %}>{{ country.country }}</option>
                {% endfor %}
            </select>

            <select name="year" class="filter-select" onchange="this.form.submit()">
                <option value="">Todos os Anos</option>
                {% for year in years %}
                <option value="{{ year.year }}" {% if current_year == year.year|string %}selected{% endif %}>{{ year.year }}</option>
                {% endfor %}
            </select>

            <select name="tag" class="filter-select" onchange="this.form.submit()">
                <option value="">Todas as Tags</option>
                {% for tag in tags %}
                <option value="{{ tag }}" {% if current_tag == tag %}selected{% endif %}>{{ tag }}</option>
                {% endfor %}
            </select>

            <button type="submit" class="btn" style="margin-left:auto;">Aplicar Filtros</button>
            <a href="{{ url_for('depoimentos') }}" class="btn btn-secondary">Limpar</a>
        </form>
    </div>

    <div class="card">
        <h3>Partilha a tua experiência</h3>
        <form id="addTestimonialForm" enctype="multipart/form-data">
            <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:0.75rem;">
                <div><label>Nome</label><input class="form-control" name="student_name" required></div>
                <div><label>País</label><input class="form-control" name="country" required></div>
                <div><label>Universidade</label><input class="form-control" name="university" required></div>
                <div><label>Ano</label><input type="number" min="1987" max="2026" class="form-control" name="year" required></div>
            </div>
            <div style="margin-top:0.75rem;">
                <label>Depoimento</label>
                <textarea class="form-control" name="testimonial_text" rows="4" required></textarea>
            </div>
            <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:0.75rem; margin-top:0.75rem;">
                <div><label>URL do Vídeo</label><input class="form-control" name="video_url" placeholder="https://..."></div>
                <div><label>Ou carrega um vídeo</label><input type="file" class="form-control" name="video_file" accept="video/*"></div>
            </div>
            <div style="margin-top:0.75rem;">
                <label>Tags (vírgula)</label>
                <input class="form-control" name="tags" placeholder="cultura, amizades, aprendizagem">
            </div>
            <div style="margin-top:0.75rem;">
                <button type="submit" class="btn btn-accent">Submeter Depoimento</button>
            </div>
        </form>
    </div>

    <div class="testimonial-grid">
        {% for testimonial in testimonials %}
        <div class="testimonial-card card">
            {% if testimonial.video_url %}
                <div class="video-container">
                    {% if 'youtube' in testimonial.video_url or 'youtu.be' in testimonial.video_url %}
                        {% set vid = testimonial.video_url %}
                        {% if 'v=' in vid %}
                            {% set vid_id = vid.split('v=')[-1].split('&')[0] %}
                        {% elif 'youtu.be' in vid %}
                            {% set vid_id = vid.split('/')[-1] %}
                        {% else %}
                            {% set vid_id = '' %}
                        {% endif %}
                        {% if vid_id %}
                            <iframe src="https://www.youtube.com/embed/{{ vid_id }}" frameborder="0" allowfullscreen style="width:100%; height:220px;"></iframe>
                        {% else %}
                            <a href="{{ testimonial.video_url }}" target="_blank">{{ testimonial.video_url }}</a>
                        {% endif %}
                    {% elif 'vimeo' in testimonial.video_url %}
                        <iframe src="https://player.vimeo.com/video/{{ testimonial.video_url.split('/')[-1] }}" frameborder="0" allowfullscreen style="width:100%; height:220px;"></iframe>
                    {% else %}
                        <a href="{{ testimonial.video_url }}" target="_blank">{{ testimonial.video_url }}</a>
                    {% endif %}
                </div>
            {% elif testimonial.video_file %}
                <div class="video-container">
                    <video controls style="width:100%; height:220px;">
                        <source src="{{ url_for('uploaded_file', filename=testimonial.video_file) }}">
                        O teu browser não suporta vídeo.
                    </video>
                </div>
            {% endif %}

            <h4>{{ testimonial.student_name }}</h4>
            <p><strong>{{ testimonial.university }}</strong>, {{ testimonial.country }} ({{ testimonial.year }})</p>
            <p>{{ testimonial.testimonial_text }}</p>
            {% if testimonial.tags %}
                <div style="margin-top:0.5rem;">
                    {% for tag in testimonial.tags.split(',') %}
                        <span style="background:var(--primary); color:white; padding:0.25rem 0.5rem; border-radius:12px; font-size:0.8rem; margin-right:0.25rem;">{{ tag.strip() }}</span>
                    {% endfor %}
                </div>
            {% endif %}
        </div>
        {% else %}
        <div class="card" style="grid-column:1/-1; text-align:center;">
            <h3>Nenhum depoimento encontrado</h3>
            <p>Sê o primeiro a partilhar a tua experiência!</p>
        </div>
        {% endfor %}
    </div>

    {% if total_pages > 1 %}
    <div style="text-align:center; margin-top:1rem;">
        {% for p in range(1, total_pages+1) %}
            <a href="{{ url_for('depoimentos', page=p, country=current_country, year=current_year, tag=current_tag) }}" class="btn" style="margin:0.25rem;">{{ p }}</a>
        {% endfor %}
    </div>
    {% endif %}
</div>

<script>
document.getElementById('addTestimonialForm').addEventListener('submit', async function(e){
    e.preventDefault();
    const fd = new FormData(this);
    try {
        const res = await fetch('/api/testimonial/add', { method: 'POST', body: fd });
        const r = await res.json();
        if (r.success) {
            alert(r.message || 'Submetido! Aguarde aprovação.');
            this.reset();
        } else {
            alert('Erro: ' + (r.message || 'erro desconhecido'));
        }
    } catch (err) {
        alert('Erro de rede: ' + err.message);
    }
});
</script>
{% endblock %}''')

    # ---------- dashboard.html ----------
    with open(os.path.join(templates_dir, 'dashboard.html'), 'w', encoding='utf-8') as f:
        f.write(r'''{% extends "base.html" %}
{% block content %}
<div class="hero">
    <h1>Dashboard de Administração</h1>
    <p>Gerir depoimentos e visualizar estatísticas</p>
</div>

<div class="main-content">
    <div class="stats-grid">
        <div class="card" style="background:linear-gradient(90deg,var(--primary), #2b8bff); color:white;">
            <div style="font-size:1.6rem; font-weight:700;">{{ total_testimonials }}</div>
            <div>Total Depoimentos</div>
        </div>
        <div class="card" style="background:linear-gradient(90deg,var(--success), #2ecc71); color:white;">
            <div style="font-size:1.6rem; font-weight:700;">{{ approved_testimonials }}</div>
            <div>Aprovados</div>
        </div>
        <div class="card" style="background:linear-gradient(90deg,var(--warning), #f0ad4e); color:white;">
            <div style="font-size:1.6rem; font-weight:700;">{{ pending_testimonials }}</div>
            <div>Pendentes</div>
        </div>
        <div class="card" style="background:linear-gradient(90deg,var(--secondary), #ffd24d); color:var(--dark);">
            <div style="font-size:1.6rem; font-weight:700;">{{ (approved_testimonials/total_testimonials*100 if total_testimonials>0 else 0)|round(1) }}%</div>
            <div>Taxa de Aprovação</div>
        </div>
    </div>

    <div class="card" style="margin-top:1rem;">
        <h3>Ações Rápidas</h3>
        <div style="display:flex; gap:0.5rem; flex-wrap:wrap;">
            <a href="{{ url_for('admin_testimonials') }}" class="btn">Gerir Depoimentos</a>
            <a href="{{ url_for('depoimentos') }}" class="btn btn-secondary">Ver Site Público</a>
            <a href="{{ url_for('admin_logout') }}" class="btn" style="background:var(--danger);">Logout</a>
        </div>
    </div>

    <div class="card" style="margin-top:1rem;">
        <h3>Estatísticas por País</h3>
        <canvas id="countriesChart" width="400" height="150"></canvas>
    </div>

    <div style="display:grid; grid-template-columns: repeat(auto-fit,minmax(300px,1fr)); gap:1rem; margin-top:1rem;">
        <div class="card">
            <h3>Distribuição por Ano</h3>
            <canvas id="yearsChart" width="400" height="200"></canvas>
        </div>
        <div class="card">
            <h3>Submissões Mensais</h3>
            <canvas id="monthlyChart" width="400" height="200"></canvas>
        </div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
const countriesLabels = [{% for c in countries_data %}'{{ c.country }}',{% endfor %}];
const countriesValues = [{% for c in countries_data %}{{ c.count }},{% endfor %}];

const ctx1 = document.getElementById('countriesChart').getContext('2d');
new Chart(ctx1, {
    type: 'bar',
    data: { labels: countriesLabels, datasets: [{ label: 'Depoimentos', data: countriesValues }]},
    options: { responsive:true, scales:{ y:{ beginAtZero:true } } }
});

const yearsLabels = [{% for y in years_data %}'{{ y.year }}',{% endfor %}];
const yearsValues = [{% for y in years_data %}{{ y.count }},{% endfor %}];
const ctx2 = document.getElementById('yearsChart').getContext('2d');
new Chart(ctx2, { type:'line', data:{ labels:yearsLabels, datasets:[{ label:'Por ano', data:yearsValues, fill:true }]}, options:{ responsive:true }});

const monthsLabels = [{% for m in monthly_data %}'{{ m.month }}',{% endfor %}];
const monthsValues = [{% for m in monthly_data %}{{ m.count }},{% endfor %}];
const ctx3 = document.getElementById('monthlyChart').getContext('2d');
new Chart(ctx3, { type:'bar', data:{ labels:monthsLabels, datasets:[{ label:'Submissões', data:monthsValues }]}, options:{ responsive:true }});
</script>
{% endblock %}''')

    # ---------- admin_login.html ----------
    with open(os.path.join(templates_dir, 'admin_login.html'), 'w', encoding='utf-8') as f:
        f.write(r'''{% extends "base.html" %}
{% block content %}
<div class="hero">
    <h1>Área de Administração</h1>
    <p>Acesso restrito</p>
</div>

<div class="main-content">
    <div class="card" style="max-width:420px; margin:0 auto;">
        <h3 style="text-align:center;">Login</h3>
        <form method="POST">
            <div style="margin-bottom:0.6rem;"><label>Username</label><input name="username" class="form-control" required></div>
            <div style="margin-bottom:0.6rem;"><label>Password</label><input type="password" name="password" class="form-control" required></div>
            <button class="btn" style="width:100%;">Entrar</button>
        </form>

        <div style="margin-top:1rem; padding:0.75rem; background:#fff8e6; border-radius:8px;">
            <strong>Credenciais padrão:</strong>
            <p>Username: <strong>admin</strong><br>Password: <strong>admin123</strong></p>
            <small style="color:var(--warning);">Altera a password em ambiente de produção!</small>
        </div>
    </div>
</div>
{% endblock %}''')

    # ---------- admin_testimonials.html ----------
    with open(os.path.join(templates_dir, 'admin_testimonials.html'), 'w', encoding='utf-8') as f:
        f.write(r'''{% extends "base.html" %}
{% block content %}
<div class="hero">
    <h1>Gerir Depoimentos</h1>
    <p>Aprovar, editar ou remover</p>
</div>

<div class="main-content">
    <div class="card">
        <a href="{{ url_for('dashboard') }}" class="btn btn-secondary">Voltar ao Dashboard</a>
    </div>

    <div style="display:grid; gap:1rem;">
        {% for testimonial in testimonials %}
        <div class="card" id="testimonial-{{ testimonial.id }}">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div><h4>{{ testimonial.student_name }}</h4><small>{{ testimonial.university }} — {{ testimonial.country }} ({{ testimonial.year }})</small></div>
                <div>
                    <span style="padding:0.3rem 0.55rem; border-radius:12px; background:{% if testimonial.is_approved %}var(--success){% else %}var(--warning){% endif %}; color:white;">
                        {% if testimonial.is_approved %}Aprovado{% else %}Pendente{% endif %}
                    </span>
                </div>
            </div>
            <p style="margin-top:0.5rem;">{{ testimonial.testimonial_text }}</p>

            <div style="display:flex; gap:0.5rem; margin-top:0.75rem;">
                {% if not testimonial.is_approved %}
                <button class="btn" onclick="approveTestimonial({{ testimonial.id }})">Aprovar</button>
                {% endif %}
                <button class="btn" style="background:var(--danger);" onclick="deleteTestimonial({{ testimonial.id }})">Remover</button>
            </div>
        </div>
        {% else %}
        <div class="card">Nenhum depoimento encontrado</div>
        {% endfor %}
    </div>

    {% if total_pages > 1 %}
    <div style="text-align:center; margin-top:1rem;">
        {% for p in range(1, total_pages+1) %}
        <a href="{{ url_for('admin_testimonials', page=p) }}" class="btn" style="margin:0.25rem;">{{ p }}</a>
        {% endfor %}
    </div>
    {% endif %}
</div>

<script>
async function approveTestimonial(id){
    if(!confirm('Aprovar este depoimento?')) return;
    try {
        const res = await fetch(`/api/testimonial/approve/${id}`, { method:'POST' });
        const r = await res.json();
        if(r.success) { location.reload(); } else alert('Erro ao aprovar');
    } catch(e){ alert('Erro de rede'); }
}
async function deleteTestimonial(id){
    if(!confirm('Remover este depoimento? Não pode ser desfeito.')) return;
    try {
        const res = await fetch(`/api/testimonial/delete/${id}`, { method:'POST' });
        const r = await res.json();
        if(r.success) { document.getElementById('testimonial-'+id).remove(); } else alert('Erro ao remover');
    } catch(e){ alert('Erro de rede'); }
}
</script>
{% endblock %}''')

    # ---------- game.html ----------
    with open(os.path.join(templates_dir, 'game.html'), 'w', encoding='utf-8') as f:
        f.write(r'''{% extends "base.html" %}
{% block content %}
<div class="hero">
    <h1>🎮 Jogo: Adivinha a Bandeira</h1>
    <p>Tenta adivinhar o país pela bandeira — escreve o nome e verifica!</p>
</div>

<div class="main-content">
    <div class="card" style="text-align:center;">
        <img id="flag" src="" alt="Bandeira" style="width:260px; border-radius:8px; border:1px solid rgba(0,0,0,0.06);">
        <div style="margin-top:1rem;">
            <input id="guess" class="form-control" placeholder="Escreve o país (ex: Portugal)" style="max-width:420px; margin:0.6rem auto;">
            <div style="display:flex; gap:0.5rem; justify-content:center;">
                <button class="btn" onclick="checkGuess()">Verificar</button>
                <button class="btn btn-accent" onclick="nextFlag()">Próxima</button>
            </div>
            <p id="result" style="margin-top:0.8rem; font-weight:700;"></p>
        </div>
        <div style="margin-top:0.8rem;">
            <small>Dicas: aceita acentos e variantes, p.ex. 'Reino Unido' / 'United Kingdom' não estão incluidos por defeito.</small>
        </div>
    </div>
</div>

<script>
const flags = [
    { country: "Portugal", flag: "https://flagcdn.com/w320/pt.png", aliases:["portugal"] },
    { country: "Espanha", flag: "https://flagcdn.com/w320/es.png", aliases:["espanha","spain"] },
    { country: "França", flag: "https://flagcdn.com/w320/fr.png", aliases:["frança","franca","france"] },
    { country: "Itália", flag: "https://flagcdn.com/w320/it.png", aliases:["itália","italia","italy"] },
    { country: "Alemanha", flag: "https://flagcdn.com/w320/de.png", aliases:["alemanha","germany","deutschland"] },
    { country: "Polónia", flag: "https://flagcdn.com/w320/pl.png", aliases:["polónia","polonia","poland"] },
    { country: "Grécia", flag: "https://flagcdn.com/w320/gr.png", aliases:["grécia","grecia","greece"] },
    { country: "Suécia", flag: "https://flagcdn.com/w320/se.png", aliases:["suécia","suecia","sweden"] },
    { country: "Irlanda", flag: "https://flagcdn.com/w320/ie.png", aliases:["irlanda","ireland"] }
];

let currentFlag = null;

function normalize(text) {
    return text.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').trim();
}

function nextFlag() {
    const idx = Math.floor(Math.random() * flags.length);
    currentFlag = flags[idx];
    document.getElementById('flag').src = currentFlag.flag;
    document.getElementById('guess').value = '';
    document.getElementById('result').textContent = '';
}

function checkGuess() {
    const val = normalize(document.getElementById('guess').value || '');
    if(!val) { alert('Escreve o nome do país'); return; }
    const ok = currentFlag.aliases.map(normalize).includes(val) || normalize(currentFlag.country) === val;
    if(ok) {
        document.getElementById('result').textContent = '✅ Correto! É ' + currentFlag.country;
        document.getElementById('result').style.color = 'var(--success)';
    } else {
        document.getElementById('result').textContent = '❌ Errado — era ' + currentFlag.country;
        document.getElementById('result').style.color = 'var(--danger)';
    }
}

nextFlag();
</script>
{% endblock %}''')

# end create_templates
create_templates()

if __name__ == '__main__':
    print("🚀 Iniciando servidor Erasmus+...")
    print("📊 Base de dados inicializada (se necessário).")
    print("🎨 Templates criados (templates/).")
    print("🔐 Admin: username='admin', password='admin123' — altera em produção!")
    app.run(debug=True, host='0.0.0.0', port=5000)

