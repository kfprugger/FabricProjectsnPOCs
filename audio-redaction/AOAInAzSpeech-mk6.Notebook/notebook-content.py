# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "f2cec01e-3596-4cc0-a50c-94769c969b33",
# META       "default_lakehouse_name": "bronze_aoai_lh",
# META       "default_lakehouse_workspace_id": "4414d1c5-d566-4308-b8d1-a275b09a7cf2",
# META       "known_lakehouses": [
# META         {
# META           "id": "f2cec01e-3596-4cc0-a50c-94769c969b33"
# META         }
# META       ]
# META     },
# META     "environment": {
# META       "environmentId": "564937f4-dbbc-80fe-42a8-004c8afb8e98",
# META       "workspaceId": "00000000-0000-0000-0000-000000000000"
# META     }
# META   }
# META }

# MARKDOWN ********************

# ***
# 
# ### **Hybrid AI Approach for Call Center Transcription and Analysis**
# 
# This notebook demonstrates a robust, hybrid AI solution for processing call center audio files. It leverages two distinct Azure AI services to achieve a comprehensive and accurate analysis that is both cost-effective and deterministic.
# 
# The process is as follows:
# 1.  **Transcription and Diarization (Azure AI Speech):** The notebook first uses the Azure AI Speech service for transcription. This service is specifically chosen for its robust speaker diarization feature, which identifies and separates different speakers in the conversation (e.g., "Speaker 1," "Speaker 2"). This is a critical feature that Azure OpenAI's audio models do not currently support.
# 2.  **Enrichment and Analysis (Azure OpenAI):** Once the raw transcript with speaker IDs is generated, the text is sent to a GPT model via the Azure OpenAI service. This service was selected because its powerful language models are superior for complex analytical tasks compared to the standard Azure AI Language service. The GPT model performs PII (Personally Identifiable Information) detection, sentiment analysis, key phrase extraction, and conversation classification.
# 
# This two-step, hybrid approach ensures high-quality speaker separation from the best-in-class service for that task, while using the superior analytical power of a large language model for enrichment, resulting in a more accurate and cost-effective end-to-end process.
# 
# ---
# ### **TODO: Performance Enhancements**
# The current implementation processes audio files one by one, which can be slow for large volumes. The initial transcription step is the primary bottleneck. Future development should focus on parallelizing this process to improve throughput. Two potential approaches are:
# 
# 1.  **Spark UDF with Pandas:** Refactor the transcription logic into a Spark User-Defined Function (UDF), possibly a Pandas UDF (Series to Series), to distribute the processing of audio files across all worker nodes in the Spark cluster.
# 2.  **Azure Batch Transcription API:** Replace the real-time Speech SDK with the Azure Batch Transcription API. This service is specifically designed for transcribing large quantities of audio files asynchronously and is the more idiomatic and scalable solution for bulk processing.
# 
# ---
# > **Cell Purpose:** This cell ensures the necessary Azure SDKs are installed for interacting with both Azure AI Speech (for transcription with speaker diarization) and Azure OpenAI (for analysis), as well as Azure Key Vault for securely accessing credentials.
# 
# ### **Cell 1: Install Required Libraries**


# CELL ********************

# %pip install azure-cognitiveservices-speech openai azure-keyvault-secrets azure-identity

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# > **Cell Purpose:** This cell imports all the required Python modules for file system interaction, data manipulation with Spark, and interfacing with the Azure AI Speech and Azure OpenAI SDKs. It also initializes the Spark session.
# 
# ### **Cell 2: Imports and Spark Initialization**

# CELL ********************

import os
import json
import time
import shutil
import tempfile
import uuid
import wave
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType,
    DoubleType, LongType, FloatType
)
from pyspark.sql.functions import col

# Azure SDKs for a HYBRID approach
import azure.cognitiveservices.speech as speechsdk
from openai import AzureOpenAI

# Fabric-specific utilities
from notebookutils import mssparkutils as notebookutils

# Initialize Spark Session
spark = SparkSession.builder.appName("HybridCallCenterAnalysis").getOrCreate()

def format_duration_hms(seconds):
    """Converts a duration in seconds to HH:MM:SS format."""
    if seconds is None:
        return "00:00:00"
    return time.strftime('%H:%M:%S', time.gmtime(seconds))

print("Spark session initialized and libraries imported. 🚀")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# > **Cell Purpose:** This cell is a critical prerequisite for corporate or secured environments. It configures the necessary SSL environment variables to point to the system's trusted CA certificate bundle. This prevents SSL/TLS handshake failures when the Python SDKs attempt to connect to Azure services through a proxy or firewall.
# 
# ### **Cell 3: Critical Prerequisite: SSL Certificate Configuration**

# CELL ********************

import os

# Define the standard path for CA certificates in Debian-based Linux environments, which is common for Spark runtimes.
ca_cert_path = "/etc/ssl/certs/ca-certificates.crt"

print(f"Attempting to configure SSL using the system's default certificate bundle.")
print(f"Checking for bundle at: {ca_cert_path}")

# Check if the standard certificate bundle exists at the expected path.
if os.path.exists(ca_cert_path):
    print("System CA certificate bundle found. Setting SSL environment variables to point to it.")

    # Set the environment variables for both the Speech SDK (SSL_CERT_FILE)
    # and other libraries like OpenAI (REQUESTS_CA_BUNDLE).
    os.environ["SSL_CERT_FILE"] = ca_cert_path
    os.environ["REQUESTS_CA_BUNDLE"] = ca_cert_path

    print(f"✅ SSL_CERT_FILE is now set to: {os.environ.get('SSL_CERT_FILE')}")
    print(f"✅ REQUESTS_CA_BUNDLE is now set to: {os.environ.get('REQUESTS_CA_BUNDLE')}")
else:
    print("WARNING: Standard system CA certificate bundle was not found at the expected path.")
    print("The connection may still fail. This could indicate an unusual runtime configuration in the environment.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# > **Cell Purpose:** This cell centralizes all configuration for the notebook. It securely retrieves credentials from Azure Key Vault using Fabric's `mssparkutils`, defines the input and output paths within the Lakehouse, and specifies the names for the target Delta tables where the results will be stored.
# 
# ### **Cell 4: Configuration**

# CELL ********************

# --- Azure Key Vault Configuration ---
key_vault_name = "akv-rjb-wu3-01"
key_vault_uri = f"https://{key_vault_name}.vault.azure.net"


# --- Retrieve Secrets using Fabric's Native mssparkutils ---
# This is the most direct and recommended method for Fabric notebooks.
try:
    print(f"Retrieving secrets from Azure Key Vault '{key_vault_name}' using mssparkutils...")

    SPEECH_KEY = notebookutils.credentials.getSecret(key_vault_uri, "SPEECH-KEY")
    SPEECH_REGION = notebookutils.credentials.getSecret(key_vault_uri, "SPEECH-REGION")
    AZURE_OPENAI_API_KEY = notebookutils.credentials.getSecret(key_vault_uri, "AZURE-OPENAI-API-KEY")
    AZURE_OPENAI_ENDPOINT = notebookutils.credentials.getSecret(key_vault_uri, "AZURE-OPENAI-ENDPOINT")
    AZURE_OPENAI_GPT_DEPLOYMENT = notebookutils.credentials.getSecret(key_vault_uri, "AZURE-OPENAI-GPT-DEPLOYMENT")

    print("✅ Secrets retrieved successfully.")

except Exception as e:
    print(f"❌ Error retrieving secrets with notebookutils: {e}")
    print("Please ensure the Key Vault name is correct and that both your user and the Fabric Workspace have the 'Key Vault Secrets User' role on the Key Vault.")
    # Stop execution if secrets can't be retrieved
    raise

# --- Fabric Lakehouse Path Configurations ---
LAKEHOUSE_AUDIO_INPUT_DIR_RELATIVE = "Files/audio-files"
LAKEHOUSE_TRANSCRIPTS_OUTPUT_DIR_RELATIVE = "Files/transcripts"
LAKEHOUSE_PROCESSED_AUDIO_DIR_RELATIVE = "Files/processed-audio"
LAKEHOUSE_FAILED_AUDIO_DIR_RELATIVE = "Files/failed"
LAKEHOUSE_SDK_LOGS_DIR_RELATIVE = "Files/sdk-logs"

# --- Fabric Lakehouse Table Configurations ---
LAKEHOUSE_NAME_FOR_TABLES = "bronze_aoai_lh"
MAIN_TRANSCRIPTS_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.transcripts"
TRANSCRIPTION_LOG_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.transcribe_log"
PII_ENTITIES_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.pii_entities"
TRANSCRIPT_PHRASES_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.transcript_phrases"
SENTENCE_SENTIMENTS_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.sentence_sentiments"
KEY_PHRASES_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.key_phrases"

# --- Local Paths for Notebook Processing (via Lakehouse mount) ---
LOCAL_LAKEHOUSE_ROOT = "/lakehouse/default/"
LOCAL_AUDIO_INPUT_PATH = os.path.join(LOCAL_LAKEHOUSE_ROOT, LAKEHOUSE_AUDIO_INPUT_DIR_RELATIVE)
LOCAL_TRANSCRIPTS_OUTPUT_PATH = os.path.join(LOCAL_LAKEHOUSE_ROOT, LAKEHOUSE_TRANSCRIPTS_OUTPUT_DIR_RELATIVE)
LOCAL_PROCESSED_AUDIO_PATH = os.path.join(LOCAL_LAKEHOUSE_ROOT, LAKEHOUSE_PROCESSED_AUDIO_DIR_RELATIVE)
LOCAL_FAILED_AUDIO_PATH = os.path.join(LOCAL_LAKEHOUSE_ROOT, LAKEHOUSE_FAILED_AUDIO_DIR_RELATIVE)
LOCAL_SDK_LOGS_PATH = os.path.join(LOCAL_LAKEHOUSE_ROOT, LAKEHOUSE_SDK_LOGS_DIR_RELATIVE)

# --- Initialize Azure OpenAI Client for Analysis ---
openai_client = None
try:
    openai_client = AzureOpenAI(
        api_key=AZURE_OPENAI_API_KEY,
        api_version="2024-02-01",
        azure_endpoint=AZURE_OPENAI_ENDPOINT
    )
    print("✅ Azure OpenAI client initialized successfully using secrets from Key Vault.")
except Exception as ex:
    print(f"❌ Error initializing Azure OpenAI client: {ex}")

# Ensure output directories exist
os.makedirs(LOCAL_TRANSCRIPTS_OUTPUT_PATH, exist_ok=True)
os.makedirs(LOCAL_PROCESSED_AUDIO_PATH, exist_ok=True)
os.makedirs(LOCAL_FAILED_AUDIO_PATH, exist_ok=True)
os.makedirs(LOCAL_SDK_LOGS_PATH, exist_ok=True)
print("Directory check complete.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# > **Cell Purpose:** This cell defines the core helper functions for the pipeline.
# > * `WavFileReaderCallback`: A class to stream audio data efficiently to the Speech SDK.
# > * `transcribe_audio_with_diarization`: The main function that calls the Azure AI Speech service. It's configured to enable speaker diarization and to save detailed SDK logs for debugging connection issues.
# > * `analyze_and_redact_with_gpt`: The function that calls the Azure OpenAI service with a detailed system prompt to perform PII redaction, sentiment analysis, key phrase extraction, and more.
# 
# ### **Cell 5: Helper Functions with Verbose Logging**

# CELL ********************

# Helper class to stream a WAV file for the Speech SDK
class WavFileReaderCallback(speechsdk.audio.PullAudioInputStreamCallback):
    def __init__(self, filename: str):
        super().__init__()
        self._file_h = wave.open(filename, 'rb')
        self.is_closed = False
        if self._file_h.getnchannels() != 1 or self._file_h.getsampwidth() != 2 or self._file_h.getframerate() not in [8000, 16000]:
             print(f"[WARN] Audio file {filename} may not be in the recommended format (16-bit, 16kHz/8kHz, Mono).")

    def read(self, audio_buffer: memoryview) -> int:
        if self.is_closed: return 0
        try:
            size = audio_buffer.nbytes
            frames = self._file_h.readframes(size // 2)
            audio_buffer[:len(frames)] = frames
            if len(frames) < size: self.close()
            return len(frames)
        except Exception as e:
            print(f"Error reading audio stream: {e}")
            self.close()
            return 0

    def close(self):
        if not self.is_closed:
            self._file_h.close()
            self.is_closed = True

def transcribe_audio_with_diarization(speech_key, speech_region, local_audio_file_path):
    """
    Transcribes a mono audio file using ConversationTranscriber to get speaker IDs.
    """
    audio_filename = os.path.basename(local_audio_file_path)
    print(f"  [SPEECH SDK] Starting DIARIZED transcription for: {audio_filename}")

    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_recognition_language = "en-US"

    # --- Enable verbose SDK logging to a file ---
    log_file_path = os.path.join(LOCAL_SDK_LOGS_PATH, f"speech-sdk-{os.path.splitext(audio_filename)[0]}.log")
    speech_config.set_property(speechsdk.PropertyId.Speech_LogFilename, log_file_path)
    print(f"  [DEBUG] Verbose SDK logging enabled. Log file: {log_file_path}")

    # --- Explicitly enable diarization for the ConversationTranscriber ---
    speech_config.set_service_property(
        name='speech.diarization.enabled',
        value='true',
        channel=speechsdk.ServicePropertyChannel.UriQueryParameter
    )

    speech_config.set_property(speechsdk.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs, "30000")

    if not os.path.exists(local_audio_file_path) or os.path.getsize(local_audio_file_path) == 0:
        print(f"  [ERROR] Audio file {audio_filename} is missing or empty.")
        return {"ProcessingStatus": "ErrorFileNotFoundOrEmpty", "RecognizedPhrases": [], "CombinedDisplayText": "", "TotalDurationInSeconds": 0.0}

    try:
        callback = WavFileReaderCallback(local_audio_file_path)
        stream = speechsdk.audio.PullAudioInputStream(callback)
        audio_config = speechsdk.audio.AudioConfig(stream=stream)
    except Exception as e:
        print(f"  [ERROR] Failed to create audio stream from {audio_filename}. Error: {e}")
        return {"ProcessingStatus": "ErrorInvalidAudioFile", "RecognizedPhrases": [], "CombinedDisplayText": "", "TotalDurationInSeconds": 0.0}

    conversation_transcriber = speechsdk.transcription.ConversationTranscriber(speech_config=speech_config, audio_config=audio_config)

    done = False
    all_results = []
    cancellation_details_output = {}

    def on_transcribed(evt: speechsdk.SpeechRecognitionEventArgs):
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            all_results.append(evt.result)
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            pass

    def on_canceled(evt: speechsdk.SpeechRecognitionCanceledEventArgs):
        nonlocal done, cancellation_details_output
        cancellation_details_output = {"reason": str(evt.reason)}
        if evt.reason == speechsdk.CancellationReason.Error:
            cancellation_details_output["error_code"] = str(evt.error_code)
            cancellation_details_output["error_details"] = evt.error_details
        done = True

    def on_session_stopped(evt: speechsdk.SessionEventArgs):
        nonlocal done
        conversation_transcriber.stop_transcribing_async()
        done = True

    conversation_transcriber.transcribed.connect(on_transcribed)
    conversation_transcriber.session_stopped.connect(on_session_stopped)
    conversation_transcriber.canceled.connect(on_canceled)

    conversation_transcriber.start_transcribing_async()
    while not done: time.sleep(0.15)
    print(f"  [SPEECH SDK] Recognition finished for {audio_filename}. Processing {len(all_results)} utterances.")

    recognized_phrases = []
    combined_text_parts = []
    total_duration_ticks = 0
    if all_results:
        for result in all_results:
            json_output = json.loads(result.json)
            display_text = json_output.get("DisplayText")
            combined_text_parts.append(display_text)
            duration_ticks = json_output.get("Duration", 0)
            total_duration_ticks += duration_ticks
            phrase = {"SpeakerId": result.speaker_id, "Text": display_text, "OffsetInTicks": json_output.get("Offset", 0), "DurationInTicks": duration_ticks, "Confidence": json_output.get("NBest", [{}])[0].get("Confidence", 0.0)}
            recognized_phrases.append(phrase)

    status = "Success" if recognized_phrases else "NoMatchOrEmpty"
    return {"ProcessingStatus": status, "RecognizedPhrases": recognized_phrases, "CombinedDisplayText": " ".join(combined_text_parts).strip(), "TotalDurationInSeconds": total_duration_ticks / 10_000_000.0, "CancellationDetails": cancellation_details_output if cancellation_details_output else None}


def analyze_and_redact_with_gpt(client: AzureOpenAI, deployment: str, transcript_text: str):
    """
    Analyzes a transcript using a GPT model and returns the analysis,
    redacted text, and the total tokens used in the API call.
    """
    if not transcript_text or not transcript_text.strip():
        return {"analysis": {"PiiRedactedText": "", "OverallSentiment": "N/A", "KeyPhrases": [], "PiiEntities": [], "SentencesSentiment": []}, "tokens": 0}

    system_prompt = """
    You are an AI assistant specialized in analyzing call center transcripts. Your task is to process the user-provided transcript and return a single, well-formed JSON object.

    The JSON object must contain the following keys:
    1. "piiRedactedText": A string containing the full transcript with all detected Personally Identifiable Information (PII) like names, addresses, phone numbers, emails, and any financial or health-related information replaced with a placeholder (e.g., "[REDACTED_PERSON]", "[REDACTED_PHONE]").
    2. "overallSentiment": A string representing the dominant sentiment of the entire call. Values can be "Positive", "Negative", "Neutral", or "Mixed".
    3. "keyPhrases": A JSON array of strings, where each string is a key topic or phrase from the conversation.
    4. "piiEntities": A JSON array of objects. Each object represents a detected PII entity and must have the keys "text" (the original PII text), "category" (e.g., "Person", "PhoneNumber", "Address", "Email"), and "confidenceScore" (a float between 0.0 and 1.0).
    5. "sentenceSentiments": A JSON array of objects. Each object represents a sentence from the transcript and must have the keys "sentenceText", "sentiment" ("Positive", "Negative", "Neutral"), and "scores" (an object with "positive", "neutral", and "negative" float values).
    6. "transcriptMainTopic": A string that succinctly summarizes the main topic or reason for the call in a few words (e.g., "Medication Refill Request", "Appointment Scheduling Inquiry", "Insurance Coverage Question").
    7. "conversationType": A string that classifies the caller type. It must be one of these three exact values: "Patient", "Health Care Professional", or "Caregiver". Analyze the context to determine the most likely caller type.

    IMPORTANT: Pay special attention to PII that is spelled out loud (e.g., "My name is J-O-H-N S-M-I-T-H" or "J-A-M-E-S S-U-L-L-I-V-A-N"). You must identify the spelled-out text as PII and redact it correctly in the "piiRedactedText" field.

    Analyze the following transcript carefully and provide the complete JSON output as requested.
    """

    print("  [GPT] Starting analysis for PII, sentiment, and key phrases.")
    try:
        response = client.chat.completions.create(
            model=deployment,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": transcript_text}
            ],
            temperature=0.1,
        )

        analysis_json = json.loads(response.choices[0].message.content)
        total_tokens = response.usage.total_tokens if response.usage else 0
        print(f"  [SUCCESS] GPT analysis complete. Tokens used: {total_tokens}")

        return {"analysis": analysis_json, "tokens": total_tokens}

    except Exception as e:
        print(f"  [ERROR] An error occurred during GPT analysis: {e}")
        return {"analysis": {"PiiRedactedText": "Error during analysis", "OverallSentiment": "Error", "KeyPhrases": [], "PiiEntities": [], "SentencesSentiment": [], "ErrorDetails": str(e)}, "tokens": 0}

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# > **Cell Purpose:** This cell is the main orchestrator for the entire pipeline. It lists the audio files in the input directory, checks against a log table to skip any files that have already been processed successfully, and then iterates through each new file, calling the transcription and analysis functions. Finally, it moves the processed files to either a "processed" or "failed" directory.
# 
# ### **Cell 6: Main Processing Loop**

# CELL ********************

# Create lists to hold the rows for each of our new tables
all_log_rows = []
all_transcripts_rows = []
all_pii_entities_rows = []
all_phrases_rows = []
all_sentence_sentiments_rows = []
all_key_phrases_rows = []

# Prevent duplicate processing by checking the log table first
processed_files = set()
try:
    if spark.catalog.tableExists(TRANSCRIPTION_LOG_TABLE):
        print(f"Checking for previously processed files in {TRANSCRIPTION_LOG_TABLE}...")
        processed_df = spark.read.table(TRANSCRIPTION_LOG_TABLE).where("ProcessingStatus = 'Success'")
        processed_files = set([row.AudioFileName for row in processed_df.select("AudioFileName").collect()])
        if processed_files:
            print(f"Found {len(processed_files)} previously successful files to skip.")
except Exception as e:
    print(f"⚠️ Warning: Could not check log table for processed files. Error: {e}")

all_files_in_dir = [f for f in os.listdir(LOCAL_AUDIO_INPUT_PATH) if f.lower().endswith(('.wav')) and os.path.isfile(os.path.join(LOCAL_AUDIO_INPUT_PATH, f))]
audio_files_to_process = [f for f in all_files_in_dir if f not in processed_files]
print(f"Found {len(all_files_in_dir)} total files. After filtering, {len(audio_files_to_process)} new files will be processed.")

with tempfile.TemporaryDirectory() as temp_dir:
    for audio_file in audio_files_to_process:
        source_file_path = os.path.join(LOCAL_AUDIO_INPUT_PATH, audio_file)
        # We copy to a temp location to avoid potential locking issues on the Lakehouse mount
        temp_audio_file = os.path.join(temp_dir, audio_file)
        shutil.copy2(source_file_path, temp_audio_file)

        print(f"\n🔄 Processing: {audio_file}...")
        transcription_id = str(uuid.uuid4())
        is_successful = False

        # Initialize timing variables
        transcription_time_seconds = 0.0
        analysis_time_seconds = 0.0

        try:
            # Time the transcription call
            start_transcribe_time = time.time()
            speech_results = transcribe_audio_with_diarization(SPEECH_KEY, SPEECH_REGION, temp_audio_file)
            transcription_time_seconds = time.time() - start_transcribe_time

            status = speech_results.get("ProcessingStatus", "UnknownError")
            is_successful = (status == "Success")
            status_details = json.dumps(speech_results.get("CancellationDetails")) if speech_results.get("CancellationDetails") else None
            duration_seconds = speech_results.get("TotalDurationInSeconds", 0.0)
            duration_hms = format_duration_hms(duration_seconds)

            # If Successful, Perform Enrichment
            if is_successful:
                print("  [SUCCESS] Transcription successful. Proceeding with OpenAI enrichment.")
                language_results = {}
                analysis_tokens = 0
                if openai_client:
                    # Time the analysis call
                    start_analysis_time = time.time()
                    language_response = analyze_and_redact_with_gpt(openai_client, AZURE_OPENAI_GPT_DEPLOYMENT, speech_results.get("CombinedDisplayText", ""))
                    analysis_time_seconds = time.time() - start_analysis_time

                    language_results = language_response.get("analysis", {})
                    analysis_tokens = language_response.get("tokens", 0)
                else:
                    print("  [WARN] OpenAI client is not configured. Skipping analysis.")

                # Populate data for Lakehouse tables
                all_transcripts_rows.append({
                    "TranscriptionId": transcription_id, "AudioFileName": audio_file, "ProcessingTimestamp": datetime.utcnow(),
                    "ProcessingStatus": status, "CallDurationSeconds": duration_seconds, "CallDurationHms": duration_hms,
                    "OverallSentiment": language_results.get("overallSentiment"),
                    "PiiRedactedText": language_results.get("piiRedactedText"),
                    "TranscriptMainTopic": language_results.get("transcriptMainTopic", "N/A"),
                    "ConversationType": language_results.get("conversationType", "Unknown"),
                    "TotalTokens": analysis_tokens,
                    "LakehouseTranscriptPath": os.path.join(LAKEHOUSE_TRANSCRIPTS_OUTPUT_DIR_RELATIVE, f"{os.path.splitext(audio_file)[0]}_enriched_transcript.json")
                })

                for entity in language_results.get("piiEntities", []):
                    all_pii_entities_rows.append({ "PiiEntityId": str(uuid.uuid4()), "TranscriptionId": transcription_id, "PiiText": entity.get("text"), "PiiCategory": entity.get("category"), "PiiSubcategory": None, "ConfidenceScore": entity.get("confidenceScore") })

                for phrase in speech_results.get("RecognizedPhrases", []):
                    all_phrases_rows.append({ "PhraseId": str(uuid.uuid4()), "TranscriptionId": transcription_id, "SpeakerId": phrase.get("SpeakerId"), "PhraseText": phrase.get("Text"), "OffsetInSeconds": phrase.get("OffsetInTicks", 0) / 10_000_000.0, "DurationInSeconds": phrase.get("DurationInTicks", 0) / 10_000_000.0, "Confidence": phrase.get("Confidence") })

                for sentence in language_results.get("sentenceSentiments", []):
                    all_sentence_sentiments_rows.append({ "SentenceId": str(uuid.uuid4()), "TranscriptionId": transcription_id, "SentenceText": sentence.get("sentenceText"), "Sentiment": sentence.get("sentiment"), "PositiveScore": sentence.get("scores", {}).get("positive"), "NeutralScore": sentence.get("scores", {}).get("neutral"), "NegativeScore": sentence.get("scores", {}).get("negative") })

                for key_phrase in language_results.get("keyPhrases", []):
                    all_key_phrases_rows.append({ "KeyPhraseId": str(uuid.uuid4()), "TranscriptionId": transcription_id, "KeyPhrase": key_phrase })

                # Save the full enriched JSON file
                full_json_output = {
                    "transcription": speech_results,
                    "analysis": language_results,
                    "usage": {
                        "analysis_total_tokens": analysis_tokens,
                        "transcription_time_seconds": transcription_time_seconds,
                        "analysis_time_seconds": analysis_time_seconds
                    }
                }
                transcript_json_filename = f"{os.path.splitext(audio_file)[0]}_enriched_transcript.json"
                target_json_path = os.path.join(LOCAL_TRANSCRIPTS_OUTPUT_PATH, transcript_json_filename)
                with open(target_json_path, 'w') as f_out: json.dump(full_json_output, f_out, indent=2)
            else:
                print(f"  [FAIL] Transcription status was '{status}'. Skipping enrichment.")
                print(f"  [ACTION] Check the log file for details: /lakehouse/default/Files/sdk-logs/speech-sdk-{os.path.splitext(audio_file)[0]}.log")

            # Log the final outcome
            print(f"  [LOG] Recording outcome for '{audio_file}'. Status: {status}")
            all_log_rows.append({
                "TranscriptionId": transcription_id, "AudioFileName": audio_file,
                "ProcessingTimestamp": datetime.utcnow(), "ProcessingStatus": status,
                "StatusDetails": status_details, "CallDurationHms": duration_hms,
                "TranscriptionTimeSeconds": transcription_time_seconds,
                "AnalysisTimeSeconds": analysis_time_seconds
            })

        except Exception as e:
            print(f"  ❌ An unhandled error occurred for {audio_file}: {e}")
            if not any(log['AudioFileName'] == audio_file for log in all_log_rows):
                all_log_rows.append({
                    "TranscriptionId": str(uuid.uuid4()), "AudioFileName": audio_file,
                    "ProcessingTimestamp": datetime.utcnow(), "ProcessingStatus": "PythonHardError",
                    "StatusDetails": json.dumps({"error": str(e)}), "CallDurationHms": "00:00:00",
                    "TranscriptionTimeSeconds": transcription_time_seconds,
                    "AnalysisTimeSeconds": analysis_time_seconds
                })
            is_successful = False

        finally:
            destination_dir = LOCAL_PROCESSED_AUDIO_PATH if is_successful else LOCAL_FAILED_AUDIO_PATH
            try:
                shutil.move(source_file_path, destination_dir)
            except Exception as move_error:
                print(f"  [ERROR] Failed to move file '{audio_file}': {move_error}")

if not audio_files_to_process:
    print(f"\n🏁 No new files to process. All files in the input directory have already been successfully processed.")
else:
    print(f"\n🏁 Finished processing all new files. Preparing to write to Lakehouse tables.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# > **Cell Purpose:** This cell is responsible for persisting the results. It defines the schema for each of the six target Delta tables and then calls a helper function to convert the in-memory lists of results into Spark DataFrames and write them to the Lakehouse, appending the new data.
# 
# ### **Cell 7: Write DataFrames to Lakehouse Tables**

# CELL ********************

def save_data_to_table(data_rows, table_name, schema, spark_session):
    """Helper function to create and save a DataFrame to a Delta table."""
    if data_rows:
        try:
            print(f"\n📝 Attempting to write {len(data_rows)} records to '{table_name}'...")
            df = spark_session.createDataFrame(data=data_rows, schema=schema)
            df.write.option("mergeSchema", "true").mode("append").format("delta").saveAsTable(table_name)
            print(f"✅ Successfully wrote {df.count()} records to '{table_name}'.")
        except Exception as e:
            print(f"❌ Error writing to table '{table_name}': {e}")
    else:
        print(f"\nℹ️ No new data to write to table '{table_name}'.")

# --- Define Schemas ---
log_schema = StructType([
    StructField("TranscriptionId", StringType(), True),
    StructField("AudioFileName", StringType(), True),
    StructField("ProcessingTimestamp", TimestampType(), True),
    StructField("ProcessingStatus", StringType(), True),
    StructField("StatusDetails", StringType(), True),
    StructField("CallDurationHms", StringType(), True),
    StructField("TranscriptionTimeSeconds", DoubleType(), True),
    StructField("AnalysisTimeSeconds", DoubleType(), True)
])

transcripts_schema = StructType([
    StructField("TranscriptionId", StringType(), True),
    StructField("AudioFileName", StringType(), True),
    StructField("ProcessingTimestamp", TimestampType(), True),
    StructField("ProcessingStatus", StringType(), True),
    StructField("CallDurationSeconds", DoubleType(), True),
    StructField("CallDurationHms", StringType(), True),
    StructField("OverallSentiment", StringType(), True),
    StructField("PiiRedactedText", StringType(), True),
    StructField("TranscriptMainTopic", StringType(), True),
    StructField("ConversationType", StringType(), True),
    StructField("TotalTokens", LongType(), True),
    StructField("LakehouseTranscriptPath", StringType(), True)
])

pii_schema = StructType([
    StructField("PiiEntityId", StringType(), True),
    StructField("TranscriptionId", StringType(), True),
    StructField("PiiText", StringType(), True),
    StructField("PiiCategory", StringType(), True),
    StructField("PiiSubcategory", StringType(), True),
    StructField("ConfidenceScore", FloatType(), True)
])

phrases_schema = StructType([
    StructField("PhraseId", StringType(), True),
    StructField("TranscriptionId", StringType(), True),
    StructField("SpeakerId", StringType(), True),
    StructField("PhraseText", StringType(), True),
    StructField("OffsetInSeconds", DoubleType(), True),
    StructField("DurationInSeconds", DoubleType(), True),
    StructField("Confidence", FloatType(), True)
])

sentence_sentiments_schema = StructType([
    StructField("SentenceId", StringType(), True),
    StructField("TranscriptionId", StringType(), True),
    StructField("SentenceText", StringType(), True),
    StructField("Sentiment", StringType(), True),
    StructField("PositiveScore", FloatType(), True),
    StructField("NeutralScore", FloatType(), True),
    StructField("NegativeScore", FloatType(), True)
])

key_phrases_schema = StructType([
    StructField("KeyPhraseId", StringType(), True),
    StructField("TranscriptionId", StringType(), True),
    StructField("KeyPhrase", StringType(), True)
])

# --- Save Data to Each Table ---
save_data_to_table(all_log_rows, TRANSCRIPTION_LOG_TABLE, log_schema, spark)
save_data_to_table(all_transcripts_rows, MAIN_TRANSCRIPTS_TABLE, transcripts_schema, spark)
save_data_to_table(all_pii_entities_rows, PII_ENTITIES_TABLE, pii_schema, spark)
save_data_to_table(all_phrases_rows, TRANSCRIPT_PHRASES_TABLE, phrases_schema, spark)
save_data_to_table(all_sentence_sentiments_rows, SENTENCE_SENTIMENTS_TABLE, sentence_sentiments_schema, spark)
save_data_to_table(all_key_phrases_rows, KEY_PHRASES_TABLE, key_phrases_schema, spark)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# > **Cell Purpose:** This optional cell allows you to run simple Spark SQL queries against the final Delta tables to quickly verify that the data was written correctly and inspect the results.
# 
# ### **Cell 8: Verification (Optional)**

# CELL ********************

# Verify data in the main transcript and PII tables
print(f"\n🔍 Verifying data in the main Lakehouse table: {MAIN_TRANSCRIPTS_TABLE}")
try:
    if spark.catalog.tableExists(MAIN_TRANSCRIPTS_TABLE):
        df_transcripts = spark.read.table(MAIN_TRANSCRIPTS_TABLE)
        print(f"Total records in '{MAIN_TRANSCRIPTS_TABLE}': {df_transcripts.count()}")
        df_transcripts.select(
            "AudioFileName", "ProcessingStatus", "OverallSentiment",
            "TranscriptMainTopic", "ConversationType", "TotalTokens"
        ).show(10, truncate=False)
    else:
        print(f"⚠️ TABLE NOT FOUND: Lakehouse table '{MAIN_TRANSCRIPTS_TABLE}' does not exist.")
except Exception as e:
    print(f"❌ Error reading from Lakehouse table '{MAIN_TRANSCRIPTS_TABLE}': {e}")


print(f"\n🔍 Verifying data in the PII entities table: {PII_ENTITIES_TABLE}")
try:
    if spark.catalog.tableExists(PII_ENTITIES_TABLE):
        df_pii = spark.read.table(PII_ENTITIES_TABLE)
        print(f"Total records in '{PII_ENTITIES_TABLE}': {df_pii.count()}")
        df_pii.show(10, truncate=False)
    else:
        print(f"⚠️ TABLE NOT FOUND: Lakehouse table '{PII_ENTITIES_TABLE}' does not exist.")
except Exception as e:
    print(f"❌ Error reading from Lakehouse table '{PII_ENTITIES_TABLE}': {e}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
