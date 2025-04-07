# screen_teacher_streamlit.py
import streamlit as st
import streamlit.components.v1 as components # Import components
import google.generativeai as genai
from gtts import gTTS
from deep_translator import GoogleTranslator
from PIL import Image
import io
import os
import time
import traceback

# --- Configuration & API Key Handling ---
GOOGLE_API_KEY = None
API_KEY_SOURCE = "Not Set"

# 1. Try getting API key from Streamlit secrets (priority)
try:
    if 'GOOGLE_API_KEY' in st.secrets:
        GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
        API_KEY_SOURCE = "Streamlit Secrets"
    else:
         # Check environment variable as a fallback (common for local dev)
        if 'GOOGLE_API_KEY' in os.environ:
             GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
             API_KEY_SOURCE = "Environment Variable"
        else:
             # Last fallback: Hardcoded placeholder (least secure, requires user action)
             # IMPORTANT: Replace only if you understand the security risk
             _placeholder_key = 'YOUR_API_KEY_HERE' # Replace ONLY if absolutely necessary
             if _placeholder_key != 'YOUR_API_KEY_HERE':
                  GOOGLE_API_KEY = _placeholder_key
                  API_KEY_SOURCE = "Hardcoded Script (Not Recommended)"

except Exception as e:
    st.warning(f"Could not read Streamlit secrets: {e}. Will check environment variables / placeholders.")
    # Attempt fallback check even if secrets access failed
    if 'GOOGLE_API_KEY' in os.environ:
        GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
        API_KEY_SOURCE = "Environment Variable (after secrets error)"
    else:
        _placeholder_key = 'YOUR_API_KEY_HERE'
        if _placeholder_key != 'YOUR_API_KEY_HERE':
            GOOGLE_API_KEY = _placeholder_key
            API_KEY_SOURCE = "Hardcoded Script (Not Recommended, after secrets error)"


# --- Helper Functions ---
def log_message(message):
    """Appends a message to the log display."""
    if 'log_messages' not in st.session_state: st.session_state.log_messages = []
    # Prepend timestamp and message
    st.session_state.log_messages.insert(0, f"{time.strftime('%H:%M:%S')}: {message}")
    # Keep log concise (optional)
    max_log_lines = 30
    if len(st.session_state.log_messages) > max_log_lines:
        st.session_state.log_messages = st.session_state.log_messages[:max_log_lines]

# --- Initialize Session State --- (Moved before configure_gemini)
default_values = {
    'log_messages': ["Welcome! Ready for input."], 'processing': False,
    'current_audio_data': None, 'current_text_to_speak': "",
    'last_explanation': "", 'last_uploaded_image': None, 'action_trigger': None,
    'tts_lang_code': 'en', 'translate_lang_code': None,
    'translate_lang_name': 'None (Original Language)', 'gemini_model': None,
    'api_key_configured': False,
    'audio_speed': 1.0, # Default audio speed
}
for key, value in default_values.items():
    if key not in st.session_state: st.session_state[key] = value

# --- Configure Gemini --- (Now checks API key explicitly)
def configure_gemini():
    """Configures the Gemini API if not already done and API key is valid."""
    # Check if already configured successfully in this session
    if st.session_state.get('gemini_model') and st.session_state.get('api_key_configured'):
        return st.session_state.gemini_model

    # Check if API key is present
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == 'YOUR_API_KEY_HERE':
        # Log this only once or if state changes to avoid flooding logs on reruns
        if not st.session_state.get('_api_key_error_logged', False):
             log_message("Configuration check failed: API Key missing or invalid placeholder.")
             st.session_state._api_key_error_logged = True # Mark as logged
        st.session_state.api_key_configured = False
        return None
    else:
        # Reset log flag if key seems present now
        st.session_state._api_key_error_logged = False


    # Attempt configuration
    try:
        log_message(f"Attempting to configure Gemini API (Key source: {API_KEY_SOURCE})...")
        genai.configure(api_key=GOOGLE_API_KEY)

        # Specify the model name - sticking to 1.5-flash for now
        model_name = 'gemini-2.0-flash'
        log_message(f"Initializing Gemini model: {model_name}...")
        model = genai.GenerativeModel(model_name)

        log_message("Gemini configured and model initialized successfully.")
        st.session_state.gemini_model = model # Cache the model
        st.session_state.api_key_configured = True # Mark as configured
        return model
    except Exception as e:
        st.error(f"🚨 Failed to configure/initialize Gemini: {e}")
        st.error("Check your API key validity, Gemini API enablement in Google Cloud, and network connection.")
        log_message(f"Error during Gemini configuration/initialization: {e}")
        st.session_state.api_key_configured = False
        st.session_state.gemini_model = None # Clear cache on failure
        return None


# --- Other Helper Functions (clean_text_for_speech, etc.) ---
def clean_text_for_speech(text):
    """Applies cleaning rules to make text more suitable for TTS."""
    if not isinstance(text, str): # Add check if text is not string
        log_message(f"Warning: Attempting to clean non-string type: {type(text)}")
        text = str(text) # Attempt to convert

    text = text.replace('\n', ' ').replace('  ', ' ')
    text = text.replace('**', '').replace('*', '')
    text = text.replace('`', '').replace('~', '')
    text = text.replace('(', '').replace(')', '')
    text = text.replace('[', '').replace(']', '')
    text = text.replace('{', '').replace('}', '')
    text = text.replace('&', ' and ')
    text = text.replace('%', ' percent ')
    text = text.replace('=', ' equals ')
    text = text.replace('≈', ' approximately ')
    text = text.replace('∝', ' proportional to ')
    text = text.replace('×', ' multiplied by ')
    text = text.replace('÷', ' divided by ')
    text = text.replace('°', ' degrees ')
    text = text.replace('+', ' plus ').replace('-', ' minus ')
    text = ' '.join(text.split()) # Remove extra whitespace
    return text

def generate_speech(text, lang_code):
    """Generates speech audio bytes using gTTS."""
    if not text:
        log_message("Cannot generate speech from empty text.")
        return None
    try:
        log_message(f"Generating speech in language: {lang_code}...")
        tts = gTTS(text=text, lang=lang_code)
        audio_fp = io.BytesIO()
        tts.write_to_fp(audio_fp)
        audio_fp.seek(0)
        log_message("Speech generated successfully.")
        return audio_fp.getvalue()
    except Exception as e:
        log_message(f"Speech generation error: {str(e)}")
        st.error(f"Could not generate speech: {e}")
        return None

def translate_if_needed(text, target_lang_code, target_lang_name):
    """Translates text if a target language is selected."""
    if not target_lang_code or target_lang_code == "en": # Assuming 'en' is the default/no translation
        return text

    if not text:
        log_message("Cannot translate empty text.")
        return ""

    try:
        log_message(f"Translating to {target_lang_name} ({target_lang_code})...")
        translator = GoogleTranslator(source='auto', target=target_lang_code)
        max_chunk_size = 4500 # Keep it safe
        translated_text = ""
        for i in range(0, len(text), max_chunk_size):
            chunk = text[i:i+max_chunk_size]
            if i > 0: time.sleep(0.2) # Small delay between chunks if needed
            translated_text += translator.translate(chunk) + " " # Add space between chunks
        log_message("Translation successful.")
        return translated_text.strip()
    except Exception as e:
        log_message(f"Translation error: {str(e)}")
        st.warning(f"Translation failed: {e}. Using original text.")
        return text # Return original text if translation fails

def get_gemini_response(prompt, image_bytes=None, text_input=None):
    """Gets response from Gemini model."""
    # Try to configure/get the model; it now handles API key checks internally
    model = configure_gemini()
    if not model:
        log_message("get_gemini_response: Cannot proceed, Gemini model not configured.")
        # Return a clear error message that reflects the root cause
        return "Error: Gemini model failed to configure. Check API Key and logs."

    try:
        content = [prompt]
        if image_bytes:
            log_message("Sending image to Gemini...")
            try:
                img = Image.open(io.BytesIO(image_bytes))
                content.append(img)
            except Exception as img_err:
                 log_message(f"Error opening image: {img_err}")
                 st.error(f"Could not process uploaded image file: {img_err}")
                 return "Error: Could not read image data."

        elif text_input:
            log_message("Sending text to Gemini...")
            content.append(text_input) # Append the text directly

        log_message(f"Generating content with model: {model.model_name}...")
        response = model.generate_content(content, request_options={"timeout": 120}) # Add timeout
        log_message("Received response from Gemini.")

        # Safely access the text part & check for blocks
        if not response.parts:
             try:
                 # Log feedback if available
                 log_message(f"Gemini response empty. Prompt feedback: {response.prompt_feedback}")
                 block_reason = response.prompt_feedback.block_reason
                 safety_ratings = response.prompt_feedback.safety_ratings
                 return f"Error: AI response blocked. Reason: {block_reason}. Ratings: {safety_ratings}"
             except Exception:
                 log_message("Gemini response received but has no text parts and no feedback info.")
                 return "Error: AI generated an empty response (possibly due to safety filters or content restrictions)."
        else:
             return response.text.strip()

    except Exception as e:
        log_message(f"Gemini API Error during generation: {str(e)}")
        # Check for specific API errors if possible (e.g., AuthenticationError, PermissionDenied)
        st.error(f"⚠️ Error communicating with Gemini during generation: {e}")
        return f"Error: Could not get response from AI during generation. Details: {e}"


# --- Prompts ---
EXPLAIN_PROMPT_BASE = """
You are a helpful teacher explaining concepts verbally. Your response will be directly converted to text-to-speech.

Analyze the provided content (image or text) and explain it clearly and concisely.

**Crucial Formatting Rules for TTS:**
1.  **Speak Naturally:** Use plain, conversational language ONLY.
2.  **No Markdown/Special Chars:** Absolutely NO markdown (*, **, ~, `, #, etc.).
3.  **Spell Out Symbols:** Write 'plus' not +, 'equals' not =, 'percent' not %, 'degrees' not °, 'multiplied by' not *, 'divided by' not /.
4.  **Numbers:** Write 'one hundred twenty three' or '123', but ensure surrounding text makes it speakable (e.g., '100 percent').
5.  **No Grouping Symbols:** Avoid parentheses (), brackets [], braces {}. Rephrase sentences if necessary.
6.  **Simple Sentences:** Break down complex ideas.
7.  **Abbreviations:** Spell out acronyms or abbreviations the first time (e.g., 'National Aeronautics and Space Administration, NASA').
8.  **Clarity First:** Ensure the final text flows well when read aloud.

Explain the core concepts or information present.
"""

READ_PROMPT_IMAGE = """
Examine this screenshot carefully. Identify and extract ONLY the most prominent or most recent text content.

*   If it's a chat, extract ONLY the latest message or turn.
*   If it's an article or document, extract the main body text you see.
*   If specific text is clearly highlighted or seems to be the focus, extract ONLY that highlighted text.

**CRITICAL:** Return ONLY the extracted text. Do NOT add any commentary, descriptions, introductions, or formatting like quotes or labels. Just the raw text found. If no text is clear, return nothing.
"""

READ_PROMPT_TEXT = """
Read the following text exactly as it is. Apply minimal cleaning ONLY if needed for basic readability (e.g., merging broken lines that are clearly part of the same sentence).

**CRITICAL:** Do NOT add any commentary, descriptions, introductions, or formatting. Just return the text provided.
"""

FOLLOW_UP_PROMPT = """
You are a helpful teacher explaining concepts verbally. Your response will be directly converted to text-to-speech.

The student was previously shown an explanation:
"{previous_explanation}"

The student responded with:
"{user_feedback}"

Address the student's feedback or question and provide a revised or clarified explanation based on their input.

**Crucial Formatting Rules for TTS:**
1.  **Speak Naturally:** Use plain, conversational language ONLY.
2.  **No Markdown/Special Chars:** Absolutely NO markdown (*, **, ~, `, #, etc.).
3.  **Spell Out Symbols:** Write 'plus' not +, 'equals' not =, 'percent' not %, 'degrees' not °, 'multiplied by' not *, 'divided by' not /.
4.  **Numbers:** Write 'one hundred twenty three' or '123', but ensure surrounding text makes it speakable (e.g., '100 percent').
5.  **No Grouping Symbols:** Avoid parentheses (), brackets [], braces {}. Rephrase sentences if necessary.
6.  **Simple Sentences:** Break down complex ideas.
7.  **Abbreviations:** Spell out acronyms or abbreviations the first time (e.g., 'National Aeronautics and Space Administration, NASA').
8.  **Clarity First:** Ensure the final text flows well when read aloud.
"""

# --- Streamlit App Layout ---
st.set_page_config(layout="wide")
st.title("👁️‍🗨️ Screen Teacher AI")
st.write("Hare Krishna! Upload a screenshot or paste text, and I'll explain it or read it aloud.")

# --- Sidebar ---
with st.sidebar:
    st.header("🔑 API Key Status")
    # Display API Key Status prominently
    if not GOOGLE_API_KEY or GOOGLE_API_KEY == 'YOUR_API_KEY_HERE':
         st.error("API Key Not Found or Placeholder!")
         st.caption(f"Configure via: {API_KEY_SOURCE}")
    elif not st.session_state.get('api_key_configured', False):
         # Attempt configuration on first load if key seems present but not configured
         configure_gemini()
         if st.session_state.get('api_key_configured', False):
              st.success(f"API Key Loaded ({API_KEY_SOURCE}) & Verified.")
         else:
              st.error(f"API Key Loaded ({API_KEY_SOURCE}) but FAILED verification.")
              st.caption("Check key validity/permissions.")
    else:
         st.success(f"API Key Loaded ({API_KEY_SOURCE}) & Verified.")


    st.header("⚙️ Settings")

    # --- FIX: Use the full dictionaries here ---
    tts_languages = {
        "English (US)": "en",
        "English (UK)": "en-gb",
        "Spanish": "es",
        "French": "fr",
        "German": "de",
        "Italian": "it",
        "Japanese": "ja",
        "Telugu": "te",
        "Hindi": "hi"
    }
    translation_languages = {
        "None (Original Language)": None,
        "Telugu": "te",
        "Hindi": "hi",
        "English": "en", # Useful if original is different
        "Spanish": "es",
        "French": "fr",
        "German": "de"
    }
    # --- End of FIX ---

    # Language Selection (using the full dictionaries now)
    # Safely get current index or default to 0
    try:
        tts_index = list(tts_languages.values()).index(st.session_state.tts_lang_code)
    except ValueError:
        tts_index = 0 # Default to first language if current code not found

    try:
        trans_index = list(translation_languages.keys()).index(st.session_state.translate_lang_name)
    except ValueError:
        trans_index = 0 # Default to "None" if current name not found


    selected_tts_lang_name = st.selectbox(
        "🗣️ TTS Language",
        options=list(tts_languages.keys()),
        index=tts_index,
        help="The language for the audio voice."
    )
    selected_translate_lang_name = st.selectbox(
        "🌐 Translate Output To",
        options=list(translation_languages.keys()),
        index=trans_index,
        help="Translate the AI's response before converting to speech."
    )

    # Update state if changed (no rerun needed here)
    # Check if the selected key exists before accessing the dictionary
    if selected_tts_lang_name in tts_languages:
        st.session_state.tts_lang_code = tts_languages[selected_tts_lang_name]
    if selected_translate_lang_name in translation_languages:
        st.session_state.translate_lang_code = translation_languages[selected_translate_lang_name]
        st.session_state.translate_lang_name = selected_translate_lang_name

    # --- Add Speed Control Slider ---
    st.header("Playback Speed")
    current_speed = st.session_state.get('audio_speed', 1.0)
    new_speed = st.slider(
        "Audio Speed", min_value=0.5, max_value=2.0,
        value=current_speed, step=0.1,
        help="Adjust the playback speed of the generated audio.",
        key="speed_slider"
    )
    if new_speed != current_speed:
        st.session_state.audio_speed = new_speed
        # Rerun might be needed if JS needs to re-apply immediately after slider change
        # Comment out if it feels too disruptive:
        # st.rerun()


    st.markdown("---")
    st.header("📝 Log")
    log_container = st.container(height=300)
    # Display logs directly from session state
    for msg in st.session_state.log_messages:
        log_container.caption(msg)

# --- Main App Area ---
col1, col2 = st.columns(2)
is_api_ready = st.session_state.get('api_key_configured', False)

with col1: # Input Column
    st.header("📤 Input")
    # Disable input elements if API key is not configured
    if not is_api_ready:
        st.warning("API Key not configured correctly. Please check sidebar status and logs. Input disabled.")

    # Image Input
    st.subheader("Screenshot Analysis")
    uploaded_file = st.file_uploader(
        "Upload a Screenshot (PNG, JPG)", type=["png", "jpg", "jpeg"],
        key="file_uploader", disabled=st.session_state.processing or not is_api_ready,
        on_change=lambda: setattr(st.session_state, 'last_uploaded_image', st.session_state.file_uploader.getvalue() if st.session_state.file_uploader else None)
    )
    # Update last_uploaded_image immediately if file is uploaded via callback
    # Display the uploaded image if available
    if st.session_state.last_uploaded_image:
        st.image(st.session_state.last_uploaded_image, caption="Uploaded Screenshot", use_column_width=True)


    img_button_col1, img_button_col2 = st.columns(2)
    if img_button_col1.button("🧠 Explain Screenshot", key="explain_img", disabled=st.session_state.processing or not st.session_state.last_uploaded_image or not is_api_ready):
        if st.session_state.last_uploaded_image:
            st.session_state.processing = True
            st.session_state.action_trigger = "explain_image"
            st.session_state.current_audio_data = None # Clear previous results
            st.session_state.current_text_to_speak = ""
            st.rerun()
        else: st.warning("Please upload an image first.")

    if img_button_col2.button("📖 Read Screenshot Text", key="read_img", disabled=st.session_state.processing or not st.session_state.last_uploaded_image or not is_api_ready):
        if st.session_state.last_uploaded_image:
            st.session_state.processing = True
            st.session_state.action_trigger = "read_image"
            st.session_state.current_audio_data = None
            st.session_state.current_text_to_speak = ""
            st.rerun()
        else: st.warning("Please upload an image first.")


    # Text Input
    st.subheader("Pasted Text Analysis")
    pasted_text = st.text_area(
        "Paste text here:", height=150, key="pasted_text_area",
        disabled=st.session_state.processing or not is_api_ready
    )
    text_button_col1, text_button_col2 = st.columns(2)
    if text_button_col1.button("🧠 Explain Pasted Text", key="explain_txt", disabled=st.session_state.processing or not pasted_text or not is_api_ready):
        st.session_state.processing = True
        st.session_state.action_trigger = "explain_text"
        st.session_state.current_audio_data = None
        st.session_state.current_text_to_speak = ""
        st.rerun()

    if text_button_col2.button("📖 Read Pasted Text", key="read_txt", disabled=st.session_state.processing or not pasted_text or not is_api_ready):
        st.session_state.processing = True
        st.session_state.action_trigger = "read_text"
        st.session_state.current_audio_data = None
        st.session_state.current_text_to_speak = ""
        st.rerun()

with col2: # Output Column
    st.header("🔊 Output & Interaction")

    # Text Display Area
    st.subheader("Text Content")
    st.text_area(
        label="Text Content (Read Only)", value=st.session_state.current_text_to_speak,
        height=200, key="spoken_text_display", disabled=True
    )

    # Audio Player Area
    st.subheader("Audio Output")
    audio_placeholder = st.empty() # Create a placeholder for the audio + JS script

    if st.session_state.current_audio_data:
        # Display audio player IN the placeholder
        audio_placeholder.audio(st.session_state.current_audio_data, format="audio/mp3")

        # --- JavaScript Injection for Speed Control ---
        speed = st.session_state.get('audio_speed', 1.0)
        js_code = f"""
            <script>
                var speed = {speed}; // Get speed from Python
                var audioElements = document.querySelectorAll('audio');
                if (audioElements.length > 0) {{
                    // Target the last audio element assuming it's the one just added
                    var audioElement = audioElements[audioElements.length - 1];
                    // Set rate only if it's different to avoid unnecessary changes/potential glitches
                    if (audioElement.playbackRate !== speed) {{
                         audioElement.playbackRate = speed;
                         // console.log("Audio playbackRate set to:", speed); // Debug
                    }}
                }}
                // Set interval to periodically check and set speed for dynamic elements
                // This is a fallback/robustness measure, might not be strictly needed
                // Clears previous interval if exists
                // if (window.audioSpeedInterval) {{ clearInterval(window.audioSpeedInterval); }}
                // window.audioSpeedInterval = setInterval(function() {{
                //     var audioElements = document.querySelectorAll('audio');
                //     if (audioElements.length > 0) {{
                //         var audioElement = audioElements[audioElements.length - 1];
                //         if (audioElement.playbackRate !== speed) {{
                //             audioElement.playbackRate = speed;
                //         }}
                //     }}
                // }}, 500); // Check every 500ms
            </script>
            """
        # Inject the JavaScript using st.components.v1.html right after the audio
        components.html(js_code, height=0) # Key might cause issues if speed changes rapidly

    elif st.session_state.processing:
         audio_placeholder.caption("Generating audio...") # Show message in placeholder
    else:
        audio_placeholder.caption("Audio will appear here once generated.") # Show message in placeholder

    st.markdown("---")

    # Follow-up Interaction
    st.subheader("💬 Follow-up Question")
    user_feedback = st.text_input(
        "Ask a question about the last explanation:", key="feedback_input",
        disabled=st.session_state.processing or not st.session_state.last_explanation or not is_api_ready
    )
    if st.button("✉️ Send Response", key="send_follow_up", disabled=st.session_state.processing or not user_feedback or not st.session_state.last_explanation or not is_api_ready):
        st.session_state.processing = True
        st.session_state.action_trigger = "follow_up"
        st.session_state.current_audio_data = None
        st.session_state.current_text_to_speak = ""
        st.rerun()


# --- Processing Logic ---
if st.session_state.processing:
    action = st.session_state.get("action_trigger")
    is_api_ready = st.session_state.get('api_key_configured', False) # Final check before API call

    if action and is_api_ready: # Only proceed if action is set AND API is ready
        log_message(f"Starting processing for action: {action}")
        with st.spinner(f"🧠 Processing: {action.replace('_', ' ')}..."):
            try:
                final_text_to_speak = ""
                gemini_result = "" # Store raw result

                # --- Action Execution Logic ---
                if action == "explain_image":
                    log_message("Processing screenshot explanation...")
                    if not st.session_state.last_uploaded_image: raise ValueError("No image data found for explanation.")
                    prompt = EXPLAIN_PROMPT_BASE
                    gemini_result = get_gemini_response(prompt, image_bytes=st.session_state.last_uploaded_image)

                elif action == "read_image":
                    log_message("Processing screenshot reading...")
                    if not st.session_state.last_uploaded_image: raise ValueError("No image data found for reading.")
                    prompt = READ_PROMPT_IMAGE
                    gemini_result = get_gemini_response(prompt, image_bytes=st.session_state.last_uploaded_image)

                elif action == "explain_text":
                    log_message("Processing pasted text explanation...")
                    current_pasted_text = st.session_state.get("pasted_text_area", "")
                    if not current_pasted_text: raise ValueError("No pasted text found for explanation.")
                    prompt = EXPLAIN_PROMPT_BASE
                    gemini_result = get_gemini_response(prompt, text_input=current_pasted_text)

                elif action == "read_text":
                    log_message("Processing pasted text reading...")
                    current_pasted_text = st.session_state.get("pasted_text_area", "")
                    if not current_pasted_text: raise ValueError("No pasted text found for reading.")
                    # Directly use the pasted text, maybe minimal cleaning
                    cleaned_text = ' '.join(current_pasted_text.split())
                    st.session_state.last_explanation = "" # Reading doesn't set context
                    # Directly translate/speak without Gemini call for "read"
                    final_text_to_speak = translate_if_needed(cleaned_text, st.session_state.translate_lang_code, st.session_state.translate_lang_name)
                    gemini_result = None # Mark that Gemini wasn't called for this path

                elif action == "follow_up":
                    log_message("Processing follow-up response...")
                    current_feedback = st.session_state.get("feedback_input", "")
                    if not current_feedback: raise ValueError("No follow-up text provided.")
                    if not st.session_state.last_explanation: raise ValueError("No previous explanation context found for follow-up.")
                    prompt = FOLLOW_UP_PROMPT.format(
                        previous_explanation=st.session_state.last_explanation,
                        user_feedback=current_feedback
                    )
                    gemini_result = get_gemini_response(prompt)

                # --- Process Gemini Result (if called) ---
                if gemini_result is not None: # Check if Gemini was actually called
                    if "Error:" not in gemini_result:
                         # Actions that need cleaning and translation after Gemini
                         if action in ["explain_image", "explain_text", "follow_up"]:
                             cleaned_explanation = clean_text_for_speech(gemini_result)
                             st.session_state.last_explanation = cleaned_explanation
                             final_text_to_speak = translate_if_needed(cleaned_explanation, st.session_state.translate_lang_code, st.session_state.translate_lang_name)
                         # Action that needs less cleaning after Gemini
                         elif action == "read_image":
                             cleaned_text = ' '.join(gemini_result.split())
                             st.session_state.last_explanation = "" # Reading doesn't set context
                             final_text_to_speak = translate_if_needed(cleaned_text, st.session_state.translate_lang_code, st.session_state.translate_lang_name)
                         # else condition should not be met if gemini_result is not None
                    else:
                        # Pass Gemini error through
                        final_text_to_speak = gemini_result
                        log_message(f"Gemini returned an error: {final_text_to_speak}")

                # --- Generate Audio ---
                if final_text_to_speak and "Error:" not in final_text_to_speak :
                    st.session_state.current_text_to_speak = final_text_to_speak
                    st.session_state.current_audio_data = generate_speech(
                        final_text_to_speak, st.session_state.tts_lang_code
                    )
                    if not st.session_state.current_audio_data:
                         st.session_state.current_text_to_speak += "\n\n(Error generating audio for this text)"
                         log_message("Audio generation failed.")
                elif final_text_to_speak: # Handles both Gemini errors and other potential errors
                    log_message(f"Skipping audio generation due to error/empty text: {final_text_to_speak[:100]}...") # Log snippet
                    st.session_state.current_text_to_speak = final_text_to_speak
                    st.session_state.current_audio_data = None
                else:
                    log_message("No text generated or extracted to speak.")
                    st.session_state.current_text_to_speak = "(No content was generated or extracted)"
                    st.session_state.current_audio_data = None

            except Exception as e:
                log_message(f"Error during processing action '{action}': {str(e)}")
                log_message(f"Traceback: {traceback.format_exc()}")
                st.error(f"An error occurred during '{action}': {e}")
                st.session_state.current_text_to_speak = f"Error during {action}: {e}"
                st.session_state.current_audio_data = None
            finally:
                log_message(f"Finished processing action: {action}")
                st.session_state.processing = False
                st.session_state.action_trigger = None
                st.rerun() # Rerun one last time to update UI (enable buttons, show results, apply JS)

    elif action and not is_api_ready:
         log_message(f"Processing blocked for action '{action}': API not configured.")
         st.error("Cannot process request. API Key is not configured correctly.")
         st.session_state.processing = False # Ensure processing stops
         st.session_state.action_trigger = None
         st.rerun() # Update UI to show error and re-enable inputs if needed

    elif not action and st.session_state.processing:
         # Safety net: Processing was true, but action was lost
         log_message("Warning: Processing state was True, but no action_trigger found. Resetting.")
         st.session_state.processing = False
         st.session_state.action_trigger = None
         st.rerun()


# --- Footer/Instructions ---
st.markdown("---")
st.markdown("""
**How to Use:**
*   **API Key:** Ensure your Google API Key with Gemini API enabled is correctly set (using Streamlit Secrets is recommended). Check status in the sidebar.
*   **Screenshot/Text:** Upload an image or paste text using the input fields in the left column.
*   **Actions:** Click 'Explain' or 'Read' below the corresponding input.
*   **Follow-up:** Use the input box in the right column to ask questions about the *last explanation*.
*   **Settings:** Use the sidebar to change voice/translation language and playback speed.
*   **Speed Control:** Adjust the 'Audio Speed' slider in the sidebar *before or during* playback.
""")