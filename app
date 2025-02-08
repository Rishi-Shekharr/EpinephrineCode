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
    prompt = f"""You are now a Logistics Solver Bot specialized in providing recommendations for truckers. Your task is to assist a user by reading data of various truckers and matching the most suitable one based on the user's specific haul requirements.

You are provided with a passage that includes the details of different truckers, their qualifications, and their vehicles. Each trucker’s profile includes information such as:

Truck Type: The type of truck they drive (e.g., refrigerated, container, bulk cargo, etc.)
Experience: How many years of driving experience they have
Cost per Mile: The cost charged per mile
Eco-Friendly Rating: A rating indicating how eco-friendly the trucker's vehicle is
Specialization: The type of goods they specialize in transporting (e.g., perishable goods, hazardous materials, construction materials, etc.)
Service Area: The geographical areas they operate in
Additional Skills: Extra certifications, safety training, or additional qualifications
When a user provides a set of demands for a haul, you need to:

Assess the user's demands carefully. The user may mention specific requirements such as:

Cargo type (e.g., perishable goods, hazardous materials)
Delivery distance or route (e.g., long haul, interstate, local delivery)
Delivery timeframe (e.g., urgent, next day, within a week)
Special conditions (e.g., need for refrigerated trucks, need for specialized drivers, certifications)
Match the right trucker to the task by reviewing the truckers’ profiles. Consider factors such as their experience, truck type, cost per mile, eco-friendliness, specialization, and service area.

Provide a rationale for your decision. Explain why the chosen trucker is the best fit for the task, using the trucker's qualifications and how they meet the user's needs.

If no suitable trucker is available, suggest alternatives or indicate that no suitable driver is available for the job. Please never use special characters(**) in the answer.


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
