from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_mail import Mail, Message
from groq import Groq
from hindsight_client import Hindsight
import random, time, os, bcrypt, json, pathlib

app = Flask(__name__)
CORS(app)

# ── Email config ──────────────────────────────────────────────────────────────
app.config['MAIL_SERVER']         = 'smtp.gmail.com'
app.config['MAIL_PORT']           = 587
app.config['MAIL_USE_TLS']        = True
app.config['MAIL_USERNAME']       = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD']       = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', '')
mail = Mail(app)

# ── API Keys ──────────────────────────────────────────────────────────────────
GROQ_KEY = os.environ.get('GROQ_KEY', '')
HS_KEY   = os.environ.get('HINDSIGHT_KEY', '')
HS_BANK  = os.environ.get('HINDSIGHT_BANK', 'newmemo')

groq_client = Groq(api_key=GROQ_KEY)

# ── User database ─────────────────────────────────────────────────────────────
otp_store = {}
DB_FILE   = os.environ.get('DB_PATH', 'users.json')

def load_users():
    try:
        if pathlib.Path(DB_FILE).exists():
            with open(DB_FILE, 'r') as f:
                return json.load(f)
    except: pass
    return {}

def save_users(users):
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        print(f"Save users error: {e}")

user_store = load_users()
print(f"📂 Loaded {len(user_store)} users from database")

# ── Level definitions ─────────────────────────────────────────────────────────
LEVELS = {
    "Beginner": {
        "Easy":   {"desc":"Print, variables, basic if/else, simple math",      "example":"Print 1-10",           "topics":["Print/Output","Variables","Basic Math","Simple Conditions","Input/Output"]},
        "Medium": {"desc":"Loops, lists, if/else chains",                       "example":"Find largest in list", "topics":["Loops","Lists","Conditions","Basic Functions","String basics"]},
        "Hard":   {"desc":"Nested loops, string manipulation",                  "example":"Reverse string",       "topics":["Nested Loops","Strings","Pattern Printing","List Operations"]}
    },
    "Intermediate": {
        "Easy":   {"desc":"Sorting, searching, simple recursion, dicts",        "example":"Binary search",        "topics":["Sorting","Searching","Recursion","Dictionaries","Functions"]},
        "Medium": {"desc":"Stacks, queues, linked lists, string algorithms",    "example":"Valid parentheses",    "topics":["Stacks","Queues","Linked Lists","String Algorithms","Two Pointers"]},
        "Hard":   {"desc":"Trees, hash maps, sliding window, basic DP",         "example":"Tree traversal",       "topics":["Trees","Hash Maps","Sliding Window","Dynamic Programming"]}
    },
    "Advanced": {
        "Easy":   {"desc":"Graphs, advanced DP, backtracking",                  "example":"BFS/DFS",              "topics":["Graphs","BFS/DFS","Advanced DP","Backtracking"]},
        "Medium": {"desc":"Complex graphs, advanced DP, caching",               "example":"Dijkstra's, LRU",      "topics":["Shortest Path","Advanced DP","Caching","Complex Data Structures"]},
        "Hard":   {"desc":"Hard optimization, multiple algorithms combined",    "example":"Merge k sorted lists", "topics":["Complex Optimization","Multiple Algorithms","System Design","Hard Graph Problems"]}
    }
}

# ── Hindsight helpers ─────────────────────────────────────────────────────────
def get_hs_client():
    return Hindsight(
        base_url='https://api.hindsight.vectorize.io',
        api_key=HS_KEY
    )

def hs_retain(email, content):
    try:
        result = get_hs_client().retain(bank_id=HS_BANK, content=content, tags=[email])
        print(f"✅ Hindsight retain: success={result.success} for {email}")
        return result.success
    except Exception as e:
        print(f"Hindsight retain error: {e}")
        return False

def hs_recall(email, query):
    try:
        result = get_hs_client().recall(bank_id=HS_BANK, query=query, tags=[email])
        if result.results:
            memory = "\n".join([r.text for r in result.results])
            print(f"🧠 Hindsight recalled {len(result.results)} memories for {email}")
            return memory
        return None
    except Exception as e:
        print(f"Hindsight recall error: {e}")
        return None

# ── AI helper ─────────────────────────────────────────────────────────────────
def ask_ai(prompt):
    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1000, temperature=0.9)
    return r.choices[0].message.content

# ── Email helper ──────────────────────────────────────────────────────────────
def send_otp_email(email, otp, is_register=True):
    subject = "🚀 Welcome to CodeBuddy AI — Verify your email" if is_register else "🔑 CodeBuddy AI — Your login OTP"
    body = f"""Hi there!

{"Welcome to CodeBuddy AI! 🎉" if is_register else "Here is your login OTP:"}

Your one-time password is:

    {otp}

This code expires in 5 minutes.

Happy coding! 💻
— CodeBuddy AI Team"""
    try:
        msg = Message(subject=subject, sender=app.config['MAIL_USERNAME'], recipients=[email], body=body)
        mail.send(msg)
        print(f"📧 OTP sent to {email}")
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

@app.route('/health')
def health():
    return jsonify({"status": "CodeBuddy AI running!"})

# ════════════════════════════════════════════════════════════
# REGISTER
# ════════════════════════════════════════════════════════════

@app.route('/api/register/send-otp', methods=['POST'])
def register_send_otp():
    email = request.json.get('email', '').strip().lower()
    if not email or '@' not in email:
        return jsonify({"error": "Invalid email"}), 400
    if email in user_store:
        return jsonify({"error": "Account already exists! Please login instead."}), 400
    otp = str(random.randint(100000, 999999))
    otp_store[email] = {"otp": otp, "expires_at": time.time() + 300}
    if send_otp_email(email, otp, is_register=True):
        return jsonify({"success": True, "message": "OTP sent!"})
    return jsonify({"error": "Failed to send email"}), 500

@app.route('/api/register/verify-otp', methods=['POST'])
def register_verify_otp():
    email  = request.json.get('email', '').strip().lower()
    otp    = request.json.get('otp', '').strip()
    record = otp_store.get(email)
    if not record:
        return jsonify({"success": False, "error": "No OTP found. Request a new one."}), 400
    if time.time() > record['expires_at']:
        del otp_store[email]
        return jsonify({"success": False, "error": "OTP expired."}), 400
    if record['otp'] != otp:
        return jsonify({"success": False, "error": "Incorrect OTP."}), 400
    del otp_store[email]
    return jsonify({"success": True})

@app.route('/api/register/complete', methods=['POST'])
def register_complete():
    data     = request.json
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    level    = data.get('level', 'Beginner')
    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    if email in user_store:
        return jsonify({"error": "Account already exists!"}), 400
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_store[email] = {"password_hash": hashed, "level": level, "created_at": time.time()}
    save_users(user_store)
    print(f"✅ Registered: {email} as {level}")
    hs_retain(email, f"USER_ACCOUNT|email:{email}|hash:{hashed}|level:{level}")
    hs_retain(email, f"New user registered. Email: {email}. Level: {level}. Joined: {time.strftime('%Y-%m-%d')}.")
    return jsonify({"success": True, "message": "Account created!"})

# ════════════════════════════════════════════════════════════
# LOGIN
# ════════════════════════════════════════════════════════════

@app.route('/api/login', methods=['POST'])
def login():
    data     = request.json
    email    = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    if not email or not password:
        return jsonify({"success": False, "error": "Email and password required"}), 400
    user = user_store.get(email)
    if not user:
        print(f"🔍 User not in local DB, checking Hindsight for {email}...")
        memory = hs_recall(email, "USER_ACCOUNT email password hash level")
        if memory:
            for line in memory.split('\n'):
                if 'USER_ACCOUNT' in line and f'email:{email}' in line:
                    try:
                        parts = dict(p.split(':', 1) for p in line.split('|')[1:])
                        user = {'password_hash': parts.get('hash', ''), 'level': parts.get('level', 'Beginner')}
                        user_store[email] = user
                        save_users(user_store)
                        print(f"♻️ Restored user from Hindsight: {email}")
                        break
                    except Exception as e:
                        print(f"Restore error: {e}")
    if not user:
        return jsonify({"success": False, "error": "No account found. Please register first."}), 404
    if not bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
        return jsonify({"success": False, "error": "Incorrect password."}), 401
    print(f"✅ Login: {email}")
    return jsonify({"success": True, "level": user['level'], "email": email})

# ════════════════════════════════════════════════════════════
# GENERATE QUESTION
# ════════════════════════════════════════════════════════════

@app.route('/api/generate-question', methods=['POST'])
def generate_question():
    data       = request.json
    email      = data.get('email', 'guest')
    level      = data.get('level', 'Beginner')
    difficulty = data.get('difficulty', 'Easy')
    topic      = data.get('topic', '')
    language   = data.get('language', 'Python')
    diff_def = LEVELS.get(level, LEVELS["Beginner"]).get(difficulty, LEVELS["Beginner"]["Easy"])
    if not topic:
        memory = hs_recall(email, f"what {level} level topics does this student struggle with and score poorly on?")
        if memory:
            weak  = [t for t in diff_def["topics"] if t.lower() in memory.lower()]
            topic = weak[0] if weak else random.choice(diff_def["topics"])
        else:
            topic = random.choice(diff_def["topics"])
    seeds = [
        "with a fun real-world scenario like food, travel, games, or animals",
        "with a creative story context that makes it interesting",
        "that a student would find relatable and enjoyable",
        "that teaches an important concept in a memorable way",
        "with a unique twist that makes it stand out",
    ]
    prompt = f"""You are a coding teacher creating a practice problem.

Student level: {level}
Difficulty within {level}: {difficulty}
Topic: {topic}
Language: {language}

WHAT {level} {difficulty} MEANS:
{diff_def['desc']}
Example of correct difficulty: {diff_def['example']}

CRITICAL RULES:
- Problem MUST match exactly {level} {difficulty} — do NOT make harder
- A {level} student should be able to solve this
- Be UNIQUE and CREATIVE — different every time
- Make it {random.choice(seeds)}

Format EXACTLY like this:
TITLE: [creative title]
TOPIC: {topic}

PROBLEM:
[2-3 clear sentences]

EXAMPLE:
Input: [example]
Output: [output]

CONSTRAINTS:
- [1 appropriate constraint]"""

    question = ask_ai(prompt)
    return jsonify({"question": question, "topic": topic, "difficulty": difficulty, "language": language, "level": level})

# ════════════════════════════════════════════════════════════
# EVALUATE CODE
# ════════════════════════════════════════════════════════════

@app.route('/api/evaluate', methods=['POST'])
def evaluate_code():
    data       = request.json
    email      = data.get('email', 'guest')
    question   = data.get('question', '')
    code       = data.get('code', '')
    topic      = data.get('topic', '')
    difficulty = data.get('difficulty', '')
    language   = data.get('language', 'Python')
    level      = data.get('level', 'Beginner')
    if not code or not question:
        return jsonify({"error": "Missing code or question"}), 400
    memory = hs_recall(email, "what mistakes has this student made before? what topics they struggle with?")
    prompt = f"""You are a kind coding mentor evaluating a {level} level student.

QUESTION:
{question}

STUDENT'S {language} CODE:
{code}

{"STUDENT HISTORY:\n" + memory if memory else "This is their first session — be extra encouraging!"}

Remember: Evaluate for {level} {difficulty} level — don't expect advanced techniques!

Reply in EXACTLY this format:
SCORE: [0-100]

WHAT YOU DID WELL:
[2-3 specific things they got right]

WHAT TO IMPROVE:
[2-3 specific actionable improvements for {level} level]

MENTOR TIP:
[One encouraging next step]

Be warm, specific, constructive. Max 200 words."""

    feedback = ask_ai(prompt)
    score = 50
    for line in feedback.split('\n'):
        if line.strip().startswith('SCORE:'):
            try: score = int(line.replace('SCORE:', '').strip())
            except: pass
    mem = f"Student {email} is {level} level. Practiced {topic} ({difficulty}) in {language}. Score: {score}/100. {'Struggled significantly.' if score < 50 else 'Made some errors.' if score < 70 else 'Did well.'} Feedback: {feedback[:300]}"
    hs_retain(email, mem)
    return jsonify({"feedback": feedback, "score": score, "should_suggest_level_up": score >= 70 and difficulty == 'Hard'})

# ════════════════════════════════════════════════════════════
# SEND TEAM FEEDBACK
# ════════════════════════════════════════════════════════════

@app.route('/api/send-feedback', methods=['POST'])
def send_feedback():
    data     = request.json
    email    = data.get('email', 'unknown')
    message  = data.get('message', '')
    sessions = data.get('totalSolved', 0)
    level    = data.get('level', 'Unknown')
    if not message.strip():
        return jsonify({"error": "Message is empty"}), 400
    team_emails = [os.environ.get('MAIL_USERNAME', '')]
    try:
        msg = Message(
            subject=f"CodeBuddy Feedback from {email}",
            sender=app.config['MAIL_USERNAME'],
            recipients=team_emails,
            body=f"""New feedback received!

User     : {email}
Level    : {level}
Sessions : {sessions}

Message:
{message}

---
Sent from CodeBuddy AI""")
        mail.send(msg)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("🚀 CodeBuddy AI at http://localhost:5000")
    app.run(debug=True, port=5000)