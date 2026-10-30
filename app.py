import sys
import os
from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import sqlite3

if getattr(sys, 'frozen', False):
    template_folder = sys._MEIPASS
else:
    template_folder = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=template_folder)
CORS(app)

DB_FILE = "meeting_315.db"
ADMIN_EMP_ID = "746878"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id TEXT PRIMARY KEY,
            title TEXT,
            applicant TEXT,
            empId TEXT,
            dept TEXT,
            startDate TEXT,
            startTime TEXT,
            endDate TEXT,
            endTime TEXT,
            remarks TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def index():
    html_path = os.path.join(template_folder, 'index.html')
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    return render_template_string(html_content)

@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('SELECT id, title, applicant, empId, dept, startDate, startTime, endDate, endTime, remarks FROM bookings')
    rows = c.fetchall()
    conn.close()
    
    data = []
    for r in rows:
        data.append({
            "id": r[0], "title": r[1], "applicant": r[2], "empId": r[3],
            "dept": r[4], "startDate": r[5], "startTime": r[6],
            "endDate": r[7], "endTime": r[8], "remarks": r[9]
        })
    return jsonify({"success": True, "bookings": data})

@app.route('/api/bookings', methods=['POST'])
def add_or_update_booking():
    req = request.json
    booking_id = req['id']
    is_update = req.get('isUpdate', False)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 若為修改，驗證原員編或管理員員編
    if is_update:
        c.execute('SELECT empId FROM bookings WHERE id = ?', (booking_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "message": "❌ 找不到原預約紀錄！"})
        if req['empId'] != row[0] and req['empId'] != ADMIN_EMP_ID:
            conn.close()
            return jsonify({"success": False, "message": "❌ 員工編號不符合原申請人或管理員，無法變更預約！"})

    # 衝突檢查（排除自身紀錄）
    c.execute('SELECT id, startDate, startTime, endDate, endTime FROM bookings')
    existing = c.fetchall()
    
    new_start = f"{req['startDate']} {req['startTime']}"
    new_end = f"{req['endDate']} {req['endTime']}"
    
    for row in existing:
        if is_update and row[0] == booking_id:
            continue
        e_start = f"{row[1]} {row[2]}"
        e_end = f"{row[3]} {row[4]}"
        if not (new_end <= e_start or new_start >= e_end):
            conn.close()
            return jsonify({"success": False, "message": "⚠️ 所選的新時段已被其他人預約，請選擇其他時間！"})

    if is_update:
        c.execute('''
            UPDATE bookings 
            SET title=?, applicant=?, empId=?, dept=?, startDate=?, startTime=?, endDate=?, endTime=?, remarks=?
            WHERE id=?
        ''', (
            req['title'], req['applicant'], req['empId'], req['dept'],
            req['startDate'], req['startTime'], req['endDate'], req['endTime'],
            req['remarks'], booking_id
        ))
        msg = "✅ 會議預約日期時段已順利變更！"
    else:
        c.execute('''
            INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            booking_id, req['title'], req['applicant'], req['empId'],
            req['dept'], req['startDate'], req['startTime'],
            req['endDate'], req['endTime'], req['remarks']
        ))
        msg = "✅ 會議預約登記成功！"

    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": msg})

@app.route('/api/bookings/delete', methods=['POST'])
def delete_booking():
    req = request.json
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('SELECT empId FROM bookings WHERE id = ?', (req['id'],))
    row = c.fetchone()
    if not row:
        conn.close()
        return jsonify({"success": False, "message": "找不到該筆資料"})
        
    if req['verifyEmpId'] == row[0] or req['verifyEmpId'] == ADMIN_EMP_ID:
        c.execute('DELETE FROM bookings WHERE id = ?', (req['id'],))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "🗑️ 會議預約已成功撤銷！"})
    else:
        conn.close()
        return jsonify({"success": False, "message": "❌ 員工編號不符合，無權限刪除！"})

if __name__ == '__main__':
    print("==================================================")
    print("  工安處南部辦公室 會議室(315)使用登記系統 伺服器啟動中...")
    print("  開放時間：24小時全日開放 (支援即時修改與撤銷)")
    print("  請勿關閉此視窗，關閉後內網將無法連線登錄。")
    print("==================================================")
    app.run(host='0.0.0.0', port=5000)