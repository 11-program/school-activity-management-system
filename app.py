from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# 初始化数据库
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        location TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        max_participants INTEGER DEFAULT 20,
        teacher_id INTEGER NOT NULL,
        FOREIGN KEY (teacher_id) REFERENCES users (id)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        activity_id INTEGER NOT NULL,
        register_time TEXT NOT NULL,
        FOREIGN KEY (student_id) REFERENCES users (id),
        FOREIGN KEY (activity_id) REFERENCES activities (id),
        UNIQUE(student_id, activity_id)
    )''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    return '<h1>校园活动管理系统 V1.0 运行正常！</h1><p>访问 <a href=" ">/register</a > 注册，或 <a href="/login">/login</a > 登录</p >'

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form['role']
        password_hash = generate_password_hash(password)
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                     (username, password_hash, role))
            conn.commit()
            conn.close()
            return '<h3>注册成功！<a href="/login">去登录</a ></h3>'
        except sqlite3.IntegrityError:
            conn.close()
            return '<h3>用户名已存在！<a href="/register">重新注册</a ></h3>'
    
    return '''
    <h2>注册</h2>
    <form method="POST">
        用户名: <input type="text" name="username" required><br>
        密码: <input type="password" name="password" required><br>
        角色: <select name="role">
            <option value="student">学生</option>
            <option value="teacher">教师</option>
        </select><br>
        <input type="submit" value="注册">
    </form>
    <p><a href="/login">已有账号？去登录</a ></p >
    '''

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT id, username, password_hash, role FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['role'] = user[3]
            return f'<h3>登录成功！欢迎 {username}！<a href="/">返回首页</a ></h3>'
        return '<h3>用户名或密码错误！<a href="/login">重新登录</a ></h3>'
    
    return '''
    <h2>登录</h2>
    <form method="POST">
        用户名: <input type="text" name="username" required><br>
        密码: <input type="password" name="password" required><br>
        <input type="submit" value="登录">
    </form>
    <p><a href="/register">没有账号？去注册</a ></p >
    '''

if __name__ == '__main__':
    app.run(debug=True)