from flask import Flask, request, jsonify, session
from flask_cors import CORS
import fitz  # PyMuPDF
import re
import os
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True) # Allow all origins for dev, supports_credentials for session cookies
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24)) # For session management

# --- OpenAI Client Setup ---
try:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not found in .env. LLM features will be degraded.")
        client = None
except Exception as e:
    print(f"Error initializing OpenAI client: {e}. LLM features may not work.")
    client = None

# --- Ported/Adapted Helper Functions from JavaScript ---

COMMON_BRANDS_LIST_PY = [
    "amul", "verka", "mother dairy", "bonn", "english oven", "harvest gold", "india gate", "daawat", "tata sampann", "aashirvaad", "pillsbury", "fortune", "madhur", "natureland organics", "local farm", "figaro", "patanjali", "saffola gold", "dhara", "tata tea", "tata salt", "lipton", "wagh bakri", "nescafe classic", "bru green label", "davidoff rich aroma", "president", "kapiva", "soyfit", "nestle a+", "epigamia", "everest tikhalal", "mdh deggi mirch", "catch", "parle-g gold", "britannia vita marie gold", "britannia", "mcvities", "mysore sandal gold", "dettol original", "dove cream bar", "patanjali dant kanti advanced", "colgate maxfresh", "sensodyne rapid relief", "surf excel easy wash", "ariel matic top load", "godrej ezee winterwear", "vim", "cadbury", "nestle", "lays", "bingo", "kettle studio", "coca-cola", "sprite", "mirinda", "pepsi black", "real activ", "tropicana", "b natural", "vadilal", "kwality walls cornetto", "kwality walls", "havmor", "maggi cuppa mania", "maggi nutrilicious", "maggi", "samyang buldak", "samyang", "kissan fresh", "kissan", "chings secret", "tops", "kelloggs", "bagrrys", "go", "safal", "mccain", "unibic", "sunfeast", "haldirams", "bikaji", "happilo", "nutraj", "bournvita 5 star magic", "bournvita", "horlicks classic malt", "horlicks", "ensure", "park avenue voyage", "park avenue", "nivea", "head & shoulders cool menthol", "head & shoulders", "clinic plus strong & long", "clinic plus", "lizol", "harpic", "air wick freshmatic", "air wick", "good knight gold flash", "good knight", "whisper", "stayfree secure", "stayfree", "sofy", "pampers all round protection", "pampers", "himalaya gentle", "himalaya", "dr. oetker funfoods", "dr. oetker", "veeba", "wingreens farms", "borges", "barilla", "generic local", "generic brand", "generic farm", "generic good quality", "generic", "imported", "24 mantra organic", "24 mantra"
]

def title_case_py(s):
    if not s or s == "N/A" or not isinstance(s, str):
        return s
    return ' '.join(word.capitalize() if word.lower() not in ['a', 'an', 'the', 'of', 'in', 'on', 'at', 'for', 'to'] or i == 0 else word.lower() for i, word in enumerate(s.lower().split())).strip()


def extract_info_py(line):
    info = {
        "platform": "N/A", "item": "N/A", "brand": "N/A", "cost": "N/A",
        "deals": "N/A", "deliveryTime": "N/A", "quantity": "N/A"
    }
    processed_line = re.sub(r'\s+', ' ', line.strip()) # Normalize spaces

    # 1. Extract Delivery Time
    delivery_time_regex = r'(\d+\s*mins?(?:utes)?|Same Day\s*\(?\s*\d+\s*hour\s*\)?)$'
    delivery_match = re.search(delivery_time_regex, processed_line, re.IGNORECASE)
    if delivery_match:
        info["deliveryTime"] = delivery_match.group(1).strip()
        processed_line = processed_line[:delivery_match.start()].strip()

    # 2. Extract Quantity
    # Regex: (anything)(space)(qty_pattern)(end_of_string OR space_not_followed_by_price)
    # This is tricky because quantity can be before or after item/brand. We'll try to grab it from the end first if it's not part of cost.
    quantity_regex_str = r'((?:\d+\s*x\s*)?\d*\.?\d*\s*(?:L|ml|kg|Kg|gm|GM|g|G|dozen|pcs|pc|pack|packs|bags|bag|unit|units|sachet|combo)(?:s)?(?:\s*\(.+?\))?)$'
    # Try to match quantity at the end of the current processed_line
    qty_parts = processed_line.split()
    # Check last few words for quantity pattern, ensuring it's not part of cost if cost is directly after
    for i in range(len(qty_parts)-1, max(-1, len(qty_parts)-4), -1): # Check last 1 to 3 words
        potential_qty_phrase = " ".join(qty_parts[i:])
        quantity_match = re.match(quantity_regex_str, potential_qty_phrase, re.IGNORECASE)
        if quantity_match:
            # Check if what's *before* this potential quantity is a price (less likely for quantity to follow price)
            # And check if what's *after* this in the original line (if it was delivery time) is not a price
            text_before_potential_qty = " ".join(qty_parts[:i]).strip()
            if not re.search(r'₹\d+(\.\d+)?$', text_before_potential_qty): # If not preceded by a clear price
                info["quantity"] = quantity_match.group(1).strip()
                processed_line = text_before_potential_qty
                break
   
    # 3. Extract Cost and Deals
    words = processed_line.split()
    cost_index = -1
    cost_value = "N/A"

    for i in range(len(words) - 1, -1, -1):
        word_cleaned = words[i].replace('₹', '') # Remove currency symbol for matching
        if re.fullmatch(r'\d+(\.\d+)?', word_cleaned):
            # Check context to avoid matching numbers in deals or quantities
            prev_word = (words[i-1].lower() if i > 0 else "")
            # next_word = (words[i+1].lower() if i < len(words) - 1 else "") # Not used in JS logic

            # If word is part of "Buy X Get Y" or "X% off" etc., it's likely part of a deal, not the main cost
            # This logic is complex in JS, simplified here: if it's a number, assume it's cost unless clearly part of a deal phrase
            # More robust: check if it's the *last* such number not clearly part of a deal.
            if not ( (prev_word in ["buy", "get", "save", "off"] and i > 0) or
                     (re.search(r'(%|percent)\s*(off)?$', " ".join(words[i+1:i+3]), re.IGNORECASE) if i < len(words)-1 else False) or
                     (re.search(r'rs\.?\s*off$', " ".join(words[i+1:i+3]), re.IGNORECASE) if i < len(words)-1 else False)
                   ):
                cost_index = i
                cost_value = words[i] if words[i].startswith('₹') else f'₹{words[i]}'
                break
    info["cost"] = cost_value

    deals_text_after_cost = ""
    if cost_index != -1:
        if cost_index < len(words) - 1: # If there are words after the identified cost
            deals_text_after_cost = " ".join(words[cost_index + 1:]).strip()
        processed_line = " ".join(words[:cost_index]).strip() # Text before cost

    # Extract Deals from remaining processed_line or from after cost
    # This can be complex. The JS version looks for specific patterns.
    current_deals = []
    if deals_text_after_cost:
        current_deals.append(deals_text_after_cost)

    deal_patterns_py = [
        r'\b(BOGO(?: on select items)?)\b', r'\b(Buy \d+ Get \d+(?: Free| % off| ?rs off)?)\b',
        r'\b(\d+\.?\d*% off(?: on .*)?)\b', r'\b(Save up to \d+%?)\b', r'\b(\d+rs off)\b',
        r'\b(Combo Deal(?: with .*)?)\b', r'\b(Flat \d+% off)\b',
        r'\b(No specific deals mentioned)\b', r'\b(No current deal)\b', r'\b(None)\b'
    ]
   
    temp_line_for_deal_search = processed_line # Search in text before cost
    for pattern in deal_patterns_py:
        deal_match = re.search(pattern, temp_line_for_deal_search, re.IGNORECASE)
        if deal_match and len(deal_match.group(1)) > 3:
            # Check if this deal isn't already captured or part of item name
            matched_deal_text = deal_match.group(1).strip()
            if matched_deal_text.lower() not in [d.lower() for d in current_deals]:
                 current_deals.append(matched_deal_text)
            # Attempt to remove matched deal from processed_line to aid item/brand extraction
            # This is risky if patterns are too general.
            # processed_line = temp_line_for_deal_search.replace(deal_match.group(1), "", 1).strip()
            # temp_line_for_deal_search = processed_line # update for next pattern search on modified line
            # For simplicity, we won't remove it from processed_line here to avoid over-complication.
            # The LLM can help disambiguate later.

    if current_deals:
        info["deals"] = ", ".join(d for d in current_deals if d.lower() not in ["none", "no current deal", "no specific deals mentioned"])
        if not info["deals"]: info["deals"] = "No specific deals mentioned"
    elif info["cost"] != "N/A":
        info["deals"] = "No specific deals mentioned"
    else:
        info["deals"] = "N/A"


    # 4. Extract Platform
    platforms_py = ["Blinkit", "Instamart", "Zepto", "Big Basket", "Flipkart Groceries", "Flipkart"] # Order matters for longer names
    temp_processed_line_lower = processed_line.lower()
    for p in platforms_py:
        if temp_processed_line_lower.startswith(p.lower()):
            info["platform"] = p # Use original casing from list
            processed_line = processed_line[len(p):].strip()
            break
   
    # 5. Extract Item and Brand (from remaining processed_line)
    words_for_item_brand = processed_line.split()
    brand_found = False
    item_parts = []
    brand_parts = []

    # Try to find known brands (multi-word brands first)
    # Check from the end of words_for_item_brand
    if words_for_item_brand:
        for i in range(len(words_for_item_brand)):
            # Consider 1, 2, or 3 word sequences as potential brands from the end
            for brand_len in range(min(3, len(words_for_item_brand) - i), 0, -1):
                # potential_brand_candidate = " ".join(words_for_item_brand[i : i + brand_len])
                # Simplified: check from the end if a known brand exists
                # More robust: check if sequence of words at the end forms a known brand
                # This is where sophisticated NER or a more structured source is better.
                # For now, let's try a simpler approach: assume last few words might be brand if not item.
                pass # This section is very hard to port 1:1 due to JS's specific loop structure

        # Simpler heuristic: if last 1-2 words are in COMMON_BRANDS_LIST_PY (case-insensitive)
        # This is a common pattern: "Item Name Item Specifier BRAND"
        num_words = len(words_for_item_brand)
        if num_words > 0:
            # Check 2-word brand first, then 1-word
            if num_words >= 2:
                potential_brand_2words = " ".join(words_for_item_brand[-2:]).lower()
                if potential_brand_2words in COMMON_BRANDS_LIST_PY:
                    info["brand"] = title_case_py(" ".join(words_for_item_brand[-2:]))
                    info["item"] = title_case_py(" ".join(words_for_item_brand[:-2]))
                    brand_found = True
            if not brand_found and num_words >= 1:
                potential_brand_1word = words_for_item_brand[-1].lower()
                if potential_brand_1word in COMMON_BRANDS_LIST_PY:
                    info["brand"] = title_case_py(words_for_item_brand[-1])
                    info["item"] = title_case_py(" ".join(words_for_item_brand[:-1]))
                    brand_found = True
           
            if not brand_found: # If no known brand found at the end
                if num_words > 1 and len(words_for_item_brand[-1]) > 2 and words_for_item_brand[-1][0].isupper(): # Last word is capitalized and decent length
                    info["brand"] = title_case_py(words_for_item_brand[-1])
                    info["item"] = title_case_py(" ".join(words_for_item_brand[:-1]))
                else: # Assume all remaining is item
                    info["item"] = title_case_py(" ".join(words_for_item_brand))
                    info["brand"] = "Generic" # Default if no brand identified
        else: # No words left for item/brand
            info["item"] = "N/A (Content)"
            info["brand"] = "N/A (Content)"

    if not info["item"]: info["item"] = "N/A (Content)" # ensure item is not empty

    # Final check for quantity if still N/A (might be embedded in item/brand if not caught earlier)
    if info["quantity"] == "N/A":
        combined_item_brand_text = f"{info['item']} {info['brand']}".strip()
        # Re-use quantity_regex_str but match anywhere in the combined string
        # And try to extract from the item string itself more directly
        final_qty_match_item = re.search(r'(.*?)\s*' + quantity_regex_str.replace(')$', ')'), info["item"], re.IGNORECASE)
        if final_qty_match_item and final_qty_match_item.group(2):
            info["quantity"] = title_case_py(final_qty_match_item.group(2).strip())
            info["item"] = title_case_py(final_qty_match_item.group(1).strip()) # Update item
        # elif: check in brand similarly if needed

    # Clean up N/a, empty strings
    for k in ["item", "brand", "quantity", "platform", "cost", "deals", "deliveryTime"]:
        if info[k] is None or (isinstance(info[k], str) and (info[k].strip() == "" or info[k].lower() == "n/a" or info[k].lower() == "n/a (content)")):
            if k in ["item", "brand", "quantity"] and info[k] is not None and "content" in info[k].lower():
                 info[k] = "N/A (Content)" # Preserve this specific N/A
            else:
                 info[k] = "N/A"
        elif isinstance(info[k], str):
             info[k] = info[k].strip()

    if info["item"] == "N/A" and info["brand"] != "Generic" and info["brand"] != "N/A":
        # If item is N/A but brand is specific, item might have been absorbed into brand.
        # This is hard to fix without more context.
        pass
    if info["brand"] == "Generic" and info["item"] == "N/A (Content)": info["item"] = "N/A"


    return info


def is_common_query_word_py(word):
    common_words = {
        'for', 'the', 'and', 'a', 'is', 'of', 'find', 'get', 'show', 'me', 'best',
        'cheapest', 'fastest', 'delivery', 'deal', 'deals', 'offer', 'offers', 'on',
        'in', 'what', 'where', 'how', 'much', 'buy', 'item', 'product', 'price', 'cost',
        'discount', 'brand', 'available', 'provide', 'tell', 'about', 'any', 'search', 'top',
        'showme', 'pls', 'please', 'findme', 'look', 'looking'
    }
    return word.lower() in common_words

def parse_delivery_time_to_minutes_py(delivery_time_str):
    if not delivery_time_str or not isinstance(delivery_time_str, str) or delivery_time_str == "N/A":
        return float('inf')
    lower_str = delivery_time_str.lower()
    min_match = re.search(r'(\d+)\s*mins?(?:utes)?', lower_str)
    if min_match:
        return int(min_match.group(1))
    hour_match = re.search(r'(\d+)\s*hour', lower_str)
    if hour_match:
        return int(hour_match.group(1)) * 60
    if "same day" in lower_str:
        return 24 * 60 # Arbitrary large number for same day
    return float('inf')


def search_pdf_data_py(query, pdf_text_data_session):
    lower_query = query.lower()
    combined_results = [] # Store dicts: {line, score, fullInfo, queriedItem}
   
    item_separators = r'\s*\b(?:and|&|,)\b\s*'
    potential_items_in_query_raw = [
        item.strip() for item in re.split(item_separators, lower_query) if item.strip()
    ]

    def clean_query_item_part(item_part):
        item_part = re.sub(r'^(?:best|any|find|search|show me|top|looking for)\s+(?:deal|deals|offer|offers)\s+(?:on|for)\s*', '', item_part, flags=re.IGNORECASE)
        item_part = re.sub(r'^(?:fastest delivery for)\s*', '', item_part, flags=re.IGNORECASE)
        item_part = re.sub(r'\s+(?:best|any|find|search|show me|top)\s+(?:deal|deals|offer|offers)$', '', item_part, flags=re.IGNORECASE)
        item_part = re.sub(r'\s+(?:fastest delivery)$', '', item_part, flags=re.IGNORECASE)
        return item_part.strip()

    potential_items_in_query = [
        clean_query_item_part(p) for p in potential_items_in_query_raw if clean_query_item_part(p)
    ]

    if not potential_items_in_query and query.strip(): # If split results in nothing, use cleaned full query
        single_item_target = clean_query_item_part(lower_query)
        if single_item_target:
            potential_items_in_query.append(single_item_target)
   
    relevant_lines_for_llm_context = []

    if not potential_items_in_query: # General search if no specific items parsed from query
        # print(f"Performing GENERAL search for query: \"{lower_query}\"")
        query_terms_for_general_search = [
            term for term in lower_query.split() if len(term) > 1 and not is_common_query_word_py(term)
        ]
        if not query_terms_for_general_search: # If all words are common, use all words
             query_terms_for_general_search = [term for term in lower_query.split() if term]

        if query_terms_for_general_search:
            for line_content in pdf_text_data_session:
                info = extract_info_py(line_content)
                # Combine relevant fields from info for matching
                searchable_text_from_info = f"{info.get('platform','')} {info.get('item','')} {info.get('brand','')} {info.get('deals','')} {info.get('quantity','')}".lower()
               
                score = 0
                for term in query_terms_for_general_search:
                    if term in searchable_text_from_info:
                        score += 1
                        if info.get('item','N/A').lower() != "n/a" and term in info['item'].lower(): score += 2 # Higher weight for item match
                        if info.get('brand','N/A').lower() != "n/a" and term in info['brand'].lower(): score += 2 # Higher weight for brand match
               
                if score > 0:
                    combined_results.append({"line": line_content, "score": score, "fullInfo": info, "queriedItem": "general"})
                    if line_content not in relevant_lines_for_llm_context:
                         relevant_lines_for_llm_context.append(line_content)
    else: # Specific items identified in query
        for target_item_name_from_query in potential_items_in_query:
            if not target_item_name_from_query: continue

            search_mode_for_item = "general_for_item"
            if "fastest delivery" in lower_query: search_mode_for_item = "fastest_for_item"
            elif "deal" in lower_query or "offer" in lower_query: search_mode_for_item = "best_deal_for_item"
           
            # print(f"Processing item part: \"{target_item_name_from_query}\" with mode: \"{search_mode_for_item}\"")

            # Terms from this specific part of the query (e.g., "apples" from "apples and milk")
            item_specific_search_terms = [
                t for t in target_item_name_from_query.lower().split() if t and not is_common_query_word_py(t)
            ]
            if not item_specific_search_terms: # If all words are common, use all words for this item part
                item_specific_search_terms = [t for t in target_item_name_from_query.lower().split() if t]

            if item_specific_search_terms:
                for line_content in pdf_text_data_session:
                    info = extract_info_py(line_content)
                    # Text from PDF line to match against: item and brand primarily for item-specific search
                    text_from_pdf_line_for_item_match = (
                        (info.get('item','N/A').lower() if info.get('item','N/A') != "N/A" else "") + " " +
                        (info.get('brand','N/A').lower() if info.get('brand','N/A') != "N/A" and info.get('brand','N/A') != "Generic" else "")
                    ).strip()

                    if all(term in text_from_pdf_line_for_item_match for term in item_specific_search_terms):
                        score = len(item_specific_search_terms) * 5 # Base score on number of matching terms
                       
                        if search_mode_for_item == "fastest_for_item":
                            delivery_minutes = parse_delivery_time_to_minutes_py(info.get("deliveryTime"))
                            score += (10000 - delivery_minutes) / 100 # Higher score for faster (scaled)
                        elif search_mode_for_item == "best_deal_for_item":
                            deals_info = info.get("deals", "N/A").lower()
                            if deals_info not in ["n/a", "no specific deals mentioned", "no current deal"]:
                                score += 50 # High bonus for having a deal
                            else:
                                score += 5 # Small bonus even if no deal, for being relevant
                        else: # general_for_item mode
                            deals_info = info.get("deals", "N/A").lower()
                            if deals_info not in ["n/a", "no specific deals mentioned", "no current deal"]:
                                score += 10 # Bonus for having any deal

                        combined_results.append({
                            "line": line_content, "score": score, "fullInfo": info,
                            "queriedItem": target_item_name_from_query
                        })
                        if line_content not in relevant_lines_for_llm_context:
                            relevant_lines_for_llm_context.append(line_content)
   
    # Deduplicate and sort results
    # Using a dictionary to ensure unique (line + queriedItem) combinations, keeping the one with highest score
    unique_results_map = {}
    for res_item in combined_results:
        # Key might need to be more unique if same line can match multiple `queriedItem`s differently
        # For now, line content itself is a good proxy if `queriedItem` mainly serves for display grouping
        key = res_item["line"] # + res_item["queriedItem"] # Potentially add queriedItem for super strict uniqueness
        if key not in unique_results_map or unique_results_map[key]["score"] < res_item["score"]:
            unique_results_map[key] = res_item
   
    final_sorted_results = sorted(list(unique_results_map.values()), key=lambda x: x.get("score", 0), reverse=True)
   
    # Limit relevant lines for LLM context to avoid overly long prompts
    # Select lines from the top sorted results for better context
    top_lines_for_llm = [res["line"] for res in final_sorted_results[:10] if "line" in res] # Max 10 lines from top results
   
    return final_sorted_results[:10], top_lines_for_llm # Return top 10 structured results and context lines

# --- Flask Endpoints ---
@app.route('/upload_pdf', methods=['POST'])
def upload_pdf_route():
    if 'pdfFile' not in request.files:
        return jsonify({"error": "No PDF file provided"}), 400
    file = request.files['pdfFile']
    if file.filename == '':
        return jsonify({"error": "No PDF file selected"}), 400

    if file and file.filename.lower().endswith('.pdf'):
        try:
            pdf_document = fitz.open(stream=file.read(), filetype="pdf")
            extracted_text_lines = []
            for page_num in range(len(pdf_document)):
                page = pdf_document.load_page(page_num)
                # Get text as blocks, then split blocks by newline, then filter
                blocks = page.get_text("blocks", sort=True) # sort=True for reading order
                for b in blocks: # x0, y0, x1, y1, text, block_no, block_type
                    block_text_lines_raw = b[4].split('\n')
                    for line_raw in block_text_lines_raw:
                        line_clean = re.sub(r'\s+', ' ', line_raw.strip()) # Normalize spaces
                        # Filter for meaningful lines (adjust thresholds as needed)
                        if len(line_clean) > 15 and len(line_clean.split()) > 2:
                            extracted_text_lines.append(line_clean)
           
            pdf_document.close()
           
            session['pdf_text_data'] = extracted_text_lines # Store in session

            if not extracted_text_lines:
                return jsonify({"message": "PDF processed, but no usable text found. Try a different PDF.", "status": "warning", "text_found": False}), 200
           
            return jsonify({"message": f"PDF processed! Found {len(extracted_text_lines)} potential lines.", "status": "success", "text_found": True}), 200
        except Exception as e:
            app.logger.error(f"Error processing PDF: {e}", exc_info=True)
            return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500
    else:
        return jsonify({"error": "Invalid file type, please upload a PDF."}), 400

@app.route('/query', methods=['POST'])
def handle_query_route():
    data = request.get_json()
    user_query = data.get('query')

    if not user_query:
        return jsonify({"error": "No query provided"}), 400

    pdf_text_data_session = session.get('pdf_text_data')
    if not pdf_text_data_session: # Or check if it's empty
        return jsonify({"error": "PDF not processed or session expired. Please upload PDF again."}), 400

    # 1. Retrieval Step
    structured_results, context_lines_for_llm = search_pdf_data_py(user_query, pdf_text_data_session)

    # 2. Generation Step (LLM)
    llm_response_text = "Could not generate AI summary due to an issue or missing API key. Displaying rule-based results."
    if client and context_lines_for_llm:
        context_str = "\n".join(context_lines_for_llm) # Use the selected context lines
       
        # Simplified prompt for brevity, expand as needed
        prompt_messages = [
            {"role": "system", "content": "You are Grocee, an AI e-grocery assistant. Your goal is to answer user queries based *only* on the provided PDF context. If the context doesn't mention something, say you cannot find it in the provided document. Be concise and helpful. Present product information clearly, perhaps using bullet points if listing multiple items."},
            {"role": "user", "content": f"""Context from PDF:
---
{context_str}
---
User Query: "{user_query}"

Based *only* on the context above, provide Grocee's Answer:"""}
        ]
        try:
            completion = client.chat.completions.create(
                model="gpt-3.5-turbo-0125", # Or "gpt-4-turbo-preview" if available
                messages=prompt_messages,
                temperature=0.2, # More factual
                max_tokens=400
            )
            llm_response_text = completion.choices[0].message.content.strip()
        except Exception as e:
            app.logger.error(f"OpenAI API error: {e}", exc_info=True)
            llm_response_text = f"Error generating AI summary: {str(e)}. Displaying extracted data."
    elif not client:
         llm_response_text = "AI assistant (OpenAI client) not initialized. API key might be missing. Displaying extracted data."
    elif not context_lines_for_llm:
        llm_response_text = "No specific context found in the PDF relevant to your query to generate an AI summary. Displaying any generally extracted data."


    return jsonify({
        "llm_summary": llm_response_text,
        "structured_results": structured_results # These are the top results from your ported search logic
    })

if __name__ == '__main__':
    app.run(debug=True, port=5001)
