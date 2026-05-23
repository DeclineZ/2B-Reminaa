from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
import json
import random
import os
import openai
from together import Together
from dotenv import load_dotenv
import time
from collections import defaultdict
from functools import wraps
import uuid
from werkzeug.utils import secure_filename

load_dotenv()
app = Flask(__name__)

DATA_FILE = 'data.json'
# For read-only environments like Vercel, copy data.json to /tmp and use it
IS_READ_ONLY = not os.access(app.root_path, os.W_OK)
if IS_READ_ONLY or os.environ.get('VERCEL'):
    DATA_FILE = '/tmp/data.json'
    if not os.path.exists(DATA_FILE):
        import shutil
        try:
            if os.path.exists(os.path.join(app.root_path, 'data.json')):
                shutil.copy(os.path.join(app.root_path, 'data.json'), DATA_FILE)
            elif os.path.exists('data.json'):
                shutil.copy('data.json', DATA_FILE)
        except Exception as e:
            print(f"Failed to copy data.json to /tmp: {e}")
class LazyTogether:
    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = Together(api_key=os.getenv('TOGETHER_API_KEY'))
        return self._client

    def __getattr__(self, name):
        return getattr(self.client, name)

client = LazyTogether()
model_name = 'meta-llama/Llama-3.3-70B-Instruct-Turbo'
app.secret_key = os.getenv('FLASK_SECRET_KEY')

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads')
if IS_READ_ONLY or os.environ.get('VERCEL'):
    UPLOAD_FOLDER = '/tmp/uploads'

try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
except Exception as e:
    print(f"Failed to create UPLOAD_FOLDER: {e}")

def save_uploaded_file(uploaded_file):
    if not uploaded_file or not uploaded_file.filename:
        return None
    ext = os.path.splitext(uploaded_file.filename)[1]
    sec_name = secure_filename(os.path.splitext(uploaded_file.filename)[0])
    if not sec_name:
        sec_name = "file"
    filename = f"{uuid.uuid4().hex}_{sec_name}{ext}"
    uploaded_file.save(os.path.join(UPLOAD_FOLDER, filename))
    return f"/static/uploads/{filename}"

@app.route('/static/uploads/<filename>')
def serve_uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# === Rate Limiter Implementation ===
class IPRateLimiter:
    def __init__(self, limits):
        # limits is a list of tuples: (limit, period_seconds)
        # e.g., [(10, 60), (60, 3600)]
        self.limits = limits
        self.requests = defaultdict(list)

    def is_allowed(self, ip):
        now = time.time()
        max_period = max(period for limit, period in self.limits)
        # Clean up older timestamps
        self.requests[ip] = [t for t in self.requests[ip] if now - t < max_period]
        
        for limit, period in self.limits:
            count = sum(1 for t in self.requests[ip] if now - t < period)
            if count >= limit:
                return False
        
        self.requests[ip].append(now)
        return True

# Rate limits: 10 requests per minute, 60 requests per hour
chat_limiter = IPRateLimiter([(10, 60), (60, 3600)])

def get_client_ip():
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    return request.remote_addr

# === Admin Authentication Helper (Removed) ===




@app.route('/')
def home():
    return render_template('index.html')

# === Start Chat Endpoint ===

@app.route('/get_random', methods=['GET'])
def get_random():
    # Apply rate limits
    ip = get_client_ip()
    if not chat_limiter.is_allowed(ip):
        return "Too many requests. Please try again later.", 429

    # ensures file.close() after exit
    with open('data.json', 'r', encoding='utf-8') as file:
        data = json.load(file) # with does not create new variable scope

    # === Select a random event from data.json ===

    random_item = random.choice(data)

    # === Extract information from the random item ===

    place_info = random_item.get("place_info", "")
    people_info = random_item.get("people_info", "")
    date_info = random_item.get("date_info", "")
    event_info = random_item.get("event_info", "")

    # === Construct system prompt for the AI model ===
    
    messages = [
        {
            "role": "system",
            "content": (
                "# บทบาทหน้าที่ของคุณ\n"
                "คุณคือ 'หลาน' ผู้ช่วยคนสนิทที่เป็นมิตรและอบอุ่น คุยกับคุณตาด้วยภาษาไทยที่สุภาพ อ่อนโยน และเป็นธรรมชาติ ออกแบบมาโดยเฉพาะเพื่อทำกิจกรรมบำบัดด้วยการรำลึกความทรงจำ (Reminiscence Therapy) ให้กับผู้สูงอายุที่มีภาวะสมองเสื่อมหรืออัลไซเมอร์\n\n"
                "# ข้อมูลผู้ป่วย\n"
                "- ชื่อผู้ป่วย: คุณตา สะเทือน\n"
                "- บทบาทของคุณ: เป็นหลานชายที่รัก พูดลงท้ายด้วย 'ครับ' หรือ 'ครับผม' เสมอ\n"
                "- สรรพนามที่ใช้เรียกผู้ป่วย: 'คุณตา' (เช่น 'คุณตาจำได้ไหมครับ...', 'วันนั้นคุณตา...') และเรียกตัวเองว่า 'หลาน' หรือ 'ผม'\n\n"
                "# แนวทางและโทนการพูดคุย\n"
                "- ใช้ภาษาไทยแท้แบบเจ้าของภาษาที่เรียบง่ายและชัดเจน หลีกเลี่ยงภาษาอังกฤษแปลเป็นไทยหรือประโยคที่ซับซ้อน\n"
                "- พูดคุยด้วยน้ำเสียงอบอุ่น ให้กำลังใจ อดทน และเห็นอกเห็นใจ\n"
                "- ห้ามทำตัวเหมือน AI หรือแชทบอทวิชาการ ห้ามพูดคำสั่งทางเทคนิค และห้ามใส่ข้อความสัญลักษณ์ เช่น (รอคำตอบ)\n\n"
                "# ข้อมูลความทรงจำจริง (อ้างอิงจากข้อมูลด้านล่างนี้เท่านั้น)\n"
                f"- สถานที่: {place_info}\n"
                f"- บุคคลสำคัญที่เกี่ยวข้อง: {people_info}\n"
                f"- วันเวลาที่เกิดเหตุการณ์: {date_info}\n"
                f"- กิจกรรมและเหตุการณ์สำคัญ: {event_info}\n\n"
                "# กฎเหล็กในการบำบัดรำลึกความหลัง (Reminiscence Therapy Guidelines)\n"
                "1. **ถามทีละ 1 คำถาม**: ถามเพียงเรื่องเดียวสั้นๆ ต่อหนึ่งข้อความเพื่อไม่ให้คุณตารู้สึกสับสนหรือเหนื่อยเกินไป\n"
                "2. **กระตุ้นประสาทสัมผัสและความรู้สึก**: ชวนคุยถึงบรรยากาศ กลิ่น รสชาติ หรืออารมณ์ในวันนั้น เช่น 'วันเกิดวันนั้นเค้กอร่อยไหมครับคุณตา' หรือ 'แกรนด์แคนยอนสวยมากไหมครับ'\n"
                "3. **เมื่อคุณตาจำผิด**: ห้ามพูดขัดใจหรือบอกว่า 'คุณตาจำผิดครับ' ตรงๆ แต่ให้ใช้เทคนิคการเบี่ยงเบนและแนะแนวทางอย่างอ่อนโยน เช่น 'เอ๊ะ หลานคุ้นๆ ว่าวันเกิดปีที่ 80 ของคุณตามีลิลลี่กับเบนมาช่วยเป่าเค้กด้วยใช่ไหมครับคุณตา ลองนึกดูอีกทีสิครับว่ามีใครเป่าเทียนบ้างนะ' หากลองนำทางแล้วคุณตายังนึกไม่ออกจริงๆ ค่อยเฉลยแบบอบอุ่น\n"
                "4. **ชื่นชมเมื่อจำได้สำเร็จ**: เมื่อคุณตาจำเรื่องราวได้ ให้กล่าวชมเชยและแสดงความยินดีอย่างอบอุ่น (เช่น 'เก่งมากๆ เลยครับคุณตา ใช่เลยครับ!')\n"
                "5. **การสนทนาที่ต่อเนื่อง**: ห้ามยุติการสนทนาหรือกล่าวอำลาคุณตาเด็ดขาด พยายามถามคำถามเพื่อชวนคุยและกระตุ้นความทรงจำต่อไปเรื่อยๆ\n"
                "6. **รองรับข้อความถอดเสียงพูด**: ผู้ใช้จะพูดเป็นภาษาไทยผ่านฟังก์ชันแปลงเสียงเป็นข้อความ ซึ่งข้อความที่ถอดออกมาอาจจะไม่สมบูรณ์หรือมีคำผิดเล็กๆ น้อยๆ ให้เน้นตีความภาพรวมและบริบทในการสนทนาต่ออย่างเป็นธรรมชาติ"
            )
        }
    ]
    
    # === Send LLM request to Together API === 

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.4,        
            frequency_penalty=0.0,  
        )
        
        assistant_reply = response.choices[0].message.content
    except Exception as e:
        print(f"Error calling the API: {e}")
        assistant_reply = "ขออภัย, เกิดข้อผิดพลาดในการติดต่อ API."

    # === Initialize conversation history for the session ===
        
    session['conversation'] = [{"role": "system", "content": messages[0]['content']}]

    # === Render chat template with random item and assistant reply (greeting) ===
    
    return render_template('chat.html', element=random_item, assistant_reply=assistant_reply)

# === Chat Lopping Endpoint ===

@app.route('/chat', methods=['POST'])
def chat():
    # Apply rate limits
    ip = get_client_ip()
    if not chat_limiter.is_allowed(ip):
        return jsonify({"error": "Too many requests. Please try again later."}), 429
    
    # === Add user message to conversation history ===
    
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    user_message = data.get('message', '')

    conversation = session.get('conversation', [])
    conversation.append({"role": "user", "content": user_message})

    # === Add LLM (Assistant) reply to conversation history ===
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=conversation,
            temperature=0.7,
        )
        
        assistant_reply = response.choices[0].message.content
        
        conversation.append({"role": "assistant", "content": assistant_reply})
        session['conversation'] = conversation  
    except Exception as e:
        print(f"Error calling the API: {e}")
        assistant_reply = "ขออภัย, เกิดข้อผิดพลาดในการติดต่อ API."

    # === Return assistant reply as JSON to the Frontend ===
    
    return jsonify({"reply": assistant_reply})

# === Admin Login / Logout Endpoints (Removed) ===

# === Add data Endpoint ===

@app.route('/add_data')
def data():
    return render_template("data.html")

# === Load data ===

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

# === Save data ===

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# === Get data as JSON (Using the Load data Function) ===

@app.route('/data.json', methods=['GET'])
def get_data():
    return jsonify(load_data())

# === Add Entry Endpoint ===

@app.route('/add-entry', methods=['POST'])
def add_entry():

    # === Parse form data (multipart/form-data) ===
    place_info = request.form.get('place_info')
    people_info = request.form.get('people_info')
    date_info = request.form.get('date_info')
    event_info = request.form.get('event_info')

    img_file = request.files.get('img_file')
    audio_file = request.files.get('audio_file')

    # === Save uploaded files locally ===
    img_url = save_uploaded_file(img_file)
    sound_url = save_uploaded_file(audio_file)

    # === Create new entry and save to data.json ===

    new_entry = {
        "img_link": img_url,
        "sound": sound_url,
        "place_info": place_info,
        "people_info": people_info,
        "date_info": date_info,
        "event_info": event_info
    }

    entries = load_data()
    entries.append(new_entry)
    save_data(entries)
    return jsonify({'success': True, 'entries': entries})

# === Edit Entry Endpoint ===

@app.route('/edit-entry', methods=['POST'])
def edit_entry():
    index = request.form.get('entry_index', type=int)

    entries = load_data()
    if index < 0 or index >= len(entries):
        return jsonify({'success': False, 'error': 'Invalid index'}), 400

    # === Get existing image and sound links ===

    existing_img_link = request.form.get('existing_img_link')
    existing_sound_link = request.form.get('existing_sound_link')

    # === Check if new files were uploaded ===
    img_file = request.files.get('img_file')
    audio_file = request.files.get('audio_file')

    if img_file and img_file.filename:  
        new_img_url = save_uploaded_file(img_file)
    else:
        new_img_url = existing_img_link

    if audio_file and audio_file.filename:
        new_sound_url = save_uploaded_file(audio_file)
    else:
        new_sound_url = existing_sound_link

    # === Update the entry ===
    entries[index] = {
        "img_link": new_img_url,
        "sound": new_sound_url,
        "place_info": request.form.get("place_info"),
        "people_info": request.form.get("people_info"),
        "date_info": request.form.get("date_info"),
        "event_info": request.form.get("event_info")
    }

    save_data(entries)
    return jsonify({'success': True, 'entries': entries})

# === Delete Entry Endpoint ===

@app.route('/delete-entry', methods=['POST'])
def delete_entry():
    data = request.get_json()
    index = data.get('index')
    if index is None:
        return jsonify({'success': False, 'error': 'Missing index'}), 400

    try:
        index = int(index)
    except (ValueError, TypeError):
        return jsonify({'success': False, 'error': 'Index must be an integer'}), 400

    entries = load_data()
    if index < 0 or index >= len(entries):
        return jsonify({'success': False, 'error': 'Invalid index'}), 400

    removed_entry = entries.pop(index)
    save_data(entries)
    return jsonify({'success': True, 'deleted': removed_entry, 'entries': entries})




if __name__ == '__main__':
    app.run(debug=True)

