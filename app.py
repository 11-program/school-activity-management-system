from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime

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

# 辅助函数：判断活动是否已结束
def is_activity_ended(end_time_str):
    try:
        end_time = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        try:
            end_time = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return False
    return datetime.now() > end_time

@app.route('/')
def index():
    return '<h1>校园活动管理系统 V1.0 运行正常</h1><p><a href="/register">注册</a> | <a href="/login">登录</a> | <a href="/activities">活动列表</a></p>'

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
            return '<h3>注册成功！<a href="/login">去登录</a></h3>'
        except sqlite3.IntegrityError:
            conn.close()
            return '<h3>用户名已存在！<a href="/register">重新注册</a></h3>'
    
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
    <p><a href="/login">已有账号？去登录</a></p>
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
            return redirect(url_for('dashboard'))
        return '<h3>用户名或密码错误！<a href="/login">重新登录</a></h3>'
    
    return '''
    <h2>登录</h2>
    <form method="POST">
        用户名: <input type="text" name="username" required><br>
        密码: <input type="password" name="password" required><br>
        <input type="submit" value="登录">
    </form>
    <p><a href="/register">没有账号？去注册</a></p>
    '''

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    role_text = '学生' if session.get('role') == 'student' else '教师'
    nav_links = '<a href="/activities">活动列表</a>'
    if session.get('role') == 'teacher':
        nav_links += ' | <a href="/create_activity">发布活动</a>'
    nav_links += ' | <a href="/my_activities">我的活动</a>'
    nav_links += ' | <a href="/logout">退出登录</a>'
    return f'''
    <h1>欢迎，{session['username']}！</h1>
    <p>角色：{role_text}</p>
    <p>{nav_links}</p>
    '''

# 发布活动（教师）
@app.route('/create_activity', methods=['GET', 'POST'])
def create_activity():
    if 'username' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'teacher':
        return '<h3>只有教师可以发布活动！<a href="/dashboard">返回</a></h3>'
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        location = request.form['location']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        max_participants = request.form['max_participants']
        teacher_id = session['user_id']
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("""INSERT INTO activities (title, description, location, start_time, end_time, max_participants, teacher_id)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (title, description, location, start_time, end_time, max_participants, teacher_id))
        conn.commit()
        conn.close()
        return '<h3>活动发布成功！<a href="/activities">查看活动列表</a></h3>'
    
    return '''
    <h2>发布活动</h2>
    <form method="POST">
        活动标题: <input type="text" name="title" required><br><br>
        活动描述: <textarea name="description" rows="4" cols="30"></textarea><br><br>
        活动地点: <input type="text" name="location" required><br><br>
        开始时间: <input type="datetime-local" name="start_time" required><br><br>
        结束时间: <input type="datetime-local" name="end_time" required><br><br>
        最大参与人数: <input type="number" name="max_participants" value="20" min="1" required><br><br>
        <input type="submit" value="发布">
    </form>
    <p><a href="/dashboard">返回仪表盘</a></p>
    '''

# 活动详情页
@app.route('/activity/<int:activity_id>')
def activity_detail(activity_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 获取活动信息
    c.execute("""SELECT a.id, a.title, a.description, a.location, a.start_time, a.end_time,
                        a.max_participants, a.teacher_id, u.username as teacher_name
                 FROM activities a JOIN users u ON a.teacher_id = u.id
                 WHERE a.id = ?""", (activity_id,))
    activity = c.fetchone()
    
    if not activity:
        conn.close()
        return '<h3>活动不存在！<a href="/activities">返回活动列表</a></h3>'
    
    # 获取报名人数
    c.execute("SELECT COUNT(*) FROM registrations WHERE activity_id = ?", (activity_id,))
    reg_count = c.fetchone()[0]
    
    # 获取已报名学生名单（仅姓名）
    c.execute("""SELECT u.username FROM registrations r
                 JOIN users u ON r.student_id = u.id
                 WHERE r.activity_id = ?
                 ORDER BY r.register_time ASC""", (activity_id,))
    students = c.fetchall()
    
    # 判断状态
    is_full = reg_count >= activity[6]
    is_ended = is_activity_ended(activity[5])
    
    # 检查当前学生是否已报名
    registered = False
    if session.get('role') == 'student':
        c.execute("SELECT 1 FROM registrations WHERE activity_id = ? AND student_id = ?",
                 (activity_id, session['user_id']))
        registered = c.fetchone() is not None
    
    conn.close()
    
    # 状态标签
    status_tags = ''
    if is_ended:
        status_tags += '<span style="background:#888;color:#fff;padding:2px 8px;border-radius:3px;margin-right:5px;">已结束</span>'
    if is_full:
        status_tags += '<span style="background:#e74c3c;color:#fff;padding:2px 8px;border-radius:3px;">已满员</span>'
    
    html = f'<h2>{activity[1]} {status_tags}</h2>'
    html += '<p><a href="/activities">返回活动列表</a></p>'
    html += f'''
    <div style="border:1px solid #ccc; padding:15px; margin:10px 0; border-radius:5px;">
        <p><b>活动描述：</b>{activity[2] or '无'}</p>
        <p><b>活动地点：</b>{activity[3]}</p>
        <p><b>开始时间：</b>{activity[4]}</p>
        <p><b>结束时间：</b>{activity[5]}</p>
        <p><b>发布教师：</b>{activity[8]}</p>
        <p><b>报名人数：</b>{reg_count} / {activity[6]}</p>
    '''
    # 报名按钮（仅学生）
    if session.get('role') == 'student':
        if registered:
            html += '<p style="color:green;">你已报名</p>'
        elif is_full:
            html += '<p style="color:red;">活动已满</p>'
        elif is_ended:
            html += '<p style="color:gray;">活动已结束，无法报名</p>'
        else:
            html += f'<a href="/register_activity/{activity[0]}">立即报名</a>'
    html += '</div>'
    
    # 已报名学生名单
    html += f'<h3>已报名学生（{reg_count}人）</h3>'
    if not students:
        html += '<p>暂无学生报名</p>'
    else:
        html += '<ul>'
        for s in students:
            html += f'<li>{s[0]}</li>'
        html += '</ul>'
    
    return html

# 活动列表
@app.route('/activities')
def activities():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("""SELECT a.id, a.title, a.description, a.location, a.start_time, a.end_time, 
                        a.max_participants, a.teacher_id, u.username as teacher_name
                 FROM activities a JOIN users u ON a.teacher_id = u.id
                 ORDER BY a.start_time ASC""")
    activity_list = c.fetchall()
    
    activity_data = []
    for act in activity_list:
        c.execute("SELECT COUNT(*) FROM registrations WHERE activity_id = ?", (act[0],))
        count = c.fetchone()[0]
        registered = False
        if session.get('role') == 'student':
            c.execute("SELECT 1 FROM registrations WHERE activity_id = ? AND student_id = ?",
                     (act[0], session['user_id']))
            registered = c.fetchone() is not None
        is_ended = is_activity_ended(act[5])
        activity_data.append({
            'id': act[0],
            'title': act[1],
            'description': act[2],
            'location': act[3],
            'start_time': act[4],
            'end_time': act[5],
            'max_participants': act[6],
            'teacher_id': act[7],
            'teacher_name': act[8],
            'registered_count': count,
            'is_full': count >= act[6],
            'is_ended': is_ended,
            'registered': registered
        })
    conn.close()
    
    html = '<h2>活动列表</h2>'
    html += '<p><a href="/dashboard">返回仪表盘</a></p>'
    
    if not activity_data:
        html += '<p>暂无活动</p>'
    else:
        for act in activity_data:
            # 状态标签
            status_tags = ''
            if act['is_ended']:
                status_tags += '<span style="background:#888;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;margin-right:5px;">已结束</span>'
            if act['is_full']:
                status_tags += '<span style="background:#e74c3c;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;">已满员</span>'
            
            html += f'''
            <div style="border:1px solid #ccc; padding:10px; margin:10px 0; border-radius:5px;">
                <h3><a href="/activity/{act["id"]}">{act["title"]}</a> {status_tags}</h3>
                <p><b>描述：</b>{act["description"] or '无'}</p>
                <p><b>地点：</b>{act["location"]}</p>
                <p><b>时间：</b>{act["start_time"]} ~ {act["end_time"]}</p>
                <p><b>发布教师：</b>{act["teacher_name"]}</p>
                <p><b>报名人数：</b>{act["registered_count"]} / {act["max_participants"]}</p>
            '''
            if session.get('role') == 'student':
                if act['registered']:
                    html += '<p style="color:green;">已报名</p>'
                elif act['is_full']:
                    html += '<p style="color:red;">已满</p>'
                elif act['is_ended']:
                    html += '<p style="color:gray;">已结束</p>'
                else:
                    html += f'<a href="/register_activity/{act["id"]}">报名</a>'
            html += '</div>'
    
    return html

# 报名活动（学生）
@app.route('/register_activity/<int:activity_id>')
def register_activity(activity_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'student':
        return '<h3>只有学生可以报名活动！<a href="/activities">返回</a></h3>'
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    c.execute("SELECT title, max_participants, end_time FROM activities WHERE id = ?", (activity_id,))
    activity = c.fetchone()
    if not activity:
        conn.close()
        return '<h3>活动不存在！<a href="/activities">返回</a></h3>'
    
    # 检查是否已结束
    if is_activity_ended(activity[2]):
        conn.close()
        return '<h3>报名失败：活动已结束！<a href="/activities">返回</a></h3>'
    
    # 检查是否已满
    c.execute("SELECT COUNT(*) FROM registrations WHERE activity_id = ?", (activity_id,))
    count = c.fetchone()[0]
    if count >= activity[1]:
        conn.close()
        return '<h3>报名失败：活动已满！<a href="/activities">返回</a></h3>'
    
    try:
        register_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        c.execute("INSERT INTO registrations (student_id, activity_id, register_time) VALUES (?, ?, ?)",
                 (session['user_id'], activity_id, register_time))
        conn.commit()
        conn.close()
        return f'<h3>报名成功！<a href="/activities">返回活动列表</a></h3>'
    except sqlite3.IntegrityError:
        conn.close()
        return '<h3>你已经报名过这个活动了！<a href="/activities">返回</a></h3>'

# 编辑活动（教师）
@app.route('/edit_activity/<int:activity_id>', methods=['GET', 'POST'])
def edit_activity(activity_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'teacher':
        return '<h3>只有教师可以编辑活动！<a href="/activities">返回</a></h3>'
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 获取活动信息
    c.execute("SELECT id, title, description, location, start_time, end_time, max_participants, teacher_id FROM activities WHERE id = ?", (activity_id,))
    activity = c.fetchone()
    
    if not activity:
        conn.close()
        return '<h3>活动不存在！<a href="/my_activities">返回</a></h3>'
    
    # 验证是否是自己的活动
    if activity[7] != session['user_id']:
        conn.close()
        return '<h3>你只能编辑自己发布的活动！<a href="/my_activities">返回</a></h3>'
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        location = request.form['location']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        max_participants = request.form['max_participants']
        
        c.execute("""UPDATE activities SET title=?, description=?, location=?, start_time=?, end_time=?, max_participants=?
                     WHERE id=?""",
                  (title, description, location, start_time, end_time, max_participants, activity_id))
        conn.commit()
        conn.close()
        return '<h3>活动修改成功！<a href="/my_activities">查看我的活动</a></h3>'
    
    conn.close()
    
    # 格式化时间用于 datetime-local 输入
    start_val = activity[4].replace(' ', 'T') if ' ' in activity[4] else activity[4]
    end_val = activity[5].replace(' ', 'T') if ' ' in activity[5] else activity[5]
    
    return f'''
    <h2>编辑活动</h2>
    <form method="POST">
        活动标题: <input type="text" name="title" value="{activity[1]}" required><br><br>
        活动描述: <textarea name="description" rows="4" cols="30">{activity[2] or ''}</textarea><br><br>
        活动地点: <input type="text" name="location" value="{activity[3]}" required><br><br>
        开始时间: <input type="datetime-local" name="start_time" value="{start_val}" required><br><br>
        结束时间: <input type="datetime-local" name="end_time" value="{end_val}" required><br><br>
        最大参与人数: <input type="number" name="max_participants" value="{activity[6]}" min="1" required><br><br>
        <input type="submit" value="保存修改">
    </form>
    <p><a href="/my_activities">返回我的活动</a></p>
    '''

# 删除活动（教师）
@app.route('/delete_activity/<int:activity_id>')
def delete_activity(activity_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'teacher':
        return '<h3>只有教师可以删除活动！<a href="/activities">返回</a></h3>'
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 验证是否是自己的活动
    c.execute("SELECT teacher_id FROM activities WHERE id = ?", (activity_id,))
    activity = c.fetchone()
    
    if not activity:
        conn.close()
        return '<h3>活动不存在！<a href="/my_activities">返回</a></h3>'
    
    if activity[0] != session['user_id']:
        conn.close()
        return '<h3>你只能删除自己发布的活动！<a href="/my_activities">返回</a></h3>'
    
    # 删除报名记录，再删除活动
    c.execute("DELETE FROM registrations WHERE activity_id = ?", (activity_id,))
    c.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
    conn.commit()
    conn.close()
    
    return '<h3>活动已删除！<a href="/my_activities">返回我的活动</a></h3>'

# 我的活动
@app.route('/my_activities')
def my_activities():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    if session.get('role') == 'teacher':
        # 教师：看自己发布的活动，附带编辑和删除按钮
        c.execute("""SELECT a.id, a.title, a.location, a.start_time, a.end_time, a.max_participants,
                            (SELECT COUNT(*) FROM registrations r WHERE r.activity_id = a.id) as reg_count
                     FROM activities a
                     WHERE a.teacher_id = ?
                     ORDER BY a.start_time ASC""", (session['user_id'],))
        activities = c.fetchall()
        conn.close()
        
        html = '<h2>我发布的活动</h2>'
        html += '<p><a href="/dashboard">返回仪表盘</a></p>'
        if not activities:
            html += '<p>你还没有发布任何活动</p>'
        else:
            for act in activities:
                is_full = act[6] >= act[5]
                is_ended = is_activity_ended(act[4])
                
                status_tags = ''
                if is_ended:
                    status_tags += '<span style="background:#888;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;margin-right:5px;">已结束</span>'
                if is_full:
                    status_tags += '<span style="background:#e74c3c;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;">已满员</span>'
                
                html += f'''
                <div style="border:1px solid #ccc; padding:10px; margin:10px 0; border-radius:5px;">
                    <h3><a href="/activity/{act[0]}">{act[1]}</a> {status_tags}</h3>
                    <p><b>地点：</b>{act[2]}</p>
                    <p><b>时间：</b>{act[3]} ~ {act[4]}</p>
                    <p><b>报名人数：</b>{act[6]} / {act[5]}</p>
                    <p>
                        <a href="/edit_activity/{act[0]}">编辑</a>
                        | <a href="/delete_activity/{act[0]}" onclick="return confirm(\'确定删除该活动吗？所有报名记录也会被删除。\')">删除</a>
                    </p>
                </div>
                '''
    else:
        # 学生：看自己报名的活动
        c.execute("""SELECT a.id, a.title, a.location, a.start_time, a.end_time, u.username as teacher_name,
                            r.register_time
                     FROM registrations r
                     JOIN activities a ON r.activity_id = a.id
                     JOIN users u ON a.teacher_id = u.id
                     WHERE r.student_id = ?
                     ORDER BY a.start_time ASC""", (session['user_id'],))
        activities = c.fetchall()
        conn.close()
        
        html = '<h2>我报名的活动</h2>'
        html += '<p><a href="/dashboard">返回仪表盘</a></p>'
        if not activities:
            html += '<p>你还没有报名任何活动</p>'
        else:
            for act in activities:
                is_ended = is_activity_ended(act[4])
                status_tag = ''
                if is_ended:
                    status_tag = '<span style="background:#888;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;margin-left:5px;">已结束</span>'
                
                html += f'''
                <div style="border:1px solid #ccc; padding:10px; margin:10px 0; border-radius:5px;">
                    <h3><a href="/activity/{act[0]}">{act[1]}</a> {status_tag}</h3>
                    <p><b>地点：</b>{act[2]}</p>
                    <p><b>时间：</b>{act[3]} ~ {act[4]}</p>
                    <p><b>发布教师：</b>{act[5]}</p>
                    <p><b>报名时间：</b>{act[6]}</p>
                </div>
                '''
    
    return html

if __name__ == '__main__':
    app.run(debug=True)
