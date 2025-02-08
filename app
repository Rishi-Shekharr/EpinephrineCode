import os
import re
import logging
from flask import Flask, request, jsonify, render_template
import chromadb
from typing import List
from werkzeug.utils import secure_filename
import pytesseract
from pdf2image import convert_from_path
from pypdf import PdfReader
import google.generativeai as genai

os.environ["GEMINI_API_KEY"] = "AIzaSyD1_C3wpg_sw6H51e9oXdZ1pzd_6WkGiYo"

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
logging.basicConfig(level=logging.DEBUG)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def extract_text_with_ocr(file_path):
    images = convert_from_path(file_path)
    text = ""
    for image in images:
        text += pytesseract.image_to_string(image)
    return text

def load_pdf(file_path):
    text = ""
    reader = PdfReader(file_path)
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text
        else:
            text = extract_text_with_ocr(file_path)
            break
    return text

def split_text(text: str):
    split_text = re.split(r'\n\s*\n', text)
    return [chunk.strip() for chunk in split_text if chunk.strip()]

class GeminiEmbeddingFunction(chromadb.EmbeddingFunction):
    def __call__(self, input: List[str]) -> List[List[float]]:
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            raise ValueError("Gemini API Key not provided.")
        genai.configure(api_key=gemini_api_key)
        model = "models/embedding-001"
        title = "Custom query"
        embeddings = []
        for doc in input:
            embedding = genai.embed_content(model=model, content=doc, task_type="retrieval_document", title=title)["embedding"]
            embeddings.append(embedding)
        return embeddings

def create_chroma_db(documents: List[str], path: str, name: str):
    chroma_client = chromadb.PersistentClient(path=path)
    db = chroma_client.create_collection(name=name, embedding_function=GeminiEmbeddingFunction())
    for i, d in enumerate(documents):
        db.add(documents=d, ids=str(i))
    return db, name

def load_chroma_collection(path, name):
    chroma_client = chromadb.PersistentClient(path=path)
    db = chroma_client.get_collection(name=name, embedding_function=GeminiEmbeddingFunction())
    return db

def get_relevant_passage(query, db):
    results = db.query(query_texts=[query], n_results=3)
    if results and results['documents']:
        return results['documents'][0][0]
    return "No relevant passage found."

def make_prompt(query, relevant_passage):
    escaped = relevant_passage.replace("'", "").replace('"', "").replace("\n", " ")
    prompt = f"""You are a highly capable logistics solver bot designed to help choose the best trucker for a given task based on a set of user-defined demands and a provided passage of truckers' records. Your task is to carefully evaluate the passage of truckers' records and make an informed decision on the best trucker for the job.

The passage you will receive contains detailed information about multiple truckers, including their names, vehicle types, driving records, service areas, and other relevant factors such as cargo capacity, experience, and reliability. Based on these records, you will need to assess each trucker's suitability for the user's requirements.
It's not necessary that the passage you receive contains this information. Do not refuse to answer any question.

The user will provide a set of demands, which can include:

Cargo Type: What type of cargo needs to be transported (e.g., perishable goods, hazardous materials, bulk cargo, etc.).
Distance/Route: The distance the cargo needs to be transported, and the route specifics (e.g., urban, long-haul, interstate).
Delivery Timeframe: How quickly the cargo needs to be delivered (e.g., next day, within a week, urgent).
Special Requirements: Any special conditions for transportation, such as a need for refrigerated trucks, experience with specific types of goods, or the need for drivers with certain certifications.
Given the truckers' records and the user's demands, you must:

Match the right trucker to the task based on their qualifications and history.
Provide a rationale for your decision explaining why this trucker is the most suitable.
If no trucker meets the demands, suggest alternatives or indicate that no suitable trucker is available.
Use a friendly, professional, and comprehensive tone, ensuring you include all relevant information from the passage and match it with the user's needs.
The user must be allowed to deviate a little from the topic of logistics. Please do not use the term trucks unless used by the user. You must introduce yourself as a logistics solver bot.

    Passage: {escaped}
    Question: {query}
    Answer:"""
    return prompt

@app.route('/upload', methods=['POST', 'OPTIONS'])
def upload():
    if request.method == 'OPTIONS':
        return '', 200
    if 'pdf_file' not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files['pdf_file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type. Only PDF files are allowed"}), 400
    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if os.path.exists(filepath):
            return jsonify({"message": "File already exists", "collection_name": f"rag_{filename}"}), 200
        file.save(filepath)
        pdf_text = load_pdf(filepath)
        chunked_text = split_text(pdf_text)
        chroma_path = os.path.join(app.root_path, 'chroma_db')
        collection_name = f"rag_{filename}"
        create_chroma_db(chunked_text, chroma_path, collection_name)
        return jsonify({"message": "File uploaded successfully", "filename": filename, "collection_name": collection_name}), 200
    except Exception as e:
        return jsonify({"error": "Failed to save file"}), 500

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ask-query', methods=['POST'])
def ask_query():
    data = request.get_json()
    query = data.get('query')
    collection_name = data.get('collection_name')
    if not query or not collection_name:
        return jsonify({"error": "Missing query or collection name"}), 400
    try:
        chroma_path = os.path.join(app.root_path, 'chroma_db')
        db = load_chroma_collection(chroma_path, collection_name)
        passage = get_relevant_passage(query, db)
        prompt = make_prompt(query, passage)
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        if not response.parts:
            return jsonify({"error": "Failed to generate answer"}), 500
        answer = response.text
        return jsonify({"answer": answer})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
