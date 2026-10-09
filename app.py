from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# ==================== 数据库初始化与升级 ====================

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # users 表
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL,
        status TEXT DEFAULT 'active',
        created_time TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    # 升级：给已有的users表加status字段（如果不存在）
    try:
        c.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active'")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN created_time TEXT DEFAULT CURRENT_TIMESTAMP")
    except sqlite3.OperationalError:
        pass

    # activities 表
    c.execute('''CREATE TABLE IF NOT EXISTS activities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        location TEXT NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        max_participants INTEGER DEFAULT 20,
        teacher_id INTEGER NOT NULL,
        status TEXT DEFAULT 'approved',
        reject_reason TEXT,
        created_time TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (teacher_id) REFERENCES users (id)
    )''')

    # 升级：activities表新增字段
    try:
        c.execute("ALTER TABLE activities ADD COLUMN status TEXT DEFAULT 'approved'")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE activities ADD COLUMN reject_reason TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE activities ADD COLUMN created_time TEXT DEFAULT CURRENT_TIMESTAMP")
    except sqlite3.OperationalError:
        pass

    # registrations 表
    c.execute('''CREATE TABLE IF NOT EXISTS registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        activity_id INTEGER NOT NULL,
        register_time TEXT NOT NULL,
        FOREIGN KEY (student_id) REFERENCES users (id),
        FOREIGN KEY (activity_id) REFERENCES activities (id),
        UNIQUE(student_id, activity_id)
    )''')

    # operation_logs 表（操作日志）
    c.execute('''CREATE TABLE IF NOT EXISTS operation_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER NOT NULL,
        admin_name TEXT NOT NULL,
        action TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id INTEGER,
        detail TEXT,
        created_time TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (admin_id) REFERENCES users (id)
    )''')

    # notifications 表（站内消息通知）
    c.execute('''CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        content TEXT,
        type TEXT DEFAULT 'system',
        is_read INTEGER DEFAULT 0,
        created_time TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')

    conn.commit()
    conn.close()

init_db()

# ==================== 辅助函数 ====================

def is_activity_ended(end_time_str):
    try:
        end_time = datetime.strptime(end_time_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        try:
            end_time = datetime.strptime(end_time_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return False
    return datetime.now() > end_time

def add_operation_log(action, target_type, target_id, detail):
    """记录管理员操作日志"""
    if session.get('role') != 'admin':
        return
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO operation_logs (admin_id, admin_name, action, target_type, target_id, detail)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (session['user_id'], session['username'], action, target_type, target_id, detail))
    conn.commit()
    conn.close()

def add_notification(user_id, title, content, ntype='system'):
    """发送站内消息"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""INSERT INTO notifications (user_id, title, content, type)
                 VALUES (?, ?, ?, ?)""",
              (user_id, title, content, ntype))
    conn.commit()
    conn.close()

def get_unread_count(user_id):
    """获取未读消息数"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count

def check_admin():
    """检查是否是管理员，不是则返回None"""
    if 'username' not in session:
        return None
    if session.get('role') != 'admin':
        return None
    # 检查账号状态
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT status FROM users WHERE id = ?", (session['user_id'],))
    user = c.fetchone()
    conn.close()
    if not user or user['status'] != 'active':
        return None
    return True

# ==================== 页面公共部分 ====================

def nav_bar():
    """生成导航栏"""
    if 'username' not in session:
        return '<p><a href="/">首页</a> | <a href="/login">登录</a> | <a href="/register">注册</a></p>'

    role = session.get('role')
    unread = get_unread_count(session['user_id'])
    unread_badge = f'({unread})' if unread > 0 else ''

    html = f'<p>欢迎，<b>{session["username"]}</b>（{role_text()}） | '
    html += f'<a href="/dashboard">仪表盘</a> | '
    html += f'<a href="/activities">活动列表</a> | '
    html += f'<a href="/my_activities">我的活动</a> | '
    html += f'<a href="/notifications">消息{unread_badge}</a> | '

    if role == 'teacher':
        html += '<a href="/create_activity">发布活动</a> | '
    elif role == 'admin':
        html += '<a href="/admin">管理后台</a> | '

    html += '<a href="/logout">退出</a></p>'
    return html

def role_text():
    role_map = {'student': '学生', 'teacher': '教师', 'admin': '管理员'}
    return role_map.get(session.get('role', 'student'), '学生')

# ==================== 首页 / 注册 / 登录 / 退出 ====================

@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return '<h1>校园活动管理系统 V2.0</h1><p><a href="/register">注册</a> | <a href="/login">登录</a> | <a href="/activities">活动列表</a></p>'

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form.get('role', 'student')
        # 限制前端只能注册学生和教师，管理员需手动创建
        if role not in ('student', 'teacher'):
            role = 'student'
        password_hash = generate_password_hash(password)

        conn = get_db()
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

    return f'''
    <h2>注册</h2>
    {nav_bar()}
    <form method="POST">
        用户名: <input type="text" name="username" required><br><br>
        密码: <input type="password" name="password" required><br><br>
        角色: <select name="role">
            <option value="student">学生</option>
            <option value="teacher">教师</option>
        </select><br><br>
        <input type="submit" value="注册">
    </form>
    <p><a href="/login">已有账号？去登录</a></p>
    '''

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, username, password_hash, role, status FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            if user['status'] == 'disabled':
                return '<h3 style="color:red;">账号已被停用，请联系管理员！</h3><p><a href="/login">返回登录</a></p>'
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('dashboard'))
        return '<h3>用户名或密码错误！<a href="/login">重新登录</a></h3>'

    return f'''
    <h2>登录</h2>
    {nav_bar()}
    <form method="POST">
        用户名: <input type="text" name="username" required><br><br>
        密码: <input type="password" name="password" required><br><br>
        <input type="submit" value="登录">
    </form>
    <p><a href="/register">没有账号？去注册</a></p>
    '''

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ==================== 仪表盘 ====================

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    html = f'<h1>欢迎，{session["username"]}！</h1>'
    html += nav_bar()
    html += f'<p>角色：{role_text()}</p>'

    role = session.get('role')
    if role == 'admin':
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) as cnt FROM activities WHERE status = 'pending'")
        pending = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) as cnt FROM users WHERE role != 'admin'")
        user_cnt = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) as cnt FROM activities")
        act_cnt = c.fetchone()['cnt']
        conn.close()

        html += f'''
        <h3>管理概览</h3>
        <div style="display:flex; gap:20px; margin:15px 0;">
            <div style="border:1px solid #ccc; padding:15px; border-radius:5px; text-align:center; width:150px;">
                <h2 style="color:#e67e22; margin:0;">{pending}</h2>
                <p style="margin:5px 0 0 0;">待审核活动</p>
                <a href="/admin/pending_activities">去审核</a>
            </div>
            <div style="border:1px solid #ccc; padding:15px; border-radius:5px; text-align:center; width:150px;">
                <h2 style="color:#3498db; margin:0;">{user_cnt}</h2>
                <p style="margin:5px 0 0 0;">注册用户</p>
                <a href="/admin/users">管理用户</a>
            </div>
            <div style="border:1px solid #ccc; padding:15px; border-radius:5px; text-align:center; width:150px;">
                <h2 style="color:#27ae60; margin:0;">{act_cnt}</h2>
                <p style="margin:5px 0 0 0;">活动总数</p>
                <a href="/admin/activities">查看全部</a>
            </div>
        </div>
        '''

    return html

# ==================== 站内消息 ====================

@app.route('/notifications')
def notifications():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT * FROM notifications WHERE user_id = ?
                 ORDER BY created_time DESC LIMIT 50""", (session['user_id'],))
    notifs = c.fetchall()

    # 标记为已读
    c.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0",
              (session['user_id'],))
    conn.commit()
    conn.close()

    html = f'<h2>我的消息</h2>'
    html += nav_bar()

    if not notifs:
        html += '<p>暂无消息</p>'
    else:
        for n in notifs:
            status = '' if n['is_read'] else '<span style="color:red;">[未读]</span> '
            html += f'''
            <div style="border:1px solid #ccc; padding:10px; margin:8px 0; border-radius:5px; background:{"#f9f9f9" if n["is_read"] else "#fffbeb"};">
                <p><b>{status}{n["title"]}</b> <span style="color:#888; font-size:12px;">{n["created_time"]}</span></p>
                <p>{n["content"] or ""}</p>
            </div>
            '''
    return html

# ==================== 发布活动（教师） ====================

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

        conn = get_db()
        c = conn.cursor()
        # 新活动状态为 pending，等待管理员审核
        c.execute("""INSERT INTO activities (title, description, location, start_time, end_time, max_participants, teacher_id, status)
                     VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
                  (title, description, location, start_time, end_time, max_participants, teacher_id))
        new_id = c.lastrowid
        conn.commit()
        conn.close()

        return f'<h3>活动提交成功，等待管理员审核！<a href="/my_activities">查看我的活动</a></h3>'

    html = '<h2>发布活动</h2>'
    html += nav_bar()
    html += '''
    <form method="POST">
        活动标题: <input type="text" name="title" required style="width:300px;"><br><br>
        活动描述: <textarea name="description" rows="4" cols="50"></textarea><br><br>
        活动地点: <input type="text" name="location" required style="width:300px;"><br><br>
        开始时间: <input type="datetime-local" name="start_time" required><br><br>
        结束时间: <input type="datetime-local" name="end_time" required><br><br>
        最大参与人数: <input type="number" name="max_participants" value="20" min="1" required><br><br>
        <p style="color:#666; font-size:12px;">💡 活动发布后需管理员审核，审核通过后学生才能看到并报名。</p>
        <input type="submit" value="提交发布">
    </form>
    <p><a href="/dashboard">返回仪表盘</a></p>
    '''
    return html

# ==================== 活动详情页 ====================

@app.route('/activity/<int:activity_id>')
def activity_detail(activity_id):
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    c = conn.cursor()

    # 获取活动信息
    c.execute("""SELECT a.*, u.username as teacher_name
                 FROM activities a JOIN users u ON a.teacher_id = u.id
                 WHERE a.id = ?""", (activity_id,))
    activity = c.fetchone()

    if not activity:
        conn.close()
        return '<h3>活动不存在！<a href="/activities">返回活动列表</a></h3>'

    # 待审核的活动只有发布教师和管理员能看到
    if activity['status'] == 'pending':
        if session.get('role') != 'admin' and session.get('user_id') != activity['teacher_id']:
            conn.close()
            return '<h3>活动正在审核中，暂不可见。</h3>'

    # 被驳回的活动只有发布教师能看到
    if activity['status'] == 'rejected':
        if session.get('user_id') != activity['teacher_id'] and session.get('role') != 'admin':
            conn.close()
            return '<h3>活动不存在！<a href="/activities">返回活动列表</a></h3>'

    # 获取报名人数
    c.execute("SELECT COUNT(*) as cnt FROM registrations WHERE activity_id = ?", (activity_id,))
    reg_count = c.fetchone()['cnt']

    # 获取已报名学生名单
    c.execute("""SELECT u.username, r.register_time FROM registrations r
                 JOIN users u ON r.student_id = u.id
                 WHERE r.activity_id = ?
                 ORDER BY r.register_time ASC""", (activity_id,))
    students = c.fetchall()

    # 判断状态
    is_full = reg_count >= activity['max_participants']
    is_ended = is_activity_ended(activity['end_time'])

    # 检查当前学生是否已报名
    registered = False
    if session.get('role') == 'student':
        c.execute("SELECT 1 FROM registrations WHERE activity_id = ? AND student_id = ?",
                 (activity_id, session['user_id']))
        registered = c.fetchone() is not None

    conn.close()

    # 活动状态标签
    status_tags = ''
    if activity['status'] == 'pending':
        status_tags += '<span style="background:#f39c12;color:#fff;padding:2px 8px;border-radius:3px;margin-right:5px;">待审核</span>'
    elif activity['status'] == 'rejected':
        status_tags += '<span style="background:#e74c3c;color:#fff;padding:2px 8px;border-radius:3px;margin-right:5px;">已驳回</span>'
    if is_ended:
        status_tags += '<span style="background:#888;color:#fff;padding:2px 8px;border-radius:3px;margin-right:5px;">已结束</span>'
    if is_full and activity['status'] == 'approved':
        status_tags += '<span style="background:#e74c3c;color:#fff;padding:2px 8px;border-radius:3px;">已满员</span>'

    html = f'<h2>{activity["title"]} {status_tags}</h2>'
    html += nav_bar()

    # 驳回原因（仅教师本人和管理员可见）
    if activity['status'] == 'rejected' and activity['reject_reason']:
        if session.get('user_id') == activity['teacher_id'] or session.get('role') == 'admin':
            html += f'<div style="background:#fdecea; border:1px solid #e74c3c; padding:10px; margin:10px 0; border-radius:5px;">'
            html += f'<p style="color:#c0392b; margin:0;"><b>驳回原因：</b>{activity["reject_reason"]}</p>'
            html += '</div>'

    html += f'''
    <div style="border:1px solid #ccc; padding:15px; margin:10px 0; border-radius:5px;">
        <p><b>活动描述：</b>{activity["description"] or "无"}</p>
        <p><b>活动地点：</b>{activity["location"]}</p>
        <p><b>开始时间：</b>{activity["start_time"]}</p>
        <p><b>结束时间：</b>{activity["end_time"]}</p>
        <p><b>发布教师：</b>{activity["teacher_name"]}</p>
        <p><b>报名人数：</b>{reg_count} / {activity["max_participants"]}（剩余 {activity["max_participants"] - reg_count} 个名额）</p>
    '''

    # 报名按钮（仅学生 + 活动已通过审核）
    if session.get('role') == 'student' and activity['status'] == 'approved':
        if registered:
            html += '<p style="color:green;"><b>你已报名</b></p>'
        elif is_full:
            html += '<p style="color:red;">活动已满员</p>'
        elif is_ended:
            html += '<p style="color:gray;">活动已结束，无法报名</p>'
        else:
            html += f'<a href="/register_activity/{activity["id"]}" style="background:#27ae60;color:#fff;padding:6px 15px;border-radius:4px;text-decoration:none;">立即报名</a>'
    elif activity['status'] == 'pending':
        html += '<p style="color:#f39c12;">⏳ 活动正在审核中，暂不能报名</p>'
    elif activity['status'] == 'rejected':
        html += '<p style="color:#e74c3c;">❌ 活动未通过审核</p>'

    html += '</div>'

    # 已报名学生名单（教师和管理员可见）
    if session.get('role') in ('teacher', 'admin') or session.get('user_id') == activity['teacher_id']:
        html += f'<h3>已报名学生（{reg_count}人）</h3>'
        if not students:
            html += '<p>暂无学生报名</p>'
        else:
            html += '<ul>'
            for s in students:
                html += f'<li>{s["username"]}（{s["register_time"]}）</li>'
            html += '</ul>'

    return html

# ==================== 活动列表 ====================

@app.route('/activities')
def activities():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    c = conn.cursor()

    # 学生和教师只能看到已审核通过的活动；管理员能看到全部
    if session.get('role') == 'admin':
        c.execute("""SELECT a.*, u.username as teacher_name
                     FROM activities a JOIN users u ON a.teacher_id = u.id
                     ORDER BY a.created_time DESC""")
    else:
        c.execute("""SELECT a.*, u.username as teacher_name
                     FROM activities a JOIN users u ON a.teacher_id = u.id
                     WHERE a.status = 'approved'
                     ORDER BY a.start_time ASC""")
    activity_list = c.fetchall()

    activity_data = []
    for act in activity_list:
        c.execute("SELECT COUNT(*) as cnt FROM registrations WHERE activity_id = ?", (act['id'],))
        count = c.fetchone()['cnt']
        registered = False
        if session.get('role') == 'student':
            c.execute("SELECT 1 FROM registrations WHERE activity_id = ? AND student_id = ?",
                     (act['id'], session['user_id']))
            registered = c.fetchone() is not None
        is_ended = is_activity_ended(act['end_time'])
        activity_data.append({
            'id': act['id'],
            'title': act['title'],
            'description': act['description'],
            'location': act['location'],
            'start_time': act['start_time'],
            'end_time': act['end_time'],
            'max_participants': act['max_participants'],
            'teacher_id': act['teacher_id'],
            'teacher_name': act['teacher_name'],
            'registered_count': count,
            'is_full': count >= act['max_participants'],
            'is_ended': is_ended,
            'registered': registered,
            'status': act['status']
        })
    conn.close()

    html = '<h2>活动列表</h2>'
    html += nav_bar()

    if not activity_data:
        html += '<p>暂无活动</p>'
    else:
        for act in activity_data:
            status_tags = ''
            if act['status'] == 'pending':
                status_tags += '<span style="background:#f39c12;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;margin-right:5px;">待审核</span>'
            elif act['status'] == 'rejected':
                status_tags += '<span style="background:#e74c3c;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;margin-right:5px;">已驳回</span>'
            if act['is_ended']:
                status_tags += '<span style="background:#888;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;margin-right:5px;">已结束</span>'
            if act['is_full'] and act['status'] == 'approved':
                status_tags += '<span style="background:#e74c3c;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;">已满员</span>'

            html += f'''
            <div style="border:1px solid #ccc; padding:10px; margin:10px 0; border-radius:5px;">
                <h3><a href="/activity/{act["id"]}">{act["title"]}</a> {status_tags}</h3>
                <p><b>描述：</b>{act["description"] or "无"}</p>
                <p><b>地点：</b>{act["location"]}</p>
                <p><b>时间：</b>{act["start_time"]} ~ {act["end_time"]}</p>
                <p><b>发布教师：</b>{act["teacher_name"]}</p>
                <p><b>报名人数：</b>{act["registered_count"]} / {act["max_participants"]}</p>
            '''
            if session.get('role') == 'student' and act['status'] == 'approved':
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

# ==================== 报名活动（学生） ====================

@app.route('/register_activity/<int:activity_id>')
def register_activity(activity_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'student':
        return '<h3>只有学生可以报名活动！<a href="/activities">返回</a></h3>'

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT title, max_participants, end_time, status FROM activities WHERE id = ?", (activity_id,))
    activity = c.fetchone()
    if not activity:
        conn.close()
        return '<h3>活动不存在！<a href="/activities">返回</a></h3>'

    # 只能报名已审核通过的活动
    if activity['status'] != 'approved':
        conn.close()
        return '<h3>报名失败：活动未通过审核！<a href="/activities">返回</a></h3>'

    # 检查活动是否已结束
    if is_activity_ended(activity['end_time']):
        conn.close()
        return '<h3>报名失败：活动已结束！<a href="/activities">返回</a></h3>'

    # 检查是否已满
    c.execute("SELECT COUNT(*) as cnt FROM registrations WHERE activity_id = ?", (activity_id,))
    count = c.fetchone()['cnt']
    if count >= activity['max_participants']:
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

# ==================== 编辑活动（教师） ====================

@app.route('/edit_activity/<int:activity_id>', methods=['GET', 'POST'])
def edit_activity(activity_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'teacher':
        return '<h3>只有教师可以编辑活动！<a href="/activities">返回</a></h3>'

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM activities WHERE id = ?", (activity_id,))
    activity = c.fetchone()

    if not activity:
        conn.close()
        return '<h3>活动不存在！<a href="/my_activities">返回</a></h3>'

    if activity['teacher_id'] != session['user_id']:
        conn.close()
        return '<h3>你只能编辑自己发布的活动！<a href="/my_activities">返回</a></h3>'

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        location = request.form['location']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        max_participants = request.form['max_participants']

        # 检测时间或地点是否变更，如果变更则通知已报名学生
        old_start = activity['start_time']
        old_end = activity['end_time']
        old_loc = activity['location']
        time_changed = (old_start != start_time) or (old_end != end_time)
        loc_changed = old_loc != location

        c.execute("""UPDATE activities SET title=?, description=?, location=?, start_time=?, end_time=?, max_participants=?
                     WHERE id=?""",
                  (title, description, location, start_time, end_time, max_participants, activity_id))
        conn.commit()

        # 如果时间或地点变更，发送通知
        if time_changed or loc_changed:
            change_msg = []
            if time_changed:
                change_msg.append(f"时间变更为 {start_time} ~ {end_time}")
            if loc_changed:
                change_msg.append(f"地点变更为 {location}")
            change_text = "；".join(change_msg)

            c.execute("SELECT student_id FROM registrations WHERE activity_id = ?", (activity_id,))
            regs = c.fetchall()
            for reg in regs:
                add_notification(reg['student_id'],
                               f'活动"《{title}》信息变更通知',
                               f'{change_text}，请留意。',
                               'activity')

        conn.close()
        return '<h3>活动修改成功！<a href="/my_activities">查看我的活动</a></h3>'

    conn.close()

    start_val = activity['start_time'].replace(' ', 'T') if ' ' in activity['start_time'] else activity['start_time']
    end_val = activity['end_time'].replace(' ', 'T') if ' ' in activity['end_time'] else activity['end_time']

    html = '<h2>编辑活动</h2>'
    html += nav_bar()
    html += f'''
    <form method="POST">
        活动标题: <input type="text" name="title" value="{activity["title"]}" required style="width:300px;"><br><br>
        活动描述: <textarea name="description" rows="4" cols="50">{activity["description"] or ""}</textarea><br><br>
        活动地点: <input type="text" name="location" value="{activity["location"]}" required style="width:300px;"><br><br>
        开始时间: <input type="datetime-local" name="start_time" value="{start_val}" required><br><br>
        结束时间: <input type="datetime-local" name="end_time" value="{end_val}" required><br><br>
        最大参与人数: <input type="number" name="max_participants" value="{activity["max_participants"]}" min="1" required><br><br>
        <p style="color:#666; font-size:12px;">💡 修改时间或地点后，系统会自动通知所有已报名的学生。</p>
        <input type="submit" value="保存修改">
    </form>
    <p><a href="/my_activities">返回我的活动</a></p>
    '''
    return html

# ==================== 删除活动（教师） ====================

@app.route('/delete_activity/<int:activity_id>')
def delete_activity(activity_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    if session.get('role') != 'teacher':
        return '<h3>只有教师可以删除活动！<a href="/activities">返回</a></h3>'

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT teacher_id, title FROM activities WHERE id = ?", (activity_id,))
    activity = c.fetchone()

    if not activity:
        conn.close()
        return '<h3>活动不存在！<a href="/my_activities">返回</a></h3>'

    if activity['teacher_id'] != session['user_id']:
        conn.close()
        return '<h3>你只能删除自己发布的活动！<a href="/my_activities">返回</a></h3>'

    c.execute("DELETE FROM registrations WHERE activity_id = ?", (activity_id,))
    c.execute("DELETE FROM activities WHERE id = ?", (activity_id,))
    conn.commit()
    conn.close()

    return '<h3>活动已删除！<a href="/my_activities">返回我的活动</a></h3>'

# ==================== 我的活动 ====================

@app.route('/my_activities')
def my_activities():
    if 'username' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    c = conn.cursor()

    html = '<h2>我的活动</h2>'
    html += nav_bar()

    if session.get('role') == 'teacher':
        c.execute("""SELECT a.*,
                            (SELECT COUNT(*) FROM registrations r WHERE r.activity_id = a.id) as reg_count
                     FROM activities a
                     WHERE a.teacher_id = ?
                     ORDER BY a.created_time DESC""", (session['user_id'],))
        activities = c.fetchall()
        conn.close()

        html += '<h3>我发布的活动</h3>'
        if not activities:
            html += '<p>你还没有发布任何活动</p>'
        else:
            for act in activities:
                is_full = act['reg_count'] >= act['max_participants']
                is_ended = is_activity_ended(act['end_time'])

                status_tags = ''
                if act['status'] == 'pending':
                    status_tags += '<span style="background:#f39c12;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;margin-right:5px;">待审核</span>'
                elif act['status'] == 'rejected':
                    status_tags += '<span style="background:#e74c3c;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;margin-right:5px;">已驳回</span>'
                if is_ended:
                    status_tags += '<span style="background:#888;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;margin-right:5px;">已结束</span>'
                if is_full and act['status'] == 'approved':
                    status_tags += '<span style="background:#e74c3c;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;">已满员</span>'

                html += f'''
                <div style="border:1px solid #ccc; padding:10px; margin:10px 0; border-radius:5px;">
                    <h3><a href="/activity/{act["id"]}">{act["title"]}</a> {status_tags}</h3>
                    <p><b>地点：</b>{act["location"]}</p>
                    <p><b>时间：</b>{act["start_time"]} ~ {act["end_time"]}</p>
                    <p><b>报名人数：</b>{act["reg_count"]} / {act["max_participants"]}</p>
                    <p>
                        <a href="/edit_activity/{act["id"]}">编辑</a>
                        | <a href="/delete_activity/{act["id"]}" onclick="return confirm(\"确定删除该活动吗？所有报名记录也会被删除。\")">删除</a>
                    </p>
                </div>
                '''
    else:
        # 学生：看自己报名的活动
        c.execute("""SELECT a.*, u.username as teacher_name, r.register_time
                     FROM registrations r
                     JOIN activities a ON r.activity_id = a.id
                     JOIN users u ON a.teacher_id = u.id
                     WHERE r.student_id = ?
                     ORDER BY a.start_time ASC""", (session['user_id'],))
        activities = c.fetchall()
        conn.close()

        html += '<h3>我报名的活动</h3>'
        if not activities:
            html += '<p>你还没有报名任何活动</p>'
        else:
            for act in activities:
                is_ended = is_activity_ended(act['end_time'])
                status_tag = ''
                if is_ended:
                    status_tag = '<span style="background:#888;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;margin-left:5px;">已结束</span>'

                html += f'''
                <div style="border:1px solid #ccc; padding:10px; margin:10px 0; border-radius:5px;">
                    <h3><a href="/activity/{act["id"]}">{act["title"]}</a> {status_tag}</h3>
                    <p><b>地点：</b>{act["location"]}</p>
                    <p><b>时间：</b>{act["start_time"]} ~ {act["end_time"]}</p>
                    <p><b>发布教师：</b>{act["teacher_name"]}</p>
                    <p><b>报名时间：</b>{act["register_time"]}</p>
                </div>
                '''

    return html

# ==================== 管理员后台 ====================

@app.route('/admin')
def admin_dashboard():
    if not check_admin():
        return '<h3 style="color:red;">无权限访问！</h3><p><a href="/dashboard">返回</a></p>'

    return redirect(url_for('dashboard'))

# --- 活动审核 ---

@app.route('/admin/pending_activities')
def admin_pending_activities():
    if not check_admin():
        return '<h3 style="color:red;">无权限访问！</h3><p><a href="/dashboard">返回</a></p>'

    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT a.*, u.username as teacher_name
                 FROM activities a JOIN users u ON a.teacher_id = u.id
                 WHERE a.status = 'pending'
                 ORDER BY a.created_time DESC""")
    activities = c.fetchall()
    conn.close()

    html = '<h2>活动审核 - 待审核列表</h2>'
    html += nav_bar()
    html += '<p><a href="/admin/activities">查看全部活动</a></p>'

    if not activities:
        html += '<p>暂无待审核的活动</p>'
    else:
        for act in activities:
            html += f'''
            <div style="border:1px solid #ccc; padding:15px; margin:10px 0; border-radius:5px; background:#fffbeb;">
                <h3>{act["title"]} <span style="background:#f39c12;color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;">待审核</span></h3>
                <p><b>发布教师：</b>{act["teacher_name"]}</p>
                <p><b>活动描述：</b>{act["description"] or "无"}</p>
                <p><b>地点：</b>{act["location"]}</p>
                <p><b>时间：</b>{act["start_time"]} ~ {act["end_time"]}</p>
                <p><b>人数上限：</b>{act["max_participants"]}人</p>
                <p><b>提交时间：</b>{act["created_time"]}</p>
                <p style="margin-top:10px;">
                    <a href="/admin/approve_activity/{act["id"]}" style="background:#27ae60;color:#fff;padding:6px 15px;border-radius:4px;text-decoration:none;margin-right:10px;">通过</a>
                    <a href="/admin/reject_activity/{act["id"]}" style="background:#e74c3c;color:#fff;padding:6px 15px;border-radius:4px;text-decoration:none;">驳回</a>
                </p>
            </div>
            '''
    return html

@app.route('/admin/approve_activity/<int:activity_id>')
def admin_approve_activity(activity_id):
    if not check_admin():
        return '<h3 style="color:red;">无权限访问！</h3>'

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT title, teacher_id FROM activities WHERE id = ?", (activity_id,))
    activity = c.fetchone()
    if not activity:
        conn.close()
        return '<h3>活动不存在！</h3>'

    c.execute("UPDATE activities SET status = 'approved', reject_reason = NULL WHERE id = ?", (activity_id,))
    conn.commit()

    # 记录操作日志
    add_operation_log('approve_activity', 'activity', activity_id, f'通过活动：{activity["title"]}')

    # 通知发布教师
    add_notification(activity['teacher_id'],
                     f'活动"《{activity["title"]}》审核通过',
                     '您发布的活动已通过管理员审核，学生现在可以查看和报名了。',
                     'system')
    conn.close()

    return redirect(url_for('admin_pending_activities'))

@app.route('/admin/reject_activity/<int:activity_id>', methods=['GET', 'POST'])
def admin_reject_activity(activity_id):
    if not check_admin():
        return '<h3 style="color:red;">无权限访问！</h3>'

    if request.method == 'POST':
        reason = request.form.get('reason', '')

        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT title, teacher_id FROM activities WHERE id = ?", (activity_id,))
        activity = c.fetchone()
        if not activity:
            conn.close()
            return '<h3>活动不存在！</h3>'

        c.execute("UPDATE activities SET status = 'rejected', reject_reason = ? WHERE id = ?",
                  (reason, activity_id))
        conn.commit()

        add_operation_log('reject_activity', 'activity', activity_id,
                         f'驳回活动：{activity["title"]}，原因：{reason}')

        add_notification(activity['teacher_id'],
                         f'活动"《{activity["title"]}》未通过审核',
                         f'驳回原因：{reason}。请修改后重新提交。',
                         'system')
        conn.close()

        return redirect(url_for('admin_pending_activities'))

    html = '<h2>驳回活动</h2>'
    html += nav_bar()
    html += f'''
    <form method="POST">
        <p>请填写驳回原因：</p>
        <textarea name="reason" rows="4" cols="50" required placeholder="请说明驳回原因，方便教师修改..."></textarea>
        <br><br>
        <input type="submit" value="确认驳回" style="background:#e74c3c;color:#fff;padding:6px 15px;border-radius:4px;border:none;cursor:pointer;">
        <a href="/admin/pending_activities">取消</a>
    </form>
    '''
    return html

# --- 全部活动（监督视图）---

@app.route('/admin/activities')
def admin_all_activities():
    if not check_admin():
        return '<h3 style="color:red;">无权限访问！</h3>'

    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT a.*, u.username as teacher_name,
                        (SELECT COUNT(*) FROM registrations r WHERE r.activity_id = a.id) as reg_count
                 FROM activities a JOIN users u ON a.teacher_id = u.id
                 ORDER BY a.created_time DESC""")
    activities = c.fetchall()
    conn.close()

    html = '<h2>全部活动（监督视图）</h2>'
    html += nav_bar()
    html += '<p><a href="/admin/pending_activities">待审核活动</a> | 全部活动</p>'
    html += '<p style="color:#666; font-size:12px;">💡 管理员仅可查看活动详情，不能直接修改活动内容。</p>'

    status_map = {'pending': '待审核', 'approved': '已通过', 'rejected': '已驳回'}
    color_map = {'pending': '#f39c12', 'approved': '#27ae60', 'rejected': '#e74c3c'}

    for act in activities:
        st = act['status']
        html += f'''
        <div style="border:1px solid #ccc; padding:10px; margin:8px 0; border-radius:5px;">
            <h3 style="margin:5px 0;"><a href="/activity/{act["id"]}">{act["title"]}</a>
               <span style="background:{color_map.get(st,"#999")};color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;margin-left:8px;">{status_map.get(st, st)}</span>
            </h3>
            <p style="margin:3px 0;"><b>教师：</b>{act["teacher_name"]} | <b>报名：</b>{act["reg_count"]}/{act["max_participants"]} | <b>时间：</b>{act["start_time"]}</p>
        </div>
        '''
    return html

# --- 用户管理 ---

@app.route('/admin/users')
def admin_users():
    if not check_admin():
        return '<h3 style="color:red;">无权限访问！</h3>'

    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT id, username, role, status, created_time
                 FROM users
                 ORDER BY created_time DESC""")
    users = c.fetchall()
    conn.close()

    html = '<h2>用户管理</h2>'
    html += nav_bar()

    role_map = {'student': '学生', 'teacher': '教师', 'admin': '管理员'}

    html += '''
    <table style="width:100%; border-collapse:collapse; margin-top:10px;" border="1">
    <tr style="background:#2B6CB0; color:#fff;">
        <th>ID</th><th>用户名</th><th>角色</th><th>状态</th><th>注册时间</th><th>操作</th>
    </tr>
    '''

    for u in users:
        status_color = '#27ae60' if u['status'] == 'active' else '#e74c3c'
        status_text = '正常' if u['status'] == 'active' else '已停用'
        action = ''
        if u['role'] != 'admin':  # 不能操作其他管理员
            if u['status'] == 'active':
                action = f'<a href="/admin/disable_user/{u["id"]}" onclick="return confirm(\'确定停用该用户吗？\')" style="color:#e74c3c;">停用</a>'
            else:
                action = f'<a href="/admin/enable_user/{u["id"]}" style="color:#27ae60;">恢复</a>'

        html += f'''
        <tr>
            <td style="text-align:center;">{u["id"]}</td>
            <td>{u["username"]}</td>
            <td style="text-align:center;">{role_map.get(u["role"], u["role"])}</td>
            <td style="text-align:center; color:{status_color}; font-weight:bold;">{status_text}</td>
            <td style="text-align:center;">{u["created_time"]}</td>
            <td style="text-align:center;">{action}</td>
        </tr>
        '''

    html += '</table>'
    return html

@app.route('/admin/disable_user/<int:user_id>')
def admin_disable_user(user_id):
    if not check_admin():
        return '<h3 style="color:red;">无权限访问！</h3>'

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT username, role FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()

    if not user:
        conn.close()
        return '<h3>用户不存在！</h3>'

    if user['role'] == 'admin':
        conn.close()
        return '<h3>不能停用管理员账号！<a href="/admin/users">返回</a></h3>'

    c.execute("UPDATE users SET status = 'disabled' WHERE id = ?", (user_id,))
    conn.commit()

    add_operation_log('disable_user', 'user', user_id, f'停用用户：{user["username"]}')

    add_notification(user_id,
                     '账号停用通知',
                     '您的账号已被管理员停用，如有疑问请联系管理员。',
                     'system')
    conn.close()

    return redirect(url_for('admin_users'))

@app.route('/admin/enable_user/<int:user_id>')
def admin_enable_user(user_id):
    if not check_admin():
        return '<h3 style="color:red;">无权限访问！</h3>'

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()

    if not user:
        conn.close()
        return '<h3>用户不存在！</h3>'

    c.execute("UPDATE users SET status = 'active' WHERE id = ?", (user_id,))
    conn.commit()

    add_operation_log('enable_user', 'user', user_id, f'恢复用户：{user["username"]}')

    add_notification(user_id,
                     '账号恢复通知',
                     '您的账号已被管理员恢复，现在可以正常登录使用了。',
                     'system')
    conn.close()

    return redirect(url_for('admin_users'))

# --- 操作日志 ---

@app.route('/admin/logs')
def admin_logs():
    if not check_admin():
        return '<h3 style="color:red;">无权限访问！</h3>'

    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT * FROM operation_logs
                 ORDER BY created_time DESC LIMIT 100""")
    logs = c.fetchall()
    conn.close()

    html = '<h2>操作日志</h2>'
    html += nav_bar()

    action_map = {
        'approve_activity': '通过活动',
        'reject_activity': '驳回活动',
        'disable_user': '停用用户',
        'enable_user': '恢复用户',
    }

    html += '''
    <table style="width:100%; border-collapse:collapse; margin-top:10px;" border="1">
    <tr style="background:#2B6CB0; color:#fff;">
        <th>时间</th><th>管理员</th><th>操作</th><th>对象类型</th><th>对象ID</th><th>详情</th>
    </tr>
    '''

    for log in logs:
        html += f'''
        <tr>
            <td style="text-align:center;">{log["created_time"]}</td>
            <td style="text-align:center;">{log["admin_name"]}</td>
            <td style="text-align:center;">{action_map.get(log["action"], log["action"])}</td>
            <td style="text-align:center;">{log["target_type"]}</td>
            <td style="text-align:center;">{log["target_id"] or "-"}</td>
            <td>{log["detail"] or "-"}</td>
        </tr>
        '''

    html += '</table>'
    return html

# ==================== 创建初始管理员账号 ====================
# 首次运行时自动创建一个管理员账号，方便测试
def create_default_admin():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'admin'")
    count = c.fetchone()['cnt']
    if count == 0:
        password_hash = generate_password_hash('admin123')
        c.execute("INSERT INTO users (username, password_hash, role, status) VALUES (?, ?, ?, 'active')",
                  ('admin', password_hash, 'admin'))
        conn.commit()
        print('默认管理员账号已创建: admin / admin123')
    conn.close()

create_default_admin()

# ==================== 启动 ====================

if __name__ == '__main__':
    print('='*50)
    print('  校园活动管理系统 V2.0（管理员版）')
    print('  默认管理员账号: admin / admin123')
    print('  访问地址: http://127.0.0.1:5000')
    print('='*50)
    app.run(debug=True)
