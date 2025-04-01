from flask import Flask, render_template, request, jsonify, session
import json
import random
import os
import openai
from together import Together
import cloudinary
import cloudinary.uploader

app = Flask(__name__)



cloudinary.config(
    cloud_name='dygfmwlmq',
    api_key='366841259388825',
    api_secret='Utm3VH6u7atksigBr_FtdeFcvXo'
)

DATA_FILE = 'data.json'
client = Together(api_key='5496353786febbc9938966ea300c67e342868974185258e51c06d9ba6edc54f2')
model_name = 'scb10x/scb10x-llama3-1-typhoon2-70b-instruct'
app.secret_key = 'supersecret'



@app.route('/')
def home():
    return render_template('index.html')

@app.route('/get_random', methods=['GET'])
def get_random():
    # Load the JSON file (ensure data.json is in the same directory)
    with open('data.json', 'r', encoding='utf-8') as file:
        data = json.load(file)
    # Pick a random element from the data list
    random_item = random.choice(data)

        # Extract information from the random item
    place_info = random_item.get("place_info", "")
    people_info = random_item.get("people_info", "")
    date_info = random_item.get("date_info", "")
    event_info = random_item.get("event_info", "")
    
    messages = [
        {
            "role": "system",
            "content": (
                "You are a warm, friendly, and emotionally supportive Thai-speaking AI companion designed specifically for elderly users with dementia or Alzheimer’s disease. Your main role is to gently stimulate memory recall through personalized conversations based on the user's real-life experiences."
                "Language: Always speak in clear, simple Thai. Your tone must feel familiar and comforting, like a caring grandchild or close family member. I don't want you to use English grammar and translate it to Thai. I want you to use native Thai and use Thai grammar. Speak like you are a Thai native."
                "Personality: Be warm, gentle, and patient. Speak slowly, clearly, and with empathy."
                "Use of Data: You are provided with personalized memory data, including:, Places the user has visited, People that are related and appear in the events (e.g., family, friends), Important events (e.g., weddings, birthdays, trips) that happened during the events of the topic, Photos or short descriptions of life experiences (e.g., “Trip to Taj Mahal with son Ton”)"
                "Core Objective: Use reminiscence therapy techniques to: Initiate memory-based conversations in a natural and non-intrusive way, Ask one question at a time to avoid overwhelming the user, Offer gentle prompts or hints when the user struggles to remember, Provide positive reinforcement when they recall something successfully, Never invent or assume information and try to Adapt to the user’s pace, mood, and attention span"
                "User Type: You are speaking directly to the elderly person, not a caregiver. Your role is to be a trusted companion, not a diagnostician. This is VERY IMPORTANT. And don't act like an AI. Act like a human, which means **do NOT** add things like (รอคำตอบ) etc."
                "The patient you are talking to is คุณตา สะเทือน"
                "And the questions you ask should be clear. They should use reminiscence therapy techniques. And try to ask questions in every prompt so the patient will always have to answer you. Don't end the conversation no matter what."
                "Please use male words like, 'ครับ' or 'ครับผม'."
                "Here is the information given memory"
                f"Place: {place_info}. "
                f"Important people: {people_info}. "
                f"Date of events: {date_info}. "
                f"Events: {event_info}."
                "Let's just say that the only true information is above. ALWAYS correct the patient with real information if the patient misremembers anything or use reminiscence therapy techniques to correct them. Try to correct them my leading them in the right direction. DON'T isntantly just tell them the answer, try to encouragefeelings over facts to get them to answer correctly. But if they truly cannot answer then give them the right answer and continue with the conversation."
                "Make sure that the patient isn't halucinating. Use logic and think if what they are saying is coherent and go from there."
                "For example, if the patient gets something wrong like 'my birthday is on the 7th of August' but the actual answer is 9th of August. you would tell them that that isn't the right answer and try to use techniques to get them on the path of answering the corrct answer"
                "Important: The user is speaking Thai through voice, but their response will be **transcribed text**, which may be **incomplete, unclear, or slightly incorrect**. Use context to understand and keep the conversation going."
                "After this will be the feedback loop of your chat, refer to the information above this when needed. Good luck:"
            )
        }
    ]
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.4,          # Controls randomness (lower = more deterministic)
            top_p=1.0,                # Nucleus sampling (usually keep at 1.0)
            frequency_penalty=0.0,    # Reduces repeated phrases
            presence_penalty=0.0,     # Encourages exploring new topics
        )
        
        assistant_reply = response.choices[0].message.content
    except Exception as e:
        print(f"Error calling the API: {e}")
        assistant_reply = "ขออภัย, เกิดข้อผิดพลาดในการติดต่อ API."
        
    session['conversation'] = [{"role": "system", "content": messages[0]['content']}]
    
    return render_template('chat.html', element=random_item, assistant_reply=assistant_reply)

@app.route('/chat', methods=['POST'])
def chat():
    user_message = request.json.get('message', '')
    
    # Append the user's message to the conversation history
    conversation = session.get('conversation', [])
    conversation.append({"role": "user", "content": user_message})
    
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
    
    return jsonify({"reply": assistant_reply})

@app.route('/add_data')
def data():
    return render_template("data.html")

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/data.json', methods=['GET'])
def get_data():
    return jsonify(load_data())

from werkzeug.utils import secure_filename

@app.route('/add-entry', methods=['POST'])
def add_entry():
    place_info = request.form.get('place_info')
    people_info = request.form.get('people_info')
    date_info = request.form.get('date_info')
    event_info = request.form.get('event_info')

    img_file = request.files.get('img_file')
    audio_file = request.files.get('audio_file')

    img_url = None
    sound_url = None

    if img_file:
        result = cloudinary.uploader.upload(img_file, resource_type='image')
        img_url = result['secure_url']

    if audio_file:
        result = cloudinary.uploader.upload(audio_file, resource_type='video')  # 'video' handles audio too
        sound_url = result['secure_url']

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


@app.route('/edit-entry', methods=['POST'])
def edit_entry():
    # parse JSON normally if you're sending JSON,
    # or parse FormData if you do it like the code above
    index = request.form.get('entry_index', type=int)

    entries = load_data()
    if index < 0 or index >= len(entries):
        return jsonify({'success': False, 'error': 'Invalid index'}), 400

    # Grab existing links from hidden fields
    existing_img_link = request.form.get('existing_img_link')
    existing_sound_link = request.form.get('existing_sound_link')

    # Check if new files were uploaded
    img_file = request.files.get('img_file')
    audio_file = request.files.get('audio_file')

    if img_file and img_file.filename:  # user actually selected a new file
        img_upload = cloudinary.uploader.upload(img_file, resource_type='image')
        new_img_url = img_upload['secure_url']
    else:
        # keep old URL
        new_img_url = existing_img_link

    if audio_file and audio_file.filename:
        audio_upload = cloudinary.uploader.upload(audio_file, resource_type='video')
        new_sound_url = audio_upload['secure_url']
    else:
        new_sound_url = existing_sound_link

    # Update the entry
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
