import os
import re
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
import chromadb
from typing import List
from werkzeug.utils import secure_filename
import pytesseract  # Requires Tesseract OCR engine in PATH
from pdf2image import convert_from_path  # Requires Poppler in PATH
from pypdf import PdfReader
import google.generativeai as genai4 # Correctly aliased

# --- Frontend HTML, CSS, and JavaScript ---
HTML_CONTENT = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Grocify</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');

        :root {
            --accent-pink: #E91E63;
            --accent-purple: #9C27B0;
            --primary-blue: #2196F3;
            --secondary-green: #4CAF50;
            --page-bg-start: #E3F2FD;
            --page-bg-mid: #EDE7F6;
            --page-bg-end: #E8F5E9;
            --card-bg: #FFFFFF;
            --container-bg: var(--card-bg);
            --dark-text: #333740;
            --light-text: #FFFFFF;
            --border-color: #E0E0E0;
            --shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            --border-radius: 18px;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Poppins', sans-serif;
            background: linear-gradient(145deg, var(--page-bg-start) 0%, var(--page-bg-mid) 50%, var(--page-bg-end) 100%);
            color: var(--dark-text);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: flex-start;
            min-height: 100vh;
            padding: 40px 20px;
            overflow-x: hidden;
        }

        .container {
            background-color: var(--container-bg);
            padding: 45px 55px;
            border-radius: var(--border-radius);
            box-shadow: var(--shadow);
            width: 100%;
            max-width: 900px;
            text-align: center;
            animation: fadeInScaleUp 1s cubic-bezier(0.165, 0.84, 0.44, 1);
            border: 1px solid var(--border-color);
            margin-bottom: 40px;
        }

        @keyframes fadeInScaleUp {
            from { opacity: 0; transform: translateY(35px) scale(0.95); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }

        header { margin-bottom: 40px; }
        header h1 {
            color: var(--accent-pink);
            font-size: 4em;
            margin-bottom: 15px;
            font-weight: 700;
            letter-spacing: -3px;
            animation: headerFadeInUp 0.9s 0.2s cubic-bezier(0.165, 0.84, 0.44, 1) forwards;
            opacity: 0;
        }
        header p {
            font-size: 1.4em;
            color: var(--dark-text);
            margin-bottom: 0;
            font-weight: 400;
            animation: headerFadeInUp 0.9s 0.45s cubic-bezier(0.165, 0.84, 0.44, 1) forwards;
            opacity: 0;
        }
        @keyframes headerFadeInUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .upload-section, .query-section, .response-section {
            background-color: var(--card-bg);
            padding: 40px;
            border-radius: var(--border-radius);
            margin-bottom: 40px;
            box-shadow: 0 7px 22px rgba(70, 70, 90, 0.09);
            animation: sectionSlideInUp 0.8s cubic-bezier(0.165, 0.84, 0.44, 1) forwards;
            opacity: 0;
            border: 1px solid var(--border-color);
        }
        @keyframes sectionSlideInUp {
            from { opacity: 0; transform: translateY(60px); }
            to { opacity: 1; transform: translateY(0); }
        }
        .upload-section { animation-delay: 0.7s; }

        h2 {
            color: var(--secondary-green);
            margin-bottom: 35px;
            font-weight: 600;
            font-size: 1.9em;
            opacity: 0;
            transform: translateY(20px);
        }
        @keyframes fadeInSlideH2 { to { opacity: 1; transform: translateY(0); } }

        label {
            display: block;
            font-weight: 600;
            margin-bottom: 18px;
            color: var(--dark-text);
            text-align: left;
            font-size: 1.2em;
        }
        input[type="file"] { display: none; }

        .custom-file-upload {
            border: 3px dashed var(--primary-blue);
            border-radius: var(--border-radius);
            display: inline-block;
            padding: 18px 35px;
            cursor: pointer;
            background-color: #E3F2FD;
            color: var(--primary-blue);
            font-weight: 600;
            font-size: 1.1em;
            transition: all 0.25s cubic-bezier(0.165, 0.84, 0.44, 1);
            margin-bottom: 20px;
            animation: pulseButton 2.2s infinite 1.2s;
        }
        @keyframes pulseButton {
            0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(var(--primary-blue), 0.4); }
            70% { transform: scale(1.025); box-shadow: 0 0 0 14px rgba(var(--primary-blue), 0); }
            100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(var(--primary-blue), 0); }
        }
        .custom-file-upload:hover, .custom-file-upload.file-selected {
            animation-play-state: paused;
            transform: scale(1.03) translateY(-3px);
            background-color: var(--primary-blue);
            color: var(--light-text);
            border-color: var(--primary-blue);
        }
        #fileName {
            margin-top: 20px;
            font-style: italic;
            color: var(--dark-text);
            font-size: 1.05em;
        }
        #pdfStatus {
            margin-top: 18px;
            font-weight: 500;
            height: 30px;
            font-size: 1.15em;
        }
        #pdfStatusIcon { margin-right: 10px; font-size: 1.3em; }

        textarea, input[type="text"] {
            width: 100%;
            padding: 20px;
            margin-bottom: 28px;
            border: 1.5px solid var(--border-color);
            border-radius: var(--border-radius);
            font-family: 'Poppins', sans-serif;
            font-size: 1.1em;
            resize: vertical;
            transition: border-color 0.3s ease, box-shadow 0.3s ease, background-color 0.3s ease;
            background-color: #FAFAFC;
        }
        textarea:focus, input[type="text"]:focus {
            border-color: var(--accent-pink);
            outline: none;
            box-shadow: 0 0 0 4px rgba(233, 30, 99, 0.25);
            background-color: var(--card-bg);
        }

        button#submitQuery {
            background: linear-gradient(60deg, var(--accent-pink), var(--accent-purple));
            color: white;
            padding: 20px 40px;
            border: none;
            border-radius: var(--border-radius);
            cursor: pointer;
            font-size: 1.2em;
            font-weight: 600;
            transition: all 0.3s cubic-bezier(0.165, 0.84, 0.44, 1);
            box-shadow: 0 5px 12px rgba(156, 39, 176, 0.3);
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        button#submitQuery:hover:not(:disabled) {
            transform: translateY(-6px) scale(1.03);
            box-shadow: 0 8px 20px rgba(233, 30, 99, 0.4);
        }
        button#submitQuery:disabled {
            background: linear-gradient(60deg, #D1C4E9, #CFD8DC);
            color: #78909C;
            cursor: not-allowed;
            box-shadow: none;
            transform: none;
        }

        #responseArea {
            background-color: #F8F9FE;
            padding: 35px;
            border-radius: var(--border-radius);
            text-align: left;
            min-height: 160px;
            border: 1px solid var(--border-color);
            animation: resultContainerFadeIn 0.7s cubic-bezier(0.165, 0.84, 0.44, 1);
            white-space: pre-wrap;
            line-height: 1.85;
            transition: opacity 0.4s ease-in-out;
        }
        @keyframes resultContainerFadeIn {
            from { opacity: 0; transform: translateY(25px); }
            to { opacity: 1; transform: translateY(0); }
        }
        #responseArea p {
            margin-bottom: 1em;
        }
        #responseArea p:last-child {
            margin-bottom: 0;
        }
        #responseArea .no-results {
            color: var(--accent-pink);
            font-weight: 500;
            text-align: center;
            padding: 40px 30px;
            background-color: #FCE4EC;
            border-radius: var(--border-radius);
            font-size: 1.2em;
            opacity: 0;
            animation: fadeInNoResults 0.6s ease-out forwards;
            border: 2px dashed var(--accent-pink);
        }
        @keyframes fadeInNoResults { to { opacity: 1; } }

        .loader {
            border: 8px solid #E8EAF6;
            border-top: 8px solid var(--accent-pink);
            border-radius: 50%;
            width: 55px;
            height: 55px;
            animation: spin 0.8s linear infinite;
            margin: 40px auto;
            display: none;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .query-section, .response-section { display: none; opacity: 0; }
        .query-section.visible, .response-section.visible {
            display: block;
            opacity: 1;
            animation: sectionSlideInUp 0.8s cubic-bezier(0.165, 0.84, 0.44, 1) forwards;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Grocify</h1>
            <p>Hello, I am Grocee. Let's fresh fetch!</p>
        </header>

        <section class="upload-section">
            <h2>1. Upload Your E-Groceries PDF</h2>
            <label for="pdfFile" class="custom-file-upload">✨ Choose PDF File ✨</label>
            <input type="file" id="pdfFile" accept=".pdf">
            <p id="fileName">No file selected.</p>
            <p id="pdfStatus">
                <span id="pdfStatusIcon"></span><span id="pdfStatusText"></span>
            </p>
        </section>

        <section class="query-section" id="querySection">
            <h2>2. Ask Grocee</h2>
            <label for="userQuery">Enter your query (e.g., "best deal on apples and milk", "fastest delivery for bread"): </label>
            <textarea id="userQuery" rows="4" placeholder="What are you looking for today? 🥕🍓🍞"></textarea>
            <button id="submitQuery" disabled>Fetch Groceries Info</button>
        </section>

        <section class="response-section" id="responseSection">
            <h2>3. Grocee's Insights</h2>
            <div class="loader" id="loader"></div>
            <div id="responseArea">
                Awaiting your query...
            </div>
        </section>
    </div>

    <script>
        const pdfFileInput = document.getElementById('pdfFile');
        const fileNameDisplay = document.getElementById('fileName');
        const pdfStatusDisplay = document.getElementById('pdfStatus');
        const pdfStatusIcon = document.getElementById('pdfStatusIcon');
        const pdfStatusText = document.getElementById('pdfStatusText');
        const querySection = document.getElementById('querySection');
        const userQueryInput = document.getElementById('userQuery');
        const submitQueryButton = document.getElementById('submitQuery');
        const responseSection = document.getElementById('responseSection');
        const responseArea = document.getElementById('responseArea');
        const loader = document.getElementById('loader');
        const customFileUploadButton = document.querySelector('.custom-file-upload');

        let currentCollectionName = null;

        pdfFileInput.addEventListener('change', handlePdfUpload);

        function showSection(sectionElement) {
            sectionElement.style.display = 'block';
            setTimeout(() => {
                 sectionElement.classList.add('visible');
                const h2 = sectionElement.querySelector('h2');
                if (h2) {
                    h2.style.opacity = 0;
                    h2.style.transform = 'translateY(20px)';
                    setTimeout(() => {
                         h2.style.animation = 'fadeInSlideH2 0.6s 0.25s cubic-bezier(0.165, 0.84, 0.44, 1) forwards';
                    }, 20);
                }
            }, 10);
        }
        function hideSection(sectionElement) {
            sectionElement.classList.remove('visible');
            const h2 = sectionElement.querySelector('h2');
            if (h2) h2.style.animation = 'none';

            setTimeout(() => {
                if (!sectionElement.classList.contains('visible')) {
                    sectionElement.style.display = 'none';
                }
            }, 800);
        }

        async function handlePdfUpload(event) {
            const file = event.target.files[0];

            hideSection(querySection);
            hideSection(responseSection);
            submitQueryButton.disabled = true;
            responseArea.innerHTML = "Awaiting your query...";
            currentCollectionName = null;

            if (file && file.type === "application/pdf") {
                fileNameDisplay.textContent = `Selected: ${file.name}`;
                customFileUploadButton.classList.add('file-selected');
                pdfStatusIcon.textContent = "⏳";
                pdfStatusText.textContent = "Uploading and processing PDF with Grocee's brain...";
                pdfStatusDisplay.style.color = "var(--primary-blue)";
                loader.style.display = 'block';

                const formData = new FormData();
                formData.append('pdf_file', file);

                try {
                    const response = await fetch('/upload', {
                        method: 'POST',
                        body: formData
                    });

                    loader.style.display = 'none';
                    const result = await response.json();

                    if (response.ok) {
                        currentCollectionName = result.collection_name;
                        pdfStatusIcon.textContent = "✅";
                        pdfStatusText.textContent = `PDF "${result.filename}" processed! You can now ask Grocee.`;
                        pdfStatusDisplay.style.color = "var(--secondary-green)";
                        showSection(querySection);
                        showSection(responseSection);
                        submitQueryButton.disabled = false;
                        responseArea.innerHTML = "PDF data loaded. Ready for your query!";
                        userQueryInput.focus();
                    } else {
                        pdfStatusIcon.textContent = "❌";
                        pdfStatusText.textContent = `Error: ${result.error || 'Failed to process PDF.'}`;
                        pdfStatusDisplay.style.color = "var(--accent-pink)";
                        fileNameDisplay.textContent = "No file selected.";
                        customFileUploadButton.classList.remove('file-selected');
                    }
                } catch (error) {
                    loader.style.display = 'none';
                    console.error("Error uploading PDF:", error);
                    pdfStatusIcon.textContent = "❌";
                    pdfStatusText.textContent = "Network error or server unavailable. Please try again.";
                    pdfStatusDisplay.style.color = "var(--accent-pink)";
                    fileNameDisplay.textContent = "No file selected.";
                    customFileUploadButton.classList.remove('file-selected');
                }

            } else {
                fileNameDisplay.textContent = "No file selected or invalid file type (PDF only).";
                customFileUploadButton.classList.remove('file-selected');
                pdfStatusIcon.textContent = "";
                pdfStatusText.textContent = "";
            }
        }

        submitQueryButton.addEventListener('click', handleQuerySubmit);
        userQueryInput.addEventListener('keypress', function(event) {
            if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                if (!submitQueryButton.disabled) handleQuerySubmit();
            }
        });

        async function handleQuerySubmit() {
            const query = userQueryInput.value.trim();

            if (!query) {
                displayBackendAnswer("<p class='no-results'>Please enter a query.</p>", true);
                return;
            }
            if (!currentCollectionName) {
                displayBackendAnswer("<p class='no-results'>Please upload and process a PDF first.</p>", true);
                return;
            }

            loader.style.display = 'block';
            responseArea.style.opacity = 0;
            submitQueryButton.disabled = true;
            userQueryInput.disabled = true;

            try {
                const response = await fetch('/ask-query', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        query: query,
                        collection_name: currentCollectionName
                    })
                });

                const result = await response.json();
                if (response.ok) {
                    displayBackendAnswer(result.answer);
                } else {
                    displayBackendAnswer(`<p class='no-results'>Error from Grocee: ${result.error || 'Failed to get an answer.'}</p>`, true);
                }

            } catch (error) {
                console.error("Error asking query:", error);
                displayBackendAnswer("<p class='no-results'>Network error or server unavailable while asking query.</p>", true);
            } finally {
                loader.style.display = 'none';
                submitQueryButton.disabled = false;
                userQueryInput.disabled = false;
                userQueryInput.focus();
            }
        }

        function displayBackendAnswer(answerText, isHtml = false) {
            responseArea.style.opacity = 0;
            setTimeout(() => {
                if (isHtml) {
                    responseArea.innerHTML = answerText;
                } else {
                    // Corrected HTML escaping
                    const escapedText = answerText.replace(/&/g, "&").replace(/</g, "<").replace(/>/g, ">");
                    responseArea.innerHTML = `<pre style="white-space: pre-wrap; word-wrap: break-word;">${escapedText}</pre>`;
                }
                responseArea.style.opacity = 1;
            }, 100);
        }

        // Initial state
        hideSection(querySection);
        hideSection(responseSection);

    </script>
</body>
</html>
"""

# --- Backend Python Code ---

# --- IMPORTANT: GEMINI API Key ---
# YOU MUST REPLACE THIS WITH A VALID API KEY FROM GOOGLE AI STUDIO
# Get one from https://aistudio.google.com/
os.environ["GEMINI_API_KEY"] = "AIzaSyC8VPxBuO7S18aRZyyeLOABQC7INaOQ9Kg" # REPLACE THIS KEY!

app = Flask(__name__) # Corrected: __name__
CORS(app)

# --- Configuration ---
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'pdf'}
app.config['CHROMA_DB_PATH'] = 'chroma_db'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__) # Corrected: __name__

# --- Ensure directories exist ---
try:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['CHROMA_DB_PATH'], exist_ok=True)
except OSError as e:
    logger.error(f"Error creating necessary directories: {e}")


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def extract_text_with_ocr(file_path):
    logger.info(f"Attempting OCR for {file_path}")
    try:
        images = convert_from_path(file_path)
        if not images:
            logger.warning(f"pdf2image returned no images for OCR from {file_path}.")
            return ""
        text = ""
        for i, image in enumerate(images):
            try:
                logger.debug(f"Processing page {i + 1} with OCR...")
                text += pytesseract.image_to_string(image)
            except pytesseract.TesseractError as te:
                logger.error(f"Tesseract error on page {i + 1} of {file_path}: {te}")
        logger.info(f"OCR extraction completed for {file_path}. Length: {len(text)}")
        return text
    except Exception as e:
        logger.error(f"General OCR extraction failed for {file_path}: {e}")
        if "poppler" in str(e).lower():
            logger.error("Critical: Poppler might not be installed or not in PATH. pdf2image depends on it.")
        if "tesseract" in str(e).lower() or "៉" in str(e) or "Failed to initialize tesseract" in str(e):
            logger.error("Critical: Tesseract might not be installed, not in PATH, or language data missing.")
        return ""


def load_pdf(file_path):
    logger.info(f"Loading PDF: {file_path}")
    text = ""
    try:
        reader = PdfReader(file_path)
        if not reader.pages:
            logger.warning(f"No pages found in PDF: {file_path}. Attempting OCR.")
            return extract_text_with_ocr(file_path)

        for i, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
                else:
                    logger.warning(f"Page {i + 1} in {file_path} has no extractable text (might be image-based).")
            except Exception as page_e:
                logger.error(f"Error extracting text from page {i + 1} of {file_path} with PyPDF: {page_e}")

        if not text.strip() or len(text.strip()) < 100:
            logger.warning(
                f"Extracted text from {file_path} via PyPDF is very short or empty. Attempting OCR for the entire document.")
            text_ocr = extract_text_with_ocr(file_path)
            if text_ocr:
                text = text_ocr

    except FileNotFoundError:
        logger.error(f"PDF file not found at path: {file_path}")
        return ""
    except Exception as e:
        logger.error(f"Error reading PDF {file_path} with PyPDF: {e}. Attempting OCR as fallback.")
        text = extract_text_with_ocr(file_path)

    if not text.strip():
        logger.warning(f"No text could be extracted from {file_path} after all attempts.")
    return text


def split_text(text: str):
    split_text_list = re.split(r'\n+', text)
    final_chunks = []
    for chunk in split_text_list:
        chunk = chunk.strip()
        if chunk:
            final_chunks.append(chunk)

    min_words_per_chunk = 5
    meaningful_chunks = [c for c in final_chunks if len(c.split()) >= min_words_per_chunk]

    if not meaningful_chunks and final_chunks:
        logger.warning(
            f"Text splitting resulted in no chunks meeting min_words criteria ({min_words_per_chunk}), but original split had {len(final_chunks)} items. Consider reviewing PDF content or splitting logic if this is unexpected.")
        return final_chunks

    return meaningful_chunks


class GeminiEmbeddingFunction(chromadb.EmbeddingFunction):
    def __call__(self, input: List[str]) -> List[List[float]]: # Corrected: __call__
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key or gemini_api_key == "YOUR_NEW_AI_STUDIO_API_KEY_HERE" or gemini_api_key == "AIzaSyD1_C3wpg_sw6H51e9oXdZ1pzd_6WkGiYo": # Check placeholder
            logger.error("CRITICAL: Gemini API Key is a placeholder or not set for embedding.")
            raise ValueError("Gemini API Key not configured for embedding function.")
        try:
            genai4.configure(api_key=gemini_api_key) # Corrected: genai4
        except Exception as e:
            logger.error(f"Failed to configure Gemini API: {e}")
            raise ValueError(f"Gemini API configuration failed: {e}")

        model = "models/embedding-001"
        all_embeddings: List[List[float]] = []
        batch_size = 100

        input_texts: List[str] = list(input)

        for i in range(0, len(input_texts), batch_size):
            batch = input_texts[i:i + batch_size]
            if not batch:
                continue
            try:
                logger.debug(f"Embedding batch of {len(batch)} documents with Gemini.")
                results = genai4.embed_content( # Corrected: genai4
                    model=model,
                    content=batch,
                    task_type="retrieval_document"
                )
                batch_embeddings = results.get('embedding')

                if batch_embeddings is None:
                    logger.error(f"Gemini API did not return 'embedding' key for batch starting at index {i}.")
                    raise ValueError("Gemini API response missing 'embedding' data.")

                if not isinstance(batch_embeddings, list):
                    logger.error(f"Unexpected type for batch_embeddings: {type(batch_embeddings)}")
                    raise ValueError("Gemini API returned unexpected embedding format (not a list).")

                if len(batch) == 1 and batch_embeddings and isinstance(batch_embeddings[0], float): # Single doc in batch
                     all_embeddings.append(batch_embeddings)
                elif all(isinstance(emb, list) for emb in batch_embeddings): # Multiple docs in batch
                    all_embeddings.extend(batch_embeddings)
                else: # Should not happen if API behaves
                    logger.error(f"Unexpected internal structure of batch_embeddings: {[type(e) for e in batch_embeddings]}")
                    raise ValueError("Gemini API returned unexpected embedding structure within the list.")


            except Exception as e:
                logger.error(f"Error embedding content with Gemini for batch starting at index {i}: {e}")
                raise RuntimeError(f"Gemini embedding failed for a batch: {e}") from e

        if len(all_embeddings) != len(input_texts):
            logger.error(
                f"Mismatch in number of embeddings ({len(all_embeddings)}) vs input texts ({len(input_texts)}).")
            raise ValueError("Embedding count mismatch after Gemini processing.")

        return all_embeddings


def create_chroma_db(documents: List[str], name: str):
    chroma_path = app.config['CHROMA_DB_PATH']
    logger.info(f"Attempting to create/load ChromaDB collection '{name}' at path '{chroma_path}'")
    try:
        chroma_client = chromadb.PersistentClient(path=chroma_path)
    except Exception as e:
        logger.error(f"Failed to initialize ChromaDB PersistentClient at {chroma_path}: {e}")
        raise RuntimeError(f"ChromaDB client initialization failed: {e}") from e

    try:
        db_collection = chroma_client.get_or_create_collection(name=name, embedding_function=GeminiEmbeddingFunction())
        logger.info(f"Successfully accessed/created collection: {name}")
    except Exception as e_get_create:
        logger.error(f"Error with get_or_create_collection for '{name}': {e_get_create}.")
        # This fallback logic might sometimes be problematic if the initial error was due to the embedding function
        # and the embedding function is still broken.
        try:
            logger.info(f"Attempting explicit creation of collection '{name}' as fallback.")
            db_collection = chroma_client.create_collection(name=name,
                                                            embedding_function=GeminiEmbeddingFunction())
        except chromadb.errors.DuplicateCollectionException:
            logger.warning(f"Collection '{name}' confirmed to already exist. Getting it.")
            db_collection = chroma_client.get_collection(name=name,
                                                          embedding_function=GeminiEmbeddingFunction())
        except Exception as e_create_final:
            logger.error(
                f"Fatal error creating or getting collection '{name}' after fallback: {e_create_final}")
            raise RuntimeError(
                f"ChromaDB collection handling failed for '{name}': {e_create_final}") from e_create_final

    if documents:
        doc_ids = [str(i) for i in range(len(documents))]
        try:
            logger.info(
                f"Adding/updating {len(documents)} documents in collection '{name}'. First doc snippet: '{documents[0][:50]}...'")
            db_collection.add(documents=documents, ids=doc_ids)
            logger.info(f"Successfully added/updated documents in collection '{name}'.")
        except Exception as e_add: # This is where the error from the screenshot was triggered
            logger.error(f"Error adding documents to ChromaDB collection '{name}': {e_add}")
            # The original error message "Gemini API configuration failed: name 'genai' is not defined in add"
            # would be part of e_add if it propagated correctly from GeminiEmbeddingFunction.
            # If the ValueError("Gemini API Key not configured...") or ValueError("Gemini API configuration failed...")
            # was raised in __call__, it would be the cause here.
            raise RuntimeError(f"Failed to add documents to '{name}': {e_add}") from e_add
    else:
        logger.info(f"No documents provided to add to collection '{name}'.")

    return db_collection, name


def load_chroma_collection(name: str):
    chroma_path = app.config['CHROMA_DB_PATH']
    logger.info(f"Loading ChromaDB collection '{name}' from path '{chroma_path}'")
    try:
        chroma_client = chromadb.PersistentClient(path=chroma_path)
        db_collection = chroma_client.get_collection(name=name, embedding_function=GeminiEmbeddingFunction())
        logger.info(f"Successfully loaded collection '{name}'.")
        return db_collection
    except chromadb.errors.CollectionNotDefinedError:
        logger.error(f"Collection '{name}' does not exist at '{chroma_path}'.")
        raise ValueError(
            f"Collection '{name}' not found. Please ensure the PDF was uploaded and processed successfully.")
    except Exception as e:
        logger.error(f"Failed to load collection '{name}': {e}")
        raise RuntimeError(f"Error loading collection '{name}': {e}") from e


def get_relevant_passage(query: str, db_collection, n_results: int = 5):
    logger.debug(f"Querying collection '{db_collection.name}' for: '{query}' with n_results={n_results}")
    try:
        results = db_collection.query(query_texts=[query], n_results=n_results)

        if results and results.get('documents') and isinstance(results['documents'], list) and results[
            'documents'] and isinstance(results['documents'][0], list) and results['documents'][0]:
            relevant_doc_strings = results['documents'][0]
            relevant_passages_text = "\n---\n".join(relevant_doc_strings)
            logger.debug(f"Found {len(relevant_doc_strings)} relevant passages. Snippet: {relevant_passages_text[:200]}...")
            return relevant_passages_text

        logger.warning(
            f"No relevant passages found in DB for query: '{query}' in collection '{db_collection.name}'. Query result: {results}")
        return "No relevant passage found in the document."
    except Exception as e:
        logger.error(f"Error querying ChromaDB collection '{db_collection.name}': {e}")
        return f"Error retrieving passages from the document: {e}"

# MODIFIED make_prompt FUNCTION STARTS HERE
def make_prompt(query: str, relevant_passage: str):
    escaped_passage = relevant_passage.replace("\n", " ").strip()
    if not escaped_passage:
        escaped_passage = "(No relevant passage content was found in the document for this query)"

    prompt = f"""You are Grocee, a friendly and helpful Grocery Assistant Bot. You are specialized in assisting,comparing, providing recommendations for e-groceries from various quick commerce platforms like blinkit,zepto,instamart and big basket. Your task is to assist a user by reading data of various items from various platforms and matching the most suitable one based on the user's specific haul requirements.

You are provided with a passage that includes the details of different items, their name, the different platforms on which they are available, their brand, quantity, deals and offers on them, their average delivery time. Each item  will include information such as:

Category Type: The type of category the item belongs to  (e.g., groceries,essentials,miscellaneous, etc.)
Item : The name of the item (e.g.,milk,sugar,bread,eggs,curd,apples,oranges,juice,LED, etc.)
Brand: The name of the brand that makes that item or items (e.g.,Amul,Mother Dairy,Bonn,Verka,Fortune, etc.)
Quantity: The quantity of the item available (e.g., 1p,2p,2.5kg,500g, etc.)
Deals and Offers:The deals and offers that the user will be getting on the searched item or items(e.g., Save Rs.10, BOGO, Get flat 10%off on paying with gpay, etc.)
Average Delivery time: The delivery time for the item searched
Additional Skills: Valuable suggestions, comments,ratings
When a user provides a set of demands for a haul, you need to:

1. Assess the user's demands carefully. The user may mention specific requirements such as:
    - Category  (e.g., groceries,essentials,miscellaneous, etc.)
    - Item name (e.g.,milk,sugar,bread,eggs,curd,apples,oranges,juice,LED, etc.)
    - Brand (e.g.,Amul,Mother Dairy,Bonn,Verka,Fortune, etc.)
    - Special conditions (e.g., fastest delivery for a paticular item or items, best deal on a paticular item or items, etc.)
2. Match the right platform and indformation regarding the item or items by reviewing the data. Consider factors such as  details of different items, their name, the different platforms on which they are available, their brand, quantity,deals and offers and average delivery time.
3. Provide a rationale for your decision. Explain why the chosen platform and other parameters like brand, deal, quantity, delivery time is the best fit for the user's search, using the data and how they meet the user's needs.

If no suitable answer is available in the provided passage, state that the information is not found in the document.
Please never use special characters like ** or ## in the answer. Use plain text and clear formatting. You can use bullet points starting with '-' or numbered lists if appropriate for readability, but avoid Markdown styling characters that might not render well.

✨ Interactive Response Style Guide: ✨
To make your response super interactive and friendly, please use relevant emojis and symbols *before* key pieces of information. Your goal is to be clear, helpful, and engaging! Here are some suggestions for the types of information you'll be providing:

    - 👋 Greeting/Intro: Start with a friendly hello!
    - 🏷️ Category Type: [e.g., Groceries, Essentials]
    - 🛒 Item: [e.g., Milk, Bread, Apples] (Feel free to use specific emojis for items too, like 🥛 for milk, 🍞 for bread!)
    - 🏢 Brand: [e.g., Amul, Mother Dairy]
    - ⚖️ Quantity/Size: [e.g., 1 piece, 2.5kg, 500g]
    - 💰 Deals & Offers: [e.g., Save Rs.10, BOGO, 10% off]
    - ⏰ Average Delivery Time: [e.g., ~10 mins, 30-45 mins]
    - 🌐 Platform: [e.g., Blinkit, Zepto, Instamart]
    - ⭐ Ratings/Comments: [e.g., 4.5 stars, "Highly recommended!"]
    - 💡 Suggestions/Additional Info/Tips: [Your valuable insights]
    - 🤔 Rationale/Reasoning: [Your explanation for the recommendation]
    - ✔️ Matched Requirement: [When confirming a specific user demand is met, e.g., "Fastest Delivery Option:"]
    - 🎯 Summary/Conclusion: A brief wrap-up if needed.

Feel free to use other relevant emojis where they naturally fit and enhance readability. Remember to maintain plain text and the clear formatting guidelines previously mentioned.

Passage from document:
---
{escaped_passage}
---
User's Question: {query}
Answer:"""
    return prompt
# MODIFIED make_prompt FUNCTION ENDS HERE


@app.route('/')
def index():
    return HTML_CONTENT


@app.route('/upload', methods=['POST', 'OPTIONS'])
def upload_file_route():
    if request.method == 'OPTIONS':
        response = jsonify({'message': 'OPTIONS request successful'})
        return response, 200

    if 'pdf_file' not in request.files:
        logger.warning("Upload API: No 'pdf_file' part in the request.")
        return jsonify({"error": "No file part in the request"}), 400

    file_obj = request.files['pdf_file']
    if file_obj.filename == '':
        logger.warning("Upload API: No file selected (empty filename).")
        return jsonify({"error": "No file selected"}), 400

    if not file_obj or not allowed_file(file_obj.filename):
        logger.warning(
            f"Upload API: Invalid file type or no file object for '{file_obj.filename if file_obj else 'N/A'}'")
        return jsonify({"error": "Invalid file type. Only PDF files are allowed"}), 400

    filename = secure_filename(file_obj.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    base_filename, file_ext = os.path.splitext(filename)
    sanitized_base = re.sub(r'[^a-zA-Z0-9_-]', '_', base_filename)
    sanitized_base = re.sub(r'_+', '_', sanitized_base).strip('_')
    if not sanitized_base: sanitized_base = "default_pdf"
    collection_name_prefix = "rag_"
    max_base_len = 63 - len(collection_name_prefix) - 5 # Max 63, plus some buffer for suffixes Chroma might add
    collection_name = f"{collection_name_prefix}{sanitized_base[:max_base_len]}"

    # ChromaDB collection name validation (basic)
    if len(collection_name) > 2 and (not collection_name[0].isalnum() or not collection_name[-1].isalnum()):
         collection_name = "c" + collection_name.strip('_')[:60] + "c" # Ensure start/end alphanumeric
    if len(collection_name) < 3:
        collection_name = collection_name + "xxx" # Ensure min length
    collection_name = collection_name[:63] # Ensure max length

    logger.info(f"Upload API: Processing file '{filename}', target collection name: '{collection_name}'")

    try:
        file_obj.save(filepath)
        logger.info(f"Upload API: File '{filename}' saved to '{filepath}'")

        pdf_text = load_pdf(filepath)
        if not pdf_text or not pdf_text.strip():
            logger.error(f"Upload API: No text extracted from '{filename}'. Cannot create embeddings.")
            return jsonify({"error": f"Failed to extract any text from the PDF: {filename}."}), 500

        chunked_text = split_text(pdf_text)
        if not chunked_text:
            logger.error(
                f"Upload API: Text extracted from '{filename}', but no usable chunks after splitting.")
            return jsonify(
                {"error": f"PDF text from {filename} was extracted but resulted in no usable content chunks."}), 500

        logger.info(
            f"Upload API: Successfully chunked text from '{filename}'. Number of chunks: {len(chunked_text)}")

        create_chroma_db(chunked_text, collection_name) # This is where the error in the screenshot originated

        return jsonify(
            {"message": "File uploaded and processed successfully", "filename": filename, "collection_name": collection_name}), 200

    except RuntimeError as re_err:
        logger.error(f"Upload API: Runtime error during processing for '{filename}': {re_err}")
        return jsonify({"error": f"Processing error: {str(re_err)}"}), 500
    except Exception as e:
        logger.exception(
            f"Upload API: Unexpected error during file upload/processing for '{filename}': {e}")
        return jsonify({"error": f"Failed to upload or process file: {str(e)}"}), 500


@app.route('/ask-query', methods=['POST'])
def ask_query_route():
    model_name_to_use = 'gemini-1.5-flash' # Changed this based on our previous conversation.
                                        # If you meant to keep 'gemini-2.0-flash', please adjust.
    try:
        data = request.get_json()
        if not data:
            logger.warning("Ask-Query API: No JSON data received.")
            return jsonify({"error": "No JSON data received"}), 400

        query = data.get('query')
        collection_name = data.get('collection_name')

        if not query:
            logger.warning("Ask-Query API: Missing 'query' in request.")
            return jsonify({"error": "Missing query"}), 400
        if not collection_name:
            logger.warning("Ask-Query API: Missing 'collection_name' in request.")
            return jsonify({"error": "Missing collection_name (PDF not processed or selected?)"}), 400

        logger.info(f"Ask-Query API: Received query: '{query}' for collection: '{collection_name}'")

        db_collection = load_chroma_collection(collection_name)
        passage = get_relevant_passage(query, db_collection)

        if passage == "No relevant passage found in the document.":
            logger.warning(
                f"Ask-Query API: No relevant passage found for query '{query}' in '{collection_name}'. Responding to user directly.")
            return jsonify({
                               "answer": f"I couldn't find specific information related to your query \"{query}\" in the uploaded document. You could try rephrasing your question, or ensure the document contains the details you're looking for."})
        elif "Error retrieving passages" in passage:
            logger.error(
                f"Ask-Query API: Error retrieving passages for query '{query}' in '{collection_name}'. Passage content: {passage}")
            return jsonify({"error": f"An error occurred while searching the document: {passage}"}), 500

        prompt = make_prompt(query, passage)

        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key or gemini_api_key == "YOUR_NEW_AI_STUDIO_API_KEY_HERE" or gemini_api_key == "AIzaSyD1_C3wpg_sw6H51e9oXdZ1pzd_6WkGiYo": # Check placeholder
            logger.error("CRITICAL: Ask-Query API: Gemini API Key is a placeholder or not set.")
            return jsonify({"error": "Gemini API Key not configured on server."}), 500
        genai4.configure(api_key=gemini_api_key) # Corrected: genai4

        model = genai4.GenerativeModel(model_name_to_use) # Corrected: genai4

        logger.debug(
            f"Ask-Query API: Generating content with Gemini using model '{model.model_name}'. Prompt snippet: {prompt[:300]}...")
        response = model.generate_content(prompt)

        answer_text = ""
        try:
            answer_text = response.text
        except ValueError as ve_text: # Handle cases where .text might be blocked
            logger.warning(f"Ask-Query API: Accessing response.text failed: {ve_text}. Checking prompt_feedback.")
        except Exception as e_text: # Other unexpected errors
            logger.error(f"Ask-Query API: Unexpected error accessing response.text: {e_text}")


        if answer_text:
            logger.info(f"Ask-Query API: Generated answer. Snippet: {answer_text[:200]}...")
            return jsonify({"answer": answer_text})
        else:
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                feedback = response.prompt_feedback
                logger.error(
                    f"Ask-Query API: Gemini response was empty or blocked. Prompt feedback: {feedback}")
                block_reason_message = "The model's response was blocked."
                if feedback.block_reason: # Accessing enum if it exists
                    block_reason_message += f" Reason: {feedback.block_reason.name}." # Use .name for enum
                if feedback.safety_ratings:
                     block_reason_message += f" Safety ratings: {[str(sr) for sr in feedback.safety_ratings]}"

                return jsonify({
                                   "error": f"{block_reason_message} Please try rephrasing your query or contact support if this persists."}), 500
            else:
                 logger.error(
                    f"Ask-Query API: Gemini response has no text and no prompt_feedback. Query: {query}")
                 return jsonify(
                    {"error": "Failed to generate an answer from the AI model (empty or malformed response)."}), 500


    except ValueError as ve:
        logger.error(f"Ask-Query API: ValueError: {ve}")
        if "not found" in str(ve).lower() and "collection" in str(ve).lower():
            return jsonify({"error": str(ve)}), 404 # Collection not found
        return jsonify({"error": str(ve)}), 400 # Other ValueErrors (e.g., bad request data)
    except RuntimeError as re_err:
        logger.error(f"Ask-Query API: Runtime error: {re_err}")
        return jsonify({"error": f"A runtime error occurred: {str(re_err)}"}), 500
    except Exception as e:
        logger.exception(
            f"Ask-Query API: Unexpected error for query '{data.get('query', 'N/A') if data else 'N/A'}': {e}")
        # Check for common API key / model access issues
        if "API key not valid" in str(e).lower() or \
           "permission_denied" in str(e).lower() or \
           ("models/" in str(e) and "not found for API version" in str(e).lower()):
            error_message = f"The AI model or API key is not configured correctly, or the requested model is unavailable. Please check your Gemini API key, project settings, and ensure the model '{model_name_to_use}' is available for your account. Original error: {str(e)}"
            logger.error(f"Ask-Query API: {error_message}")
            return jsonify({"error": error_message}), 500
        return jsonify({"error": f"An unexpected server error occurred: {str(e)}"}), 500


if __name__ == '__main__': # Corrected: __name__
    logger.info("----- Starting Grocify Flask App -----")
    logger.info("IMPORTANT: Ensure Tesseract OCR and Poppler utilities are installed and in your system's PATH.")

    placeholder_key1 = "YOUR_NEW_AI_STUDIO_API_KEY_HERE"
    placeholder_key2 = "AIzaSyD1_C3wpg_sw6H51e9oXdZ1pzd_6WkGiYo" # The key from your code
    current_api_key = os.getenv("GEMINI_API_KEY")

    if not current_api_key or current_api_key == placeholder_key1 or current_api_key == placeholder_key2:
        logger.error(
            f"CRITICAL: GEMINI_API_KEY is not set or is still a placeholder ('{current_api_key}').")
        logger.error(
            "Please get a valid API key from https://aistudio.google.com/ and set it as an environment variable or directly in the code (less secure).")
        logger.error("The application WILL NOT WORK until a valid API key is provided.")
    else:
        logger.info(f"GEMINI_API_KEY is SET. (Value is hidden for security in logs).")

    app.run(debug=True, host='0.0.0.0', port=5000)