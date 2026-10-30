import os
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__, template_folder='.')
CORS(app)

DB_URL = os.environ.get('DATABASE_URL')
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'h.kuoyi@gmail.com')

def get_db():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def send_notification_email(action_type, booking_data):
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        return
    try:
        subject = f"【315會議室通知】{action_type} - {booking_data.get('title')} ({booking_data.get('applicant')})"
        body = f"""黃大哥 您好，

315 會議室預約系統有最新動態：

📌 異動類型：{action_type}
📌 會議名稱：{booking_data.get('title')}
📌 申 請 人：{booking_data.get('applicant')} ({booking_data.get('dept') or '未填寫單位'})
📌 預約時間：{booking_data.get('startDate')} {booking_data.get('startTime')} ～ {booking_data.get('endDate')} {booking_data.get('endTime')}
📌 備註事項：{booking_data.get('remarks') or '無'}

---
本信件由 315 會議室預約系統自動發送。
"""
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = MAIL_USERNAME
        msg['To'] = ADMIN_EMAIL

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_USERNAME, [ADMIN_EMAIL], msg.as_string())
        server.quit()
    except Exception as e:
        print(f"寄信失敗: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, title, applicant, dept, start_date::text as \"startDate\", start_time as \"startTime\", end_date::text as \"endDate\", end_time as \"endTime\", remarks FROM bookings ORDER BY start_date ASC, start_time ASC;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'bookings': list(rows)})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/bookings', methods=['POST'])
def save_booking():
    data = request.json
    try:
        conn = get_db()
        cur = conn.cursor()
        
        # 衝突檢查
        cur.execute("""
            SELECT id FROM bookings 
            WHERE id != %s 
              AND start_date <= %s AND end_date >= %s
              AND NOT (end_time <= %s OR start_time >= %s);
        """, (data.get('id'), data.get('endDate'), data.get('startDate'), data.get('startTime'), data.get('endTime')))
        
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({'success': False, 'message': '❌ 該時段已被預約，請選擇其他時間！'})

        if data.get('isUpdate'):
            cur.execute("SELECT emp_id FROM bookings WHERE id = %s;", (data.get('id'),))
            target = cur.fetchone()
            if not target or (data.get('empId') != '746878' and data.get('empId') != target['emp_id']):
                cur.close()
                conn.close()
                return jsonify({'success': False, 'message': '❌ 員工編號驗證失敗！無法變更。'})

            cur.execute("""
                UPDATE bookings 
                SET title=%s, applicant=%s, emp_id=%s, dept=%s, start_date=%s, start_time=%s, end_date=%s, end_time=%s, remarks=%s
                WHERE id=%s;
            """, (data.get('title'), data.get('applicant'), data.get('empId'), data.get('dept'),
                  data.get('startDate'), data.get('startTime'), data.get('endDate'), data.get('endTime'), data.get('remarks'), data.get('id')))
            msg = '✅ 預約變更成功！'
            action_type = '變更預約'
        else:
            cur.execute("""
                INSERT INTO bookings (id, title, applicant, emp_id, dept, start_date, start_time, end_date, end_time, remarks)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (data.get('id'), data.get('title'), data.get('applicant'), data.get('empId'), data.get('dept'),
                  data.get('startDate'), data.get('startTime'), data.get('endDate'), data.get('endTime'), data.get('remarks')))
            msg = '✅ 會議室預約登記成功！'
            action_type = '新增登記'

        conn.commit()
        cur.close()
        conn.close()
        send_notification_email(action_type, data)
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/bookings/delete', methods=['POST'])
def delete_booking():
    data = request.json
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT title, applicant, dept, start_date::text as \"startDate\", start_time as \"startTime\", end_date::text as \"endDate\", end_time as \"endTime\", remarks, emp_id FROM bookings WHERE id = %s;", (data.get('id'),))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return jsonify({'success': False, 'message': '❌ 找不到該筆預約紀錄！'})

        if data.get('verifyEmpId') == '746878' or data.get('verifyEmpId') == row['emp_id']:
            cur.execute("DELETE FROM bookings WHERE id = %s;", (data.get('id'),))
            conn.commit()
            send_notification_email('撤銷預約', dict(row))
            msg = '✅ 預約紀錄已成功撤銷！'
            success = True
        else:
            msg = '❌ 員工編號驗證失敗！無法撤銷預約。'
            success = False

        cur.close()
        conn.close()
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
