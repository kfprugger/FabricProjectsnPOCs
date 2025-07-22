# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# Okay, I understand you want to start over and build upon the previous plan. We'll analyze the provided Microsoft Learn page again (though my previous analysis is still largely valid) and then create a Python notebook for Microsoft Fabric.
# 
# This enhanced notebook will:
# 
# 1.  Read audio files from `/Files/audio-files/` in your Fabric Lakehouse.
# 2.  Transcribe them using Azure AI Speech Services.
# 3.  Enrich the transcription with additional insights using Azure AI Language Services:
#     * Sentiment analysis (overall and per-sentence).
#     * Key phrase extraction (to identify call subject matter).
#     * PII (Personally Identifiable Information) entity recognition.
# 4.  Save the comprehensive JSON output (including transcription and enrichments) to `/Files/transcripts/` in your Lakehouse.
# 5.  Insert this enriched data into a new table in your Lakehouse, with an appropriately updated schema.
# 
# The quickstart you linked focuses on the capabilities of Azure for call centers, which often involves batch processing and combining Speech service outputs with Language service outputs. We'll adapt this by processing files individually within the Fabric notebook, making calls to both services.
# 
# ---
# ## Enhanced Notebook: Call Center Transcription & Analysis in Microsoft Fabric
# 
# This notebook processes audio files, performs speech-to-text, and enriches transcripts with sentiment, key phrases, and PII detection before storing them in a Lakehouse table and as JSON files.
# 
# ---
# ### Cell 1: Install Required Libraries
# Ensure the necessary Azure SDKs for Speech and Text Analytics (Language) are installed.


# CELL ********************

%pip install azure-cognitiveservices-speech azure-ai-textanalytics

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# ### Cell 2: Imports and Spark Initialization
# Import all required modules and initialize the Spark session.

# CELL ********************

import os
import json
import time
import shutil
import tempfile
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType,
    ArrayType, MapType, LongType, DoubleType, FloatType # Added FloatType for scores
)

# Azure SDKs
import azure.cognitiveservices.speech as speechsdk
from azure.core.credentials import AzureKeyCredential
from azure.ai.textanalytics import TextAnalyticsClient

# Initialize Spark Session
spark = SparkSession.builder.appName("EnhancedCallCenterAnalysisFabric").getOrCreate()

print("Spark session initialized and libraries imported. 🚀")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# ### Cell 3: Configuration
# Set up your Azure service credentials and Lakehouse paths.

# CELL ********************

# --- Azure Speech Service Configuration ---
# ⚠️ IMPORTANT: Store these securely (e.g., Azure Key Vault linked to Fabric)
SPEECH_KEY = "YOUR_SPEECH_SERVICE_KEY"
SPEECH_REGION = "YOUR_SPEECH_SERVICE_REGION"  # e.g., "eastus"

# --- Azure AI Language Service (Text Analytics) Configuration ---
LANGUAGE_KEY = "YOUR_LANGUAGE_SERVICE_KEY"
LANGUAGE_ENDPOINT = "YOUR_LANGUAGE_SERVICE_ENDPOINT" # e.g., https://your-language-resource.cognitiveservices.azure.com/

# --- Fabric Lakehouse Paths ---
LAKEHOUSE_AUDIO_INPUT_DIR_RELATIVE = "Files/audio-files"
LAKEHOUSE_TRANSCRIPTS_OUTPUT_DIR_RELATIVE = "Files/transcripts"

# --- Fabric Lakehouse Table Configuration ---
LAKEHOUSE_NAME_FOR_TABLE = spark.conf.get("spark.synapse.workspace.defaultLakehouseName", "your_default_lakehouse_name_if_not_set")
ENRICHED_TABLE_NAME = "call_center_enriched_transcripts"
QUALIFIED_ENRICHED_TABLE_NAME = f"{LAKEHOUSE_NAME_FOR_TABLE}.{ENRICHED_TABLE_NAME}"

# --- Local Paths for Notebook Processing (via Lakehouse mount) ---
LOCAL_LAKEHOUSE_ROOT = "/lakehouse/default/"
LOCAL_AUDIO_INPUT_PATH = os.path.join(LOCAL_LAKEHOUSE_ROOT, LAKEHOUSE_AUDIO_INPUT_DIR_RELATIVE)
LOCAL_TRANSCRIPTS_OUTPUT_PATH = os.path.join(LOCAL_LAKEHOUSE_ROOT, LAKEHOUSE_TRANSCRIPTS_OUTPUT_DIR_RELATIVE)

print(f"Speech Service Region: {SPEECH_REGION}")
print(f"Language Service Endpoint: {LANGUAGE_ENDPOINT}")
print(f"Using Lakehouse: {LAKEHOUSE_NAME_FOR_TABLE}")
print(f"Lakehouse Audio Input (Mounted): {LOCAL_AUDIO_INPUT_PATH}")
print(f"Lakehouse Transcripts Output (Mounted): {LOCAL_TRANSCRIPTS_OUTPUT_PATH}")
print(f"Target Delta Table: {QUALIFIED_ENRICHED_TABLE_NAME}")

# Initialize Text Analytics Client
try:
    text_analytics_client = TextAnalyticsClient(endpoint=LANGUAGE_ENDPOINT, credential=AzureKeyCredential(LANGUAGE_KEY))
    print("Text Analytics client initialized successfully.")
except Exception as ta_ex:
    print(f"Error initializing Text Analytics client: {ta_ex}. Please check LANGUAGE_KEY and LANGUAGE_ENDPOINT.")
    # Optionally raise error or handle: raise ta_ex

# Create transcript output directory in Lakehouse Files
try:
    os.makedirs(LOCAL_TRANSCRIPTS_OUTPUT_PATH, exist_ok=True)
    print(f"Ensured transcript output directory exists: {LOCAL_TRANSCRIPTS_OUTPUT_PATH}")
except OSError as e:
    print(f"Error creating directory {LOCAL_TRANSCRIPTS_OUTPUT_PATH}. Error: {e}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# **➡️ Action**: Replace `YOUR_SPEECH_SERVICE_KEY`, `YOUR_SPEECH_SERVICE_REGION`, `YOUR_LANGUAGE_SERVICE_KEY`, `YOUR_LANGUAGE_SERVICE_ENDPOINT`, and potentially `your_default_lakehouse_name_if_not_set` with your actual values.
# 
# ---
# ### Cell 4: Helper Functions - Transcription and Text Analytics
# This cell contains functions for speech transcription and calls to the Language service.

# CELL ********************

def transcribe_audio(speech_key, speech_region, local_audio_file_path):
    """Transcribes a mono audio file using Speech SDK."""
    audio_filename = os.path.basename(local_audio_file_path)
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_recognition_language = "en-US"
    speech_config.output_format = speechsdk.OutputFormat.Detailed
    speech_config.request_word_level_timestamps()

    if not os.path.exists(local_audio_file_path) or os.path.getsize(local_audio_file_path) == 0:
        print(f"Audio file {audio_filename} is missing or empty.")
        return {"AudioFileName": audio_filename, "ProcessingStatus": "ErrorFileNotFoundOrEmpty", "Timestamp": datetime.utcnow().isoformat() + "Z", "RecognizedPhrases": [], "CombinedDisplayText": "", "TotalDurationInSeconds": 0.0}

    audio_config = speechsdk.audio.AudioConfig(filename=local_audio_file_path)
    speech_recognizer = speechsdk.SpeechRecognizer(speech_config=speech_config, audio_config=audio_config)

    done = False
    recognized_phrases = []
    combined_text_parts = []
    total_duration_ticks = 0
    cancellation_details_output = {}

    def on_recognized(evt: speechsdk.SpeechRecognitionEventArgs):
        nonlocal total_duration_ticks
        if evt.result.reason == speechsdk.ResultReason.RecognizedSpeech:
            json_output = json.loads(evt.result.json)
            display_text = json_output.get("DisplayText")
            combined_text_parts.append(display_text)
            total_duration_ticks += evt.result.duration_in_ticks
            phrase = {
                "SpeakerId": "Speaker_1", # Placeholder
                "Text": display_text, "Lexical": json_output.get("NBest", [{}])[0].get("Lexical", ""),
                "ITN": json_output.get("NBest", [{}])[0].get("ITN", ""),
                "MaskedITN": json_output.get("NBest", [{}])[0].get("MaskedITN", ""),
                "OffsetInTicks": evt.result.offset_in_ticks, "DurationInTicks": evt.result.duration_in_ticks,
                "Confidence": json_output.get("NBest", [{}])[0].get("Confidence", 0.0),
                "Words": json_output.get("NBest", [{}])[0].get("Words", [])
            }
            recognized_phrases.append(phrase)
        elif evt.result.reason == speechsdk.ResultReason.NoMatch:
            print(f"NOMATCH for {audio_filename}: No speech. SessionId: {evt.session_id}")

    def on_canceled(evt: speechsdk.SpeechRecognitionCanceledEventArgs):
        nonlocal done, cancellation_details_output
        cancellation_details_output = {"reason": str(evt.reason)}
        if evt.reason == speechsdk.CancellationReason.Error:
            cancellation_details_output["error_code"] = str(evt.error_code)
            cancellation_details_output["error_details"] = evt.error_details
        done = True

    def on_session_stopped(evt: speechsdk.SessionEventArgs): nonlocal done; done = True

    speech_recognizer.recognized.connect(on_recognized)
    speech_recognizer.session_started.connect(lambda evt: print(f"SESSION STARTED for {audio_filename}. SessionId: {evt.session_id}"))
    speech_recognizer.session_stopped.connect(on_session_stopped)
    speech_recognizer.canceled.connect(on_canceled)

    speech_recognizer.start_continuous_recognition()
    loop_start_time = time.time()
    while not done:
        time.sleep(0.2)
        if time.time() - loop_start_time > 600: break # 10-min timeout
    speech_recognizer.stop_continuous_recognition()

    status = "Success"
    if not recognized_phrases:
        status = f"ErrorOrNoMatch_{cancellation_details_output.get('reason', 'NoMatch')}" if cancellation_details_output else "NoMatchOrEmpty"

    return {
        "AudioFileName": audio_filename, "ProcessingStatus": status,
        "Timestamp": datetime.utcnow().isoformat() + "Z",
        "RecognizedPhrases": recognized_phrases,
        "CombinedDisplayText": " ".join(combined_text_parts).strip(),
        "TotalDurationInSeconds": total_duration_ticks / 10_000_000.0, # Ticks to seconds
        "CancellationDetails": cancellation_details_output if cancellation_details_output else None
    }

def analyze_transcript_with_language_service(client: TextAnalyticsClient, text_to_analyze: str, audio_filename: str):
    """Analyzes text for sentiment, key phrases, and PII entities."""
    if not text_to_analyze or not text_to_analyze.strip():
        return {"Sentiment": "N/A", "KeyPhrases": [], "PiiEntities": [], "SentencesSentiment": []}

    analysis_results = {}
    documents = [text_to_analyze]

    try:
        # Sentiment Analysis (includes sentence-level)
        sentiment_response = client.analyze_sentiment(documents, show_opinion_mining=True)
        doc_sentiment = sentiment_response[0]
        if not doc_sentiment.is_error:
            analysis_results["Sentiment"] = doc_sentiment.sentiment
            analysis_results["SentimentScores"] = {
                "Positive": doc_sentiment.confidence_scores.positive,
                "Neutral": doc_sentiment.confidence_scores.neutral,
                "Negative": doc_sentiment.confidence_scores.negative
            }
            sentences_sentiment = []
            for sentence in doc_sentiment.sentences:
                sentences_sentiment.append({
                    "Text": sentence.text,
                    "Sentiment": sentence.sentiment,
                    "Scores": {
                        "Positive": sentence.confidence_scores.positive,
                        "Neutral": sentence.confidence_scores.neutral,
                        "Negative": sentence.confidence_scores.negative
                    },
                    "Opinions": [{"Target": opinion.target.text, "Assessments": [asm.text for asm in opinion.assessments]} for opinion in sentence.mined_opinions]
                })
            analysis_results["SentencesSentiment"] = sentences_sentiment
        else:
            analysis_results["Sentiment"] = f"Error: {doc_sentiment.error.code} - {doc_sentiment.error.message}"
            analysis_results["SentencesSentiment"] = []


        # Key Phrase Extraction
        key_phrases_response = client.extract_key_phrases(documents)
        if not key_phrases_response[0].is_error:
            analysis_results["KeyPhrases"] = key_phrases_response[0].key_phrases
        else:
            analysis_results["KeyPhrases"] = [f"Error: {key_phrases_response[0].error.code} - {key_phrases_response[0].error.message}"]


        # PII Entity Recognition
        pii_response = client.recognize_pii_entities(documents)
        pii_entities_list = []
        if not pii_response[0].is_error:
            for entity in pii_response[0].entities:
                pii_entities_list.append({"Text": entity.text, "Category": entity.category, "Subcategory": entity.subcategory, "ConfidenceScore": entity.confidence_score})
            analysis_results["PiiEntities"] = pii_entities_list
            analysis_results["PiiRedactedText"] = pii_response[0].redacted_text # Example of getting redacted text
        else:
             analysis_results["PiiEntities"] = [{"Error": f"{pii_response[0].error.code} - {pii_response[0].error.message}"}]


    except Exception as e:
        print(f"  Error during Text Analytics for {audio_filename}: {e}")
        return {"Sentiment": "Error", "KeyPhrases": [str(e)], "PiiEntities": [{"Error": str(e)}], "SentencesSentiment": []}

    return analysis_results

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# ### Cell 5: Main Processing Loop
# Iterate, transcribe, analyze, and save.

# CELL ********************

all_audio_files = []
if os.path.exists(LOCAL_AUDIO_INPUT_PATH):
    for item_name in os.listdir(LOCAL_AUDIO_INPUT_PATH):
        if item_name.lower().endswith((".wav", ".mp3")): # Ensure your files are in supported formats
            full_item_path = os.path.join(LOCAL_AUDIO_INPUT_PATH, item_name)
            if os.path.isfile(full_item_path):
                 all_audio_files.append(item_name)
else:
    print(f"⚠️ Audio input directory not found: {LOCAL_AUDIO_INPUT_PATH}")

print(f"Found {len(all_audio_files)} audio files to process in {LOCAL_AUDIO_INPUT_PATH}.")

enriched_transcripts_for_table = []

with tempfile.TemporaryDirectory(prefix="fabric_speech_sdk_") as local_sdk_temp_dir:
    print(f"Using temporary directory for SDK audio processing: {local_sdk_temp_dir}")

    for audio_file in all_audio_files:
        source_lakehouse_file_path = os.path.join(LOCAL_AUDIO_INPUT_PATH, audio_file)
        temp_audio_file_for_sdk = os.path.join(local_sdk_temp_dir, audio_file)
        combined_json_output = {} # To store results from all services

        print(f"\n🔄 Processing: {audio_file}...")
        try:
            shutil.copy2(source_lakehouse_file_path, temp_audio_file_for_sdk)

            # 1. Speech Transcription
            speech_result_json = transcribe_audio(SPEECH_KEY, SPEECH_REGION, temp_audio_file_for_sdk)
            combined_json_output.update(speech_result_json) # Merge speech results

            # 2. Language Service Analysis (Sentiment, Key Phrases, PII)
            language_analysis_json = {}
            if speech_result_json.get("ProcessingStatus") == "Success" and speech_result_json.get("CombinedDisplayText"):
                if 'text_analytics_client' in locals() and text_analytics_client: # Check if client initialized
                    print(f"  🗣️ Transcript for Language Analysis: '{speech_result_json.get('CombinedDisplayText')[:100]}...'")
                    language_analysis_json = analyze_transcript_with_language_service(
                        text_analytics_client,
                        speech_result_json.get("CombinedDisplayText"),
                        audio_file
                    )
                    combined_json_output.update(language_analysis_json) # Merge language results
                    print(f"  📊 Language analysis complete. Overall Sentiment: {language_analysis_json.get('Sentiment')}")
                else:
                    print("  ⚠️ Text Analytics client not initialized. Skipping language analysis.")
            else:
                print(f"  ⚠️ Skipping Language Analysis due to transcription status: {speech_result_json.get('ProcessingStatus')}")

            # 3. Save comprehensive JSON to Lakehouse /Files/transcripts/
            transcript_json_filename = f"{os.path.splitext(audio_file)[0]}_enriched_transcript.json"
            target_json_lakehouse_path_local = os.path.join(LOCAL_TRANSCRIPTS_OUTPUT_PATH, transcript_json_filename)
            with open(target_json_lakehouse_path_local, 'w') as f_out:
                json.dump(combined_json_output, f_out, indent=2)
            print(f"  ✅ Enriched transcript JSON saved to Lakehouse Files: {target_json_lakehouse_path_local}")

            lakehouse_json_file_relative_path = os.path.join(LAKEHOUSE_TRANSCRIPTS_OUTPUT_DIR_RELATIVE, transcript_json_filename)

            # 4. Prepare data for the Lakehouse table
            row_data = {
                "AudioFileName": combined_json_output.get("AudioFileName"),
                "ProcessingTimestamp": datetime.strptime(combined_json_output.get("Timestamp"), "%Y-%m-%dT%H:%M:%S.%fZ") if "." in combined_json_output.get("Timestamp") else datetime.strptime(combined_json_output.get("Timestamp"), "%Y-%m-%dT%H:%M:%SZ"),
                "ProcessingStatus": combined_json_output.get("ProcessingStatus"),
                "CallDurationSeconds": combined_json_output.get("TotalDurationInSeconds"),
                "CombinedDisplayText": combined_json_output.get("CombinedDisplayText"),
                "OverallSentiment": language_analysis_json.get("Sentiment"),
                "SentimentScoresJson": json.dumps(language_analysis_json.get("SentimentScores")),
                "SentencesSentimentJson": json.dumps(language_analysis_json.get("SentencesSentiment")),
                "KeyPhrasesJson": json.dumps(language_analysis_json.get("KeyPhrases")),
                "PiiEntitiesJson": json.dumps(language_analysis_json.get("PiiEntities")),
                "PiiRedactedText": language_analysis_json.get("PiiRedactedText"), # From PII analysis
                "RecognizedPhrasesJsonString": json.dumps(combined_json_output.get("RecognizedPhrases")),
                "LakehouseTranscriptPath": lakehouse_json_file_relative_path,
                "CancellationDetailsJsonString": json.dumps(combined_json_output.get("CancellationDetails"))
            }
            enriched_transcripts_for_table.append(row_data)

        except Exception as e:
            print(f"  ❌ ERROR during main processing loop for {audio_file}: {e}")
            enriched_transcripts_for_table.append({ "AudioFileName": audio_file, "ProcessingTimestamp": datetime.utcnow(), "ProcessingStatus": "PythonErrorInCell5Loop", "CancellationDetailsJsonString": json.dumps({"error": str(e)})})
        finally:
            if os.path.exists(temp_audio_file_for_sdk): os.remove(temp_audio_file_for_sdk)

print("\n🏁 Finished processing all audio files.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# ### Cell 6: Define Enhanced Schema and Save to Lakehouse Table
# The schema now includes fields for sentiment, key phrases, and PII.

# CELL ********************

if enriched_transcripts_for_table:
    # Define the schema for the enriched table
    enriched_table_schema = StructType([
        StructField("AudioFileName", StringType(), True),
        StructField("ProcessingTimestamp", TimestampType(), True),
        StructField("ProcessingStatus", StringType(), True),
        StructField("CallDurationSeconds", DoubleType(), True), # Added
        StructField("CombinedDisplayText", StringType(), True),
        StructField("OverallSentiment", StringType(), True), # Added
        StructField("SentimentScoresJson", StringType(), True), # Added (e.g., {"Positive": 0.8, ...})
        StructField("SentencesSentimentJson", StringType(), True), # Added (Array of sentence sentiments)
        StructField("KeyPhrasesJson", StringType(), True), # Added (Array of strings)
        StructField("PiiEntitiesJson", StringType(), True), # Added (Array of PII entity objects)
        StructField("PiiRedactedText", StringType(), True), # Added
        StructField("RecognizedPhrasesJsonString", StringType(), True),
        StructField("LakehouseTranscriptPath", StringType(), True),
        StructField("CancellationDetailsJsonString", StringType(), True)
    ])

    try:
        enriched_df = spark.createDataFrame(data=enriched_transcripts_for_table, schema=enriched_table_schema)

        print("Preview of the Enriched DataFrame to be saved:")
        enriched_df.printSchema()
        enriched_df.show(5, truncate=30, vertical=True)

        print(f"\nWriting enriched data to Delta table: {QUALIFIED_ENRICHED_TABLE_NAME}...")
        enriched_df.write.mode("append").format("delta").saveAsTable(QUALIFIED_ENRICHED_TABLE_NAME)
        # For overwriting: .mode("overwrite").option("overwriteSchema", "true")

        print(f"✅ Successfully wrote {enriched_df.count()} enriched records to Lakehouse table: {QUALIFIED_ENRICHED_TABLE_NAME}")

    except Exception as e:
        print(f"❌ Error writing enriched data to Lakehouse table '{QUALIFIED_ENRICHED_TABLE_NAME}': {e}")
        fallback_df_path = f"Files/enriched_transcripts_df_fallback_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        try:
            if 'enriched_df' in locals():
                print(f"Attempting to save DataFrame to fallback Parquet path: {fallback_df_path}")
                enriched_df.write.format("parquet").mode("overwrite").save(fallback_df_path)
                print(f"DataFrame saved to fallback Parquet path: {fallback_df_path}")
        except Exception as fe:
            print(f"Error saving DataFrame to fallback Parquet path: {fe}")
else:
    print("ℹ️ No enriched transcript data was processed to save to the Lakehouse table.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# ### Cell 7: Verification (Optional)
# Query the new table to verify the enriched data.

# CELL ********************

# Verify data in the enriched Lakehouse table
try:
    print(f"\n🔍 Verifying data in enriched Lakehouse table: {QUALIFIED_ENRICHED_TABLE_NAME}")
    if spark.catalog.tableExists(QUALIFIED_ENRICHED_TABLE_NAME):
        df_from_lakehouse = spark.read.table(QUALIFIED_ENRICHED_TABLE_NAME)
        print(f"Total records in '{QUALIFIED_ENRICHED_TABLE_NAME}': {df_from_lakehouse.count()}")

        print("Sample enriched records (select relevant new columns):")
        df_from_lakehouse.select(
            "AudioFileName",
            "ProcessingStatus",
            "CallDurationSeconds",
            "OverallSentiment",
            "KeyPhrasesJson",
            "PiiEntitiesJson"
        ).show(10, truncate=50)

        print("\nRecords with processing errors (if any):")
        df_from_lakehouse.filter(~col("ProcessingStatus").isin("Success", "NoMatchOrEmpty")).show(truncate=70) # Using ~col & isin
    else:
        print(f"⚠️ TABLE NOT FOUND: Lakehouse table '{QUALIFIED_ENRICHED_TABLE_NAME}' does not exist.")
except Exception as e:
    print(f"❌ Error reading from Lakehouse table '{QUALIFIED_ENRICHED_TABLE_NAME}': {e}")

print(f"\n🎉 Enhanced Notebook execution for Call Center Analysis finished.")
# Add this import if using col() in the filter above and it's not already imported globally
from pyspark.sql.functions import col

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# 
# **Key Changes and Considerations:**
# 
# * **Azure AI Language Service Integration**: The notebook now makes explicit calls to the Language service for sentiment, key phrases, and PII detection.
# * **Comprehensive JSON**: The JSON files saved to `/Files/transcripts/` will contain the raw transcription segments *and* the results from the Language service analyses.
# * **Enhanced Table Schema**: The Delta table schema (`call_center_enriched_transcripts`) is significantly expanded to store this new information. Complex objects like lists of PII entities or sentence sentiments are stored as JSON strings. You can parse these further within Spark using `from_json` if needed for specific queries.
# * **Error Handling**: Basic error handling is included for Text Analytics calls.
# * **PII Redaction**: The `recognize_pii_entities` response includes `redacted_text`. This notebook now captures and stores it. If you only want to store redacted text instead of the original `CombinedDisplayText` in some cases, you can adjust the logic.
# * **"Other relevant info"**:
#     * `CallDurationSeconds` is now calculated and stored.
#     * PII detection is included.
#     * More advanced call center metrics (silence, interruption, talk-listen ratio) would require more sophisticated diarization (e.g., using `ConversationTranscriber` with multi-channel audio or more complex logic) and potentially custom audio processing beyond the direct scope of this adaptation.
# * **Configuration**: Remember to set **all four** credential/endpoint values in Cell 3.
# 
# This notebook provides a robust solution for transcribing and performing initial analysis on call center audio files directly within Microsoft Fabric.


# MARKDOWN ********************

# <div class="md-recitation">
#   Sources
#   <ol>
#   <li><a href="https://github.com/laruokol/Azure_cognitive">https://github.com/laruokol/Azure_cognitive</a></li>
#   </ol>
# </div>
