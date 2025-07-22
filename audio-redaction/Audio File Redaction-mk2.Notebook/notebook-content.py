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
# META       "default_lakehouse_workspace_id": "4414d1c5-d566-4308-b8d1-a275b09a7cf2"
# META     },
# META     "environment": {
# META       "environmentId": "564937f4-dbbc-80fe-42a8-004c8afb8e98",
# META       "workspaceId": "00000000-0000-0000-0000-000000000000"
# META     }
# META   }
# META }

# MARKDOWN ********************

# > **Cell Purpose:** Provides a high-level summary of the notebook's function, inputs, and outputs.
# 
# ### Notebook Summary
# 
# This notebook is a complete solution for redacting sensitive information from audio files based on the PII (Personally Identifiable Information) detected in a previous transcription process. It is designed to be run after your transcription notebook is complete.
# 
# * **Reads Processed Data**: The notebook reads audio files and their corresponding PII analysis tables from the Lakehouse.
# * **Identifies PII Timestamps**: It calculates the precise start and end times for each piece of PII within an audio file by cross-referencing transcription and PII tables.
# * **Configurable Redaction Mode**: You can easily choose how to redact the audio by setting a variable to either `'SILENCE'` or `'BLEEP'`.
# * **Audio Manipulation with Pydub**: The notebook uses the powerful `pydub` library to slice the original audio, generate the redaction sound, and stitch everything back together.
# * **Writes Redacted Audio**: The final, redacted audio files are saved to a new `/Files/redacted-audio/` directory, keeping your original files intact.


# MARKDOWN ********************

# ### TODO
# 
# I'll come back to developing this more once I have more time as the time offsets are sometimes off by a half second or two.

# MARKDOWN ********************

# > **Cell Purpose:** Installs the `pydub` library, which is essential for the audio manipulation tasks performed later in the notebook.
# 
# ---
# ### **Cell 1: Install Required Libraries**

# CELL ********************

# This cell installs the 'pydub' library. 

# Uncomment if running manually with a default env. 

# pydub is a powerful and easy-to-use Python library for audio manipulation.
# %pip install pydub

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# > **Cell Purpose:** Imports all the necessary libraries for file system interaction, data manipulation with Spark, and audio processing.
# 
# ---
# ### **Cell 2: Imports and Spark Initialization**

# CELL ********************

# This cell handles all the necessary imports and starts the Spark session.

# Standard Python library for interacting with the operating system (e.g., file paths)
import os

# PySpark libraries for distributed data processing
from pyspark.sql import SparkSession
import pyspark.sql.functions as F
from pyspark.sql.functions import col
from pyspark.sql.types import ArrayType, StructType, StructField, StringType, DoubleType

# pydub is used for the core audio manipulation tasks
from pydub import AudioSegment
from pydub.generators import Sine

# Initialize the Spark Session, which is the entry point to programming Spark with the DataFrame API.
spark = SparkSession.builder.appName("AudioRedaction").getOrCreate()

print("Spark session initialized and libraries imported. 🚀")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# > **Cell Purpose:** Sets up all the necessary configuration variables for the notebook, such as file paths and redaction behavior. Edit these variables to match your environment.
# 
# ---
# ### **Cell 3: Configuration**

# CELL ********************

# This cell contains all the configurable parameters for the notebook.
# Adjust these variables to match your environment and desired output.

# --- Redaction Behavior Configuration ---
# VARIABLE: REDACTION_MODE
# PURPOSE: Choose your redaction method. 
# OPTIONS: 'SILENCE' (replaces PII with silence), 'BLEEP' (replaces PII with a tone).
REDACTION_MODE = 'BLEEP'

# VARIABLE: BLEEP_FREQUENCY
# PURPOSE: Sets the frequency of the bleep tone in Hz. Only used if REDACTION_MODE is 'BLEEP'.
BLEEP_FREQUENCY = 1000  

# VARIABLE: BLEEP_VOLUME_REDUCTION
# PURPOSE: Reduces the bleep volume in dB to make it less jarring.
BLEEP_VOLUME_REDUCTION = 6

# --- Fabric Lakehouse Input/Output Configurations ---
# These variables define the directories and tables used for input and output.

# VARIABLE: LAKEHOUSE_PROCESSED_AUDIO_DIR_RELATIVE
# PURPOSE: The input directory in the Lakehouse 'Files' section containing the audio to be redacted.
LAKEHOUSE_PROCESSED_AUDIO_DIR_RELATIVE = "Files/processed-audio"

# VARIABLE: LAKEHOUSE_REDACTED_AUDIO_DIR_RELATIVE
# PURPOSE: The output directory in the Lakehouse 'Files' section where the redacted audio will be saved.
LAKEHOUSE_REDACTED_AUDIO_DIR_RELATIVE = "Files/redacted-audio" 

# VARIABLE: LAKEHOUSE_NAME_FOR_TABLES
# PURPOSE: The name of the Lakehouse where the input tables are stored.
LAKEHOUSE_NAME_FOR_TABLES = "bronze_aoai_lh"

# VARIABLE: LAKEHOUSE_*_TABLE
# PURPOSE: Full names of the tables created by the previous transcription notebook.
LAKEHOUSE_TRANSCRIPTS_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.transcripts"
LAKEHOUSE_PII_ENTITIES_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.pii_entities"
LAKEHOUSE_SEGMENTS_TABLE = f"{LAKEHOUSE_NAME_FOR_TABLES}.transcript_phrases"

# --- Local Paths for Notebook Processing ---
# These paths are the local mount points inside the notebook environment to access the Lakehouse files.
# You should not need to change these.
LOCAL_LAKEHOUSE_ROOT = "/lakehouse/default/"
LOCAL_PROCESSED_AUDIO_PATH = os.path.join(LOCAL_LAKEHOUSE_ROOT, LAKEHOUSE_PROCESSED_AUDIO_DIR_RELATIVE)
LOCAL_REDACTED_AUDIO_PATH = os.path.join(LOCAL_LAKEHOUSE_ROOT, LAKEHOUSE_REDACTED_AUDIO_DIR_RELATIVE)

# Ensure the output directory exists on the local file system
os.makedirs(LOCAL_REDACTED_AUDIO_PATH, exist_ok=True)

print(f"Configuration set. Redaction mode: '{REDACTION_MODE}'")
print(f"Redacted audio will be saved to: {LOCAL_REDACTED_AUDIO_PATH}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# > **Cell Purpose:** This is the core data processing step. This Spark job joins tables from the previous notebook to accurately calculate the start and end timestamps for each PII entity.
# 
# ---
# ### **Cell 4: Find PII Timestamps**

# CELL ********************

try:
    # Step 1: Read the base tables from the previous notebook.
    # We need the transcript phrases (segments), the PII entities, and the main transcript log to link them.
    transcripts_df = spark.read.table(LAKEHOUSE_TRANSCRIPTS_TABLE)
    pii_df = spark.read.table(LAKEHOUSE_PII_ENTITIES_TABLE)
    segments_df = spark.read.table(LAKEHOUSE_SEGMENTS_TABLE).join(
        transcripts_df.select("TranscriptionId", "AudioFileName"), "TranscriptionId"
    )
    print("✅ Successfully loaded transcripts, PII, and segments tables.")

    # Step 2: For each transcript, create an array of all its PII entities.
    # This aggregates all PII text for a given transcription into a single list.
    pii_list_df = pii_df.groupBy("TranscriptionId").agg(
        F.collect_list(F.struct(F.col("PiiText"), F.col("PiiCategory"))).alias("PiiList")
    )
    
    # Step 3: Join the PII list with the audio segments table.
    # Now each segment (phrase) row also has the full list of PII for that audio file.
    segments_with_pii_list_df = segments_df.join(pii_list_df, "TranscriptionId")

    # Step 4: Define a User-Defined Function (UDF) to find which PII entities appear in a given phrase.
    pii_struct = StructType([
        StructField("PiiText", StringType()), StructField("PiiCategory", StringType())
    ])

    @udf(returnType=ArrayType(pii_struct))
    def find_all_pii_in_phrase(phrase_text, pii_list):
        matches = []
        if not phrase_text or not pii_list: return None
        for pii_entity in pii_list:
            if pii_entity["PiiText"] in phrase_text:
                matches.append(pii_entity)
        return matches if matches else None

    # Step 5: Apply the UDF to find matches and explode the results.
    # This creates a separate row for each PII entity found within a phrase.
    pii_located_df = segments_with_pii_list_df.withColumn(
        "MatchedPii", find_all_pii_in_phrase(col("PhraseText"), col("PiiList"))
    ).where(col("MatchedPii").isNotNull()).withColumn("PiiMatch", F.explode(col("MatchedPii"))).select("AudioFileName", col("PiiMatch.PiiText").alias("PiiText"), "PhraseText", "OffsetInSeconds", "DurationInSeconds")

    # Step 6: Define a UDF to calculate the precise start/end time of the PII within the phrase.
    # This works by finding the PII's position and length relative to the entire phrase.
    @udf(returnType=StructType([
        StructField("start_ms", DoubleType(), False), StructField("end_ms", DoubleType(), False)
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
        except: return None

    # Step 7: Apply the timing UDF to get the final redaction timestamps in milliseconds.
    pii_timestamps_df = pii_located_df.withColumn(
        "timing", calculate_pii_timing(col("PiiText"), col("PhraseText"), col("OffsetInSeconds"), col("DurationInSeconds"))
    ).select(
        "AudioFileName", "PiiText", col("timing.start_ms").alias("start_ms"), col("timing.end_ms").alias("end_ms")
    ).dropna()

    # Step 8: Group by filename to get a final 'redaction plan' DataFrame.
    # This gives us one row per audio file, with a list of start/end times to redact.
    redaction_plan_df = pii_timestamps_df.groupBy("AudioFileName").agg(
        F.collect_list(F.struct("start_ms", "end_ms")).alias("redactions")
    )

    print("✅ Successfully created redaction plan:")
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

# > **Cell Purpose:** This cell iterates through the redaction plan created above. For each audio file, it loads the audio data, applies the redactions (silence or bleeps), and saves the new file.
# 
# ---
# ### **Cell 5: Main Redaction Loop**

# CELL ********************

# Check if the redaction plan was created successfully before proceeding
if redaction_plan_df:
    # Collect the plan from Spark into a list in the driver node's memory for processing
    redaction_plan = redaction_plan_df.collect()

    print(f"\nStarting audio redaction process for {len(redaction_plan)} files...")

    # Loop through each file in the redaction plan
    for row in redaction_plan:
        audio_filename = row["AudioFileName"]
        # Sort redactions by start time to process them in order
        redactions = sorted(row["redactions"], key=lambda x: x['start_ms'])

        # Define the full input and output file paths
        source_audio_path = os.path.join(LOCAL_PROCESSED_AUDIO_PATH, audio_filename)
        redacted_audio_path = os.path.join(LOCAL_REDACTED_AUDIO_PATH, f"REDACTED_{audio_filename}")

        print(f"\n🔄 Processing '{audio_filename}'...")

        if not os.path.exists(source_audio_path):
            print(f"  [WARN] Source audio file not found, skipping: {source_audio_path}")
            continue

        try:
            # Load the original audio file using pydub
            original_audio = AudioSegment.from_wav(source_audio_path)
            # Create an empty audio segment to build the redacted version
            redacted_audio = AudioSegment.empty()

            last_end_ms = 0

            # Iterate through the timestamps and build the new audio file chunk by chunk
            for redaction in redactions:
                start_ms = int(redaction['start_ms'])
                end_ms = int(redaction['end_ms'])

                # 1. Append the clean audio segment before the PII
                redacted_audio += original_audio[last_end_ms:start_ms]

                # 2. Generate and append the redaction segment (silence or bleep)
                duration_ms = end_ms - start_ms
                if duration_ms > 0:
                    if REDACTION_MODE == 'SILENCE':
                        redaction_segment = AudioSegment.silent(duration=duration_ms)
                    else: # 'BLEEP' mode
                        bleep = Sine(BLEEP_FREQUENCY).to_audio_segment(duration=duration_ms).apply_gain(-BLEEP_VOLUME_REDUCTION)
                        redaction_segment = bleep
                    redacted_audio += redaction_segment

                # 3. Update the pointer to the end of the current redaction
                last_end_ms = end_ms

            # 4. Append the rest of the audio after the last PII segment
            redacted_audio += original_audio[last_end_ms:]

            # 5. Export the final redacted audio file
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

# > **Cell Purpose:** This final cell lists the files in the output directory, allowing you to quickly confirm that the new, redacted audio files have been successfully created.
# 
# ---
# ### **Cell 6: Verification**

# CELL ********************

# This cell verifies that the redacted audio files were created in the output directory.
print(f"Verifying files in: {LOCAL_REDACTED_AUDIO_PATH}\n")

try:
    redacted_files = os.listdir(LOCAL_REDACTED_AUDIO_PATH)
    if not redacted_files:
        print("No files found in the redacted audio directory.")
    else:
        print(f"Found {len(redacted_files)} redacted files:")
        for filename in redacted_files:
            # We only want to see the redacted files, not other system files
            if filename.startswith("REDACTED_") and filename.endswith(".wav"):
                print(f"- {filename}")
except Exception as e:
    print(f"An error occurred while listing files: {e}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
