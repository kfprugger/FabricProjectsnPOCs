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
# META     }
# META   }
# META }

# MARKDOWN ********************

# 
# ### Notebook Summary
# 
# This new notebook is a complete solution for redacting sensitive information from audio files based on the PII (Personally Identifiable Information) detected in the previous transcription process. It is designed to be run after your transcription notebook is complete.
# 
# * **Reads Processed Data**: The notebook is configured to read the audio files from the `/Files/processed-audio/` directory and their corresponding JSON analysis files from `/Files/transcripts/`.
# * **Identifies PII Timestamps**: It parses the JSON files to find PII entities and, most importantly, calculates their precise start and end times within the audio by cross-referencing the `transcript_segments` table. This is a critical step to ensure redactions are accurate.
# * **Configurable Redaction Mode**: You can easily choose how to redact the audio by setting a variable. The two modes are:
#     * `'SILENCE'`: Replaces the PII with complete silence.
#     * `'BLEEP'`: Replaces the PII with a generated bleep tone.
# * **Audio Manipulation with Pydub**: The notebook uses the powerful `pydub` library to slice the original audio, generate the redaction sound (silence or bleep), and stitch everything back together into a new, clean audio file.
# * **Writes Redacted Audio**: The final, redacted audio files are saved to a new `/Files/redacted-audio/` directory in your Lakehouse, keeping your original and processed files intact.
# 
# Here is the complete, runnable Microsoft Fabric notebook.
# 
# ---
# 
# ### **New Notebook: Audio PII Redaction**
# 
# This notebook reads the output from the "Call Center Transcription & Analysis" notebook, identifies the timestamps of detected PII, and redacts those sections from the original audio files by replacing them with either silence or a bleep tone.
# 
# ---
# ### **Cell 1: Install Required Libraries**
# This cell installs the `pydub` library, which is essential for audio manipulation tasks like slicing, generating tones, and exporting audio files.


# CELL ********************

%pip install pydub

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# ### **Cell 2: Imports and Spark Initialization**
# This cell imports all required modules for file system interaction, data manipulation with Spark, and audio processing with `pydub`.

# CELL ********************

import os
import json
import math
import array
from datetime import datetime

from pyspark.sql import SparkSession
import pyspark.sql.functions as F
from pyspark.sql.functions import col, lit, udf
from pyspark.sql.types import ArrayType, StructType, StructField, StringType, DoubleType

# pydub is used for audio manipulation
from pydub import AudioSegment
from pydub.generators import Sine

# Initialize Spark Session
spark = SparkSession.builder.appName("AudioRedaction").getOrCreate()

print("Spark session initialized and libraries imported. 🚀")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# ### **Cell 3: Configuration**
# This cell sets up all the necessary paths for the redaction process and allows you to configure the redaction method.

# CELL ********************

# --- Redaction Configuration ---
# Choose your redaction method: 'SILENCE' or 'BLEEP'
REDACTION_MODE = 'BLEEP'
BLEEP_FREQUENCY = 1000  # Hz (A standard 1kHz bleep tone)
BLEEP_VOLUME_REDUCTION = 6 # dB, reduce the bleep volume to make it less jarring


# --- Fabric Lakehouse Path Configurations (Unchanged) ---
LAKEHOUSE_AUDIO_INPUT_DIR_RELATIVE = "Files/audio-files"
LAKEHOUSE_TRANSCRIPTS_OUTPUT_DIR_RELATIVE = "Files/transcripts"
LAKEHOUSE_PROCESSED_AUDIO_DIR_RELATIVE = "Files/processed-audio"
LAKEHOUSE_FAILED_AUDIO_DIR_RELATIVE = "Files/failed"
LAKEHOUSE_SDK_LOGS_DIR_RELATIVE = "Files/sdk-logs"

# --- Fabric Lakehouse Table Configurations (Unchanged) ---
LAKEHOUSE_NAME_FOR_TABLES = "bronze_aoai_lh" 
LAKEHOUSE_TRANSCRIPTS_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.transcripts"
TRANSCRIPTION_LOG_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.transcribe_log"
LAKEHOUSE_PII_ENTITIES_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.pii_entities"
LAKEHOUSE_SEGMENTS_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.transcript_phrases"
SENTENCE_SENTIMENTS_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.sentence_sentiments"
KEY_PHRASES_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.key_phrases"


# --- Fabric Lakehouse Configuration ---
LAKEHOUSE_NAME = "bronze_aoai_lh" 



# This is the destination for the newly created redacted audio files
LAKEHOUSE_REDACTED_AUDIO_DIR_RELATIVE = "Files/redacted-audio"


# --- Local Paths for Notebook Processing (via Lakehouse mount) ---
LOCAL_LAKEHOUSE_ROOT = "/lakehouse/default/"
LOCAL_PROCESSED_AUDIO_PATH = os.path.join(LOCAL_LAKEHOUSE_ROOT, LAKEHOUSE_PROCESSED_AUDIO_DIR_RELATIVE)
LOCAL_REDACTED_AUDIO_PATH = os.path.join(LOCAL_LAKEHOUSE_ROOT, LAKEHOUSE_REDACTED_AUDIO_DIR_RELATIVE)

# Ensure the output directory exists
os.makedirs(LOCAL_REDACTED_AUDIO_PATH, exist_ok=True)
print(f"Configuration set. Redaction mode: '{REDACTION_MODE}'")
print(f"Redacted audio will be saved to: {LOCAL_REDACTED_AUDIO_PATH}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# ### **Cell 4: Find PII Timestamps**
# This is the core data processing step. This cell uses Spark to join the tables from the previous notebook. It performs a complex join to accurately calculate the start and end timestamps for each PII entity by finding which audio segment it belongs to.

# CELL ********************

import pyspark.sql.functions as F
from pyspark.sql.functions import col, udf
from pyspark.sql.types import ArrayType, StructType, StructField, StringType, DoubleType

try:
    # 1. Read the base tables from the previous notebook
    transcripts_df = spark.read.table(LAKEHOUSE_TRANSCRIPTS_TABLE)
    pii_df = spark.read.table(LAKEHOUSE_PII_ENTITIES_TABLE)
    segments_df = spark.read.table(LAKEHOUSE_SEGMENTS_TABLE).join(
        transcripts_df.select("TranscriptionId", "AudioFileName"), "TranscriptionId"
    )
    print("Successfully loaded transcripts, PII, and segments tables.")

    # 2. For each transcript, create a list of all its PII entities
    pii_list_df = pii_df.groupBy("TranscriptionId").agg(
        F.collect_list(F.struct(
            F.col("PiiText"),
            F.col("PiiCategory")
        )).alias("PiiList")
    )
    
    # 3. Join the PII list with the audio segments table
    # This is a simple equijoin, which is highly optimized
    segments_with_pii_list_df = segments_df.join(pii_list_df, "TranscriptionId")

    # 4. Define a UDF to find all PII entities that appear in a given phrase
    pii_struct = StructType([
        StructField("PiiText", StringType()),
        StructField("PiiCategory", StringType())
    ])

    @udf(returnType=ArrayType(pii_struct))
    def find_all_pii_in_phrase(phrase_text, pii_list):
        matches = []
        if not phrase_text or not pii_list:
            return None
        for pii_entity in pii_list:
            if pii_entity["PiiText"] in phrase_text:
                matches.append(pii_entity)
        return matches if matches else None

    # 5. Apply the UDF to find matches and explode the results
    # This creates a separate row for each PII entity found in a phrase
    pii_located_df = segments_with_pii_list_df.withColumn(
        "MatchedPii", find_all_pii_in_phrase(col("PhraseText"), col("PiiList"))
    ).where(
        col("MatchedPii").isNotNull()
    ).withColumn(
        "PiiMatch", F.explode(col("MatchedPii"))
    ).select(
        "AudioFileName",
        col("PiiMatch.PiiText").alias("PiiText"),
        "PhraseText",
        "OffsetInSeconds",
        "DurationInSeconds"
    )

    # 6. Define the UDF to calculate the precise timing of the PII within the phrase
    @udf(returnType=StructType([
        StructField("start_ms", DoubleType(), False),
        StructField("end_ms", DoubleType(), False)
    ]))
    def calculate_pii_timing(pii_text, segment_text, offset_sec, duration_sec):
        try:
            start_index = segment_text.find(pii_text)
            if start_index == -1: return None
            
            start_ratio = start_index / len(segment_text)
            pii_start_time_sec = offset_sec + (duration_sec * start_ratio)
            
            duration_ratio = len(pii_text) / len(segment_text)
            pii_duration_sec = duration_sec * duration_ratio
            
            pii_end_time_sec = pii_start_time_sec + pii_duration_sec
            return {"start_ms": pii_start_time_sec * 1000, "end_ms": pii_end_time_sec * 1000}
        except:
            return None

    # 7. Apply the timing UDF to get the final redaction timestamps
    pii_timestamps_df = pii_located_df.withColumn(
        "timing",
        calculate_pii_timing(col("PiiText"), col("PhraseText"), col("OffsetInSeconds"), col("DurationInSeconds"))
    ).select(
        "AudioFileName",
        "PiiText",
        col("timing.start_ms").alias("start_ms"),
        col("timing.end_ms").alias("end_ms")
    ).dropna()

    # 8. Group by filename to get a list of all redaction timestamps for each file
    redaction_plan_df = pii_timestamps_df.groupBy("AudioFileName").agg(
        F.collect_list(F.struct("start_ms", "end_ms")).alias("redactions")
    )

    print("Successfully created redaction plan:")
    redaction_plan_df.show(truncate=False)
    print(f"Found {redaction_plan_df.count()} files with PII to be redacted.")

except Exception as e:
    print(f"❌ An error occurred while reading or processing the tables. Make sure the previous notebook ran successfully.")
    print(e)
    redaction_plan_df = None

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# ### **Cell 5: Main Redaction Loop**
# This cell iterates through the redaction plan created in the previous cell. For each audio file, it loads the audio data, applies the redactions (silence or bleeps) according to the timestamps, and saves the new file.

# CELL ********************


if redaction_plan_df:
    redaction_plan = redaction_plan_df.collect()

    print(f"\nStarting audio redaction process for {len(redaction_plan)} files...")

    for row in redaction_plan:
        audio_filename = row["AudioFileName"]
        redactions = sorted(row["redactions"], key=lambda x: x['start_ms']) # Sort by start time

        source_audio_path = os.path.join(LOCAL_PROCESSED_AUDIO_PATH, audio_filename)
        redacted_audio_path = os.path.join(LOCAL_REDACTED_AUDIO_PATH, f"REDACTED_{audio_filename}")

        print(f"\n🔄 Processing '{audio_filename}'...")

        if not os.path.exists(source_audio_path):
            print(f"  [WARN] Source audio file not found, skipping: {source_audio_path}")
            continue

        try:
            # Load the original audio file
            original_audio = AudioSegment.from_wav(source_audio_path)
            redacted_audio = AudioSegment.empty()

            last_end_ms = 0

            # Iterate through the redaction timestamps and build the new audio file
            for redaction in redactions:
                start_ms = int(redaction['start_ms'])
                end_ms = int(redaction['end_ms'])

                # Append the clean audio segment before the PII
                redacted_audio += original_audio[last_end_ms:start_ms]

                # Generate and append the redaction segment (silence or bleep)
                duration_ms = end_ms - start_ms
                if duration_ms > 0:
                    if REDACTION_MODE == 'SILENCE':
                        redaction_segment = AudioSegment.silent(duration=duration_ms)
                    else: # BLEEP mode
                        bleep = Sine(BLEEP_FREQUENCY).to_audio_segment(duration=duration_ms).apply_gain(-BLEEP_VOLUME_REDUCTION)
                        redaction_segment = bleep

                    redacted_audio += redaction_segment

                last_end_ms = end_ms

            # Append the rest of the audio after the last PII
            redacted_audio += original_audio[last_end_ms:]

            # Export the final redacted audio file
            redacted_audio.export(redacted_audio_path, format="wav")
            print(f"  [SUCCESS] Redacted audio saved to: {redacted_audio_path}")

        except Exception as e:
            print(f"  [ERROR] Failed to redact '{audio_filename}'. Error: {e}")

    print("\n\n🏁 Finished processing all files.")
else:
    print("ℹ️ No redaction plan was generated. Nothing to process.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ---
# ### **Cell 6: Verification**
# This final cell lists the files in the output directory, allowing you to quickly confirm that the new, redacted audio files have been successfully created.

# CELL ********************

print("Verifying redacted audio files...\n")

try:
    redacted_files = os.listdir(LOCAL_REDACTED_AUDIO_PATH)
    if not redacted_files:
        print("No files found in the redacted audio directory.")
    else:
        print(f"Found {len(redacted_files)} redacted files:")
        for filename in redacted_files:
            print(f"- {filename}")
except Exception as e:
    print(f"An error occurred while listing files: {e}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
