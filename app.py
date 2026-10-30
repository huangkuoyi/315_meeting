import os
from flask import Flask, request, jsonify, render_template, Response
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

app = Flask(__name__, template_folder='.')
CORS(app)

DB_URL = os.environ.get('DATABASE_URL')

def get_db():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def init_and_clean_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT clean_old_bookings();")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Database init error: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    try:
        init_and_clean_db()
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
            if not target:
                return jsonify({'success': False, 'message': '❌ 找不到欲變更的預約紀錄！'})
            if data.get('empId') != '746878' and data.get('empId') != target['emp_id']:
                return jsonify({'success': False, 'message': '❌ 員工編號驗證失敗！無法變更此預約。'})

            cur.execute("""
                UPDATE bookings 
                SET title=%s, applicant=%s, emp_id=%s, dept=%s, start_date=%s, start_time=%s, end_date=%s, end_time=%s, remarks=%s
                WHERE id=%s;
            """, (data.get('title'), data.get('applicant'), data.get('empId'), data.get('dept'),
                  data.get('startDate'), data.get('startTime'), data.get('endDate'), data.get('endTime'), data.get('remarks'), data.get('id')))
            msg = '✅ 預約變更成功！'
        else:
            cur.execute("""
                INSERT INTO bookings (id, title, applicant, emp_id, dept, start_date, start_time, end_date, end_time, remarks)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (data.get('id'), data.get('title'), data.get('applicant'), data.get('empId'), data.get('dept'),
                  data.get('startDate'), data.get('startTime'), data.get('endDate'), data.get('endTime'), data.get('remarks')))
            msg = '✅ 會議室預約登記成功！'

        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/bookings/delete', methods=['POST'])
def delete_booking():
    data = request.json
    booking_id = data.get('id')
    verify_emp_id = data.get('verifyEmpId')
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT emp_id FROM bookings WHERE id = %s;", (booking_id,))
        target = conn.cursor().fetchone() if hasattr(conn, 'cursor') else None
        
        cur.execute("SELECT emp_id FROM bookings WHERE id = %s;", (booking_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'message': '❌ 找不到該筆預約紀錄！'})

        if verify_emp_id == '746878' or verify_emp_id == row['emp_id']:
            cur.execute("DELETE FROM bookings WHERE id = %s;", (booking_id,))
            conn.commit()
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

@app.route('/calendar.ics', methods=['GET'])
def get_calendar():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id, title, applicant, dept, start_date::text as \"startDate\", start_time as \"startTime\", end_date::text as \"endDate\", end_time as \"endTime\", remarks FROM bookings;")
        rows = cur.fetchall()
        cur.close()
        conn.close()

        ics_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//CPC//315 Room//ZH",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "X-WR-CALNAME:315會議室登記情形"
        ]

        for b in rows:
            try:
                # 轉為標準 ISO 格式
                s_str = f"{b['startDate']} {b['startTime']}"
                e_str = f"{b['endDate']} {b['endTime']}"
                s_dt = datetime.strptime(s_str, "%Y-%m-%d %H:%M").strftime("%Y%m%dT%H%M00")
                e_dt = datetime.strptime(e_str, "%Y-%m-%d %H:%M").strftime("%Y%m%dT%H%M00")
                
                ics_lines.append("BEGIN:VEVENT")
                ics_lines.append(f"UID:{b['id']}@three15-meeting.onrender.com")
                ics_lines.append(f"DTSTART:{s_dt}")
                ics_lines.append(f"DTEND:{e_dt}")
                ics_lines.append(f"SUMMARY:【315會議室】{b['title']} - {b['applicant']}")
                ics_lines.append(f"DESCRIPTION:申請人：{b['applicant']} (單位：{b['dept'] or '無'}) 備註：{b['remarks'] or '無'}")
                ics_lines.append("LOCATION:工安處南部辦公室 315 會議室")
                ics_lines.append("END:VEVENT")
            except Exception as ex:
                continue

        ics_lines.append("END:VCALENDAR")
        response_text = "\r\n".join(ics_lines)
        return Response(response_text, mimetype="text/calendar", headers={"Content-Disposition": "inline; filename=calendar.ics"})
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
