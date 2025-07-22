# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "4a34fe1b-5db9-4a7e-abaa-00229c9e0a74",
# META       "default_lakehouse_name": "clientPOCsDemoLH",
# META       "default_lakehouse_workspace_id": "4414d1c5-d566-4308-b8d1-a275b09a7cf2",
# META       "known_lakehouses": [
# META         {
# META           "id": "4a34fe1b-5db9-4a7e-abaa-00229c9e0a74"
# META         }
# META       ]
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Transform and enrich data seamlessly with AI functions (Preview)
# 
# [Transform and enrich data seamlessly with AI functions - Microsoft Fabric | Microsoft Learn](https://learn.microsoft.com/en-us/fabric/data-science/ai-functions/overview?tabs=pandas#getting-started-with-ai-functionshttps://learn.microsoft.com/en-us/fabric/data-science/ai-functions/overview?tabs=pandas#getting-started-with-ai-functions)
# 
# Use of the AI functions library in a Fabric notebook currently requires certain custom packages. The following code installs and imports those packages. Afterward, you can use AI functions with pandas or PySpark, depending on your preference.

# CELL ********************

# Install fixed version of packages
%pip install -q --force-reinstall openai==1.30 httpx==0.27.0

# Install latest version of SynapseML-core
%pip install -q --force-reinstall https://mmlspark.blob.core.windows.net/pip/1.0.11-spark3.5/synapseml_core-1.0.11.dev1-py2.py3-none-any.whl

# Install SynapseML-Internal .whl with AI functions library from blob storage:
%pip install -q --force-reinstall https://mmlspark.blob.core.windows.net/pip/1.0.11.1-spark3.5/synapseml_internal-1.0.11.1.dev1-py2.py3-none-any.whl

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Required imports
import synapse.ml.aifunc as aifunc
import pandas as pd
import openai

# Optional import for progress bars
from tqdm.auto import tqdm
tqdm.pandas()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ### Calculate similarity with `ai.similarity`
# 
# The `ai.similarity` function invokes AI to compare input text values with a single common text value, or with pairwise text values in another column. The output similarity scores are relative, and they can range from **-1** (opposites) to **1** (identical). A score of **0** indicates that the values are completely unrelated in meaning. For more detailed instructions about the use of `ai.similarity`, visit [this article](https://learn.microsoft.com/en-us/fabric/data-science/ai-functions/similarity).

# CELL ********************

# This code uses AI. Always review output for mistakes. 
# Read terms: https://azure.microsoft.com/support/legal/preview-supplemental-terms/

# df = spark.read.csv("Jeremy's awesome path...")

df = pd.DataFrame([ 
        ("Bill Gates", "Microsoft"), 
        ("Satya Nadella", "Toyota"), 
        ("Joan of Arc", "Nike"),
        ("Joey Brakefield", "Nissan")
    ], columns=["names", "companies"])
    
df["similarity"] = df["companies"].ai.similarity(df["names"])
display(df)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ### Categorize text with `ai.classify`
# 
# The `ai.classify` function invokes AI to categorize input text according to custom labels you choose. For more information about the use of `ai.classify`, visit [this article](https://learn.microsoft.com/en-us/fabric/data-science/ai-functions/classify).

# CELL ********************

#### ATTENTION: AI-generated code can include errors or operations you didn't intend. Review the code in this cell carefully before running it.

import pandas as pd

# This is the DataFrame from your example.
df = pd.DataFrame([
        "This duvet, lovingly hand-crafted from all-natural fabric, is perfect for a good night's sleep.",
        "Tired of friends judging your baking? With these handy-dandy measuring cups, you'll create culinary delights.",
        "Enjoy this *BRAND NEW CAR!* A compact SUV perfect for the professional commuter!",
        "Thanks for calling Cleveland Clinic. I see you are calling about your recent visit. How can I help?",
        "I'm really tired of measuring my flour for baking. How do I change this? I'm lazy",
    ], columns=["descriptions"])

# This is the classification step from your example.
df["category"] = df['descriptions'].ai.classify("kitchen", "bedroom", "garage", "other")

# Start Spark session
from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()

# Convert the pandas DataFrame to a Spark DataFrame
spark_df = spark.createDataFrame(df)

# Write Spark DataFrame to the Lakehouse table in the dbo schema
spark_df.write.mode("overwrite").format("delta").saveAsTable("aiwork.classify")

# To verify, you can read the data back from the lakehouse into a new Spark DataFrame
df_read = spark.read.table("dbo.classify")
display(df_read)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ###  Detect sentiment with `ai.analyze_sentiment`
# 
# The `ai.analyze_sentiment` function invokes AI to identify whether the emotional state expressed by input text is positive, negative, mixed, or neutral. If AI can't make this determination, the output is left blank. For more detailed instructions about the use of `ai.analyze_sentiment`, visit [this article](https://learn.microsoft.com/en-us/fabric/data-science/ai-functions/analyze-sentiment).

# CELL ********************

# This code uses AI. Always review output for mistakes. 
# Read terms: https://azure.microsoft.com/support/legal/preview-supplemental-terms/

df = pd.DataFrame([
        "The cleaning spray permanently stained my beautiful kitchen counter. Never again!",
        "I used this sunscreen on my vacation to Florida, and I didn't get burned at all. Would recommend.",
        "I'm torn about this speaker system. The sound was high quality, though it didn't connect to my roommate's phone.",
        "The umbrella is OK, I guess."
    ], columns=["reviews"])

df["sentiment"] = df["reviews"].ai.analyze_sentiment()
display(df)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ### Extract entities with `ai.extract`
# 
# The `ai.extract` function invokes AI to scan input text and extract specific types of information designated by labels you choose—for example, locations or names. For more detailed instructions about the use of `ai.extract`, visit [this article](https://learn.microsoft.com/en-us/fabric/data-science/ai-functions/extract).

# CELL ********************

# This code uses AI. Always review output for mistakes. 
# Read terms: https://azure.microsoft.com/support/legal/preview-supplemental-terms/

df = pd.DataFrame([
        "MJ Lee lives in Tuscon, AZ, and works as a software engineer for Microsoft.",
        "Kris Turner, a nurse at NYU Langone, is a resident of Jersey City, New Jersey."
    ], columns=["descriptions"])

df_entities = df["descriptions"].ai.extract("name", "profession", "city")
display(df_entities)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ###  Fix grammar with `ai.fix_grammar`
# 
# The `ai.fix_grammar` function invokes AI to correct the spelling, grammar, and punctuation of input text. For more detailed instructions about the use of `ai.fix_grammar`, visit [this article](https://learn.microsoft.com/en-us/fabric/data-science/ai-functions/fix-grammar).

# CELL ********************

# This code uses AI. Always review output for mistakes. 
# Read terms: https://azure.microsoft.com/support/legal/preview-supplemental-terms/

df = pd.DataFrame([
        "There are an error here.",
        "She and me go weigh back. We used to hang out every weeks.",
        "The big picture are right, but you're details is all wrong."
    ], columns=["text"])

df["corrections"] = df["text"].ai.fix_grammar()
display(df)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ### Summarize text with `ai.summarize`
# 
# The `ai.summarize` function invokes AI to generate summaries of input text (either values from a single column of a DataFrame, or row values across all the columns). For more detailed instructions about the use of `ai.summarize`, visit [this dedicated article](https://learn.microsoft.com/en-us/fabric/data-science/ai-functions/summarize).

# CELL ********************

# This code uses AI. Always review output for mistakes. 
# Read terms: https://azure.microsoft.com/support/legal/preview-supplemental-terms/

df= pd.DataFrame([
        ("Microsoft Teams", "2017",
        """
        The ultimate messaging app for your organization—a workspace for real-time 
        collaboration and communication, meetings, file and app sharing, and even the 
        occasional emoji! All in one place, all in the open, all accessible to everyone.
        """),
        ("Microsoft Fabric", "2023",
        """
        An enterprise-ready, end-to-end analytics platform that unifies data movement, 
        data processing, ingestion, transformation, and report building into a seamless, 
        user-friendly SaaS experience. Transform raw data into actionable insights.
        """)
    ], columns=["product", "release_year", "description"])

df["summaries"] = df["description"].ai.summarize()
display(df)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ###  Translate text with `ai.translate`
# 
# The `ai.translate` function invokes AI to translate input text to a new language of your choice. For more detailed instructions about the use of `ai.translate`, visit [this article](https://learn.microsoft.com/en-us/fabric/data-science/ai-functions/translate).

# CELL ********************

# This code uses AI. Always review output for mistakes. 
# Read terms: https://azure.microsoft.com/support/legal/preview-supplemental-terms/

df = pd.DataFrame([
        "Hello! How are you doing today?", 
        "Tell me what you'd like to know, and I'll do my best to help.", 
        "The only thing we have to fear is fear itself."
    ], columns=["text"])

df["translations"] = df["text"].ai.translate("french")
display(df)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ### Answer custom user prompts with `ai.generate_response`
# 
# The `ai.generate_response` function invokes AI to generate custom text based on your own instructions. For more detailed instructions about the use of `ai.generate_response`, visit [this article](https://learn.microsoft.com/en-us/fabric/data-science/ai-functions/generate-response).

# CELL ********************

# This code uses AI. Always review output for mistakes. 
# Read terms: https://azure.microsoft.com/support/legal/preview-supplemental-terms/

df = pd.DataFrame([
        ("Scarves"),
        ("Snow pants"),
        ("Ski goggles")
    ], columns=["product"])

df["response"] = df.ai.generate_response("Write a short, punchy email subject line for a winter sale.")
display(df)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
