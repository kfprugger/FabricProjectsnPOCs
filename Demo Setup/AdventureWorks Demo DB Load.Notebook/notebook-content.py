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

# 
# 
# ### Author: Joey Brakefield
# ### Date: 18-Jun-2025
# ### Purpose: Create a quick AdventureWorks Demo database inside Microsoft Fabric using the public AdventureWorks DB
# 
# 
# MIT License
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
# 


# CELL ********************

# coding: utf-8

# ##  AdventureWorks OLTP Data Ingestion Notebook
# 
# This notebook automates the process of downloading the AdventureWorks OLTP sample data scripts and CSV files from GitHub, saving them to the Fabric Lakehouse, and converting the CSV data into managed Delta tables.
# 
# **Key Features:**
# * **Automated File Discovery**: Uses the GitHub API to find all files, so no hardcoded lists are needed.
# * **Idempotent Downloads**: Checks for existing files and skips them to avoid re-downloading.
# * **Robust Encoding Handling**: Attempts to decode files using multiple text encodings (UTF-8-SIG, UTF-16).
# * **Dynamic Schema Detection**: Automatically writes to the `dbo` schema if it exists in the Lakehouse, otherwise falls back to `default`.
# * **Comprehensive Logging**: Provides detailed progress updates and error messages.
# * **Metadata Summary**: Generates a summary table of all created tables with row and column counts.

# ### 1. Setup and Configuration
# 
# This section imports necessary libraries and defines the core configuration variables for the GitHub repository and the Lakehouse storage path.

# In[ ]:


import requests
import json
import base64
import re
from pyspark.sql.functions import col, lit, when
from pyspark.sql.utils import AnalysisException

# --- Configuration ---
# GitHub API URL for the AdventureWorks OLTP install script directory
GH_API_URL = "https://api.github.com/repos/microsoft/sql-server-samples/contents/samples/databases/adventure-works/oltp-install-script"

# Target location in Fabric Lakehouse for raw files
# The '/Files/' path is the default, user-facing location for unstructured data in a Lakehouse.
LAKEHOUSE_RAW_PATH = "Files/raw/adventureworks-oltp"
# Desired schema for the tables. The notebook will check if this schema exists.
TARGET_SCHEMA_NAME = "dbo"

# Currently attached Lakehouse. This is useful if you have multiple schemas to support and write to. :-)
LH_NAME = notebookutils.runtime.context['defaultLakehouseName']
LH_PREFIX = f"{LH_NAME}."

print(f"✅ Configuration loaded. Target Lakehouse path: '{LAKEHOUSE_RAW_PATH}'")


# ### 2. Download Files from GitHub
# 
# This step fetches the list of files from the GitHub repository, downloads each one, and saves it to the specified Lakehouse path using `mssparkutils`. It handles file existence checks and text decoding.

# In[ ]:


print("--- Starting File Download Process ---")

# Initialize tracking counters
download_summary = {"successful": 0, "skipped": 0, "failed": 0, "files": []}

# 1. Create the target directory if it doesn't exist
try:
    notebookutils.fs.mkdirs(LAKEHOUSE_RAW_PATH)
    print(f"Directory '{LAKEHOUSE_RAW_PATH}' ensured to exist.")
except Exception as e:
    # Handle cases where the path might already exist in a way that throws an error
    if "exists" not in str(e).lower():
        raise e

# 2. Fetch file list from GitHub API
try:
    response = requests.get(GH_API_URL)
    response.raise_for_status() # Raise an exception for bad status codes
    files_to_download = response.json()
    print(f"Found {len(files_to_download)} files in the GitHub repository.")
except requests.exceptions.RequestException as e:
    print(f"❌ Error fetching file list from GitHub: {e}")
    files_to_download = []

# 3. Download each file
for file_info in files_to_download:
    file_name = file_info['name']
    download_url = file_info['download_url']
    file_path = f"{LAKEHOUSE_RAW_PATH}/{file_name}"

    try:
        # Check if file already exists to make the process idempotent
        if notebookutils.fs.exists(file_path):
            print(f"⏭️ Skipping '{file_name}' (already exists).")
            download_summary["skipped"] += 1
            continue

        print(f"⬇️ Downloading '{file_name}'...")
        file_content_response = requests.get(download_url)
        file_content_response.raise_for_status()
        
        content_bytes = file_content_response.content
        file_size_kb = len(content_bytes) / 1024
        
        # Handle encoding with fallbacks
        decoded_content = None
        if file_name.endswith('.csv'): # Only attempt to decode text for CSVs
            try:
                # UTF-8 with BOM support is a good first choice
                decoded_content = content_bytes.decode('utf-8-sig')
                encoding_used = 'utf-8-sig'
            except UnicodeDecodeError:
                try:
                    # Fallback for files like *.sql that might be UTF-16
                    decoded_content = content_bytes.decode('utf-16')
                    encoding_used = 'utf-16'
                except UnicodeDecodeError:
                    print(f"⚠️ Could not decode '{file_name}' as text. Saving as raw binary with Base64 encoding.")
                    # Fallback for truly binary or un-decodable files
                    decoded_content = base64.b64encode(content_bytes).decode('utf-8')
                    file_path += ".b64" # Append extension to signify binary
                    encoding_used = 'base64'
        else: # For non-CSV files like .sql, assume text but with fallbacks
            try:
                decoded_content = content_bytes.decode('utf-8-sig')
                encoding_used = 'utf-8-sig'
            except UnicodeDecodeError:
                decoded_content = content_bytes.decode('utf-16')
                encoding_used = 'utf-16'

        # Save the file to the Lakehouse
        mssparkutils.fs.put(file_path, decoded_content, overwrite=True)
        print(f"   -> ✅ Saved to '{file_path}' (Size: {file_size_kb:.2f} KB, Encoding: {encoding_used})")
        download_summary["successful"] += 1
        download_summary["files"].append(file_path)

    except Exception as e:
        print(f"   -> ❌ FAILED to download or save '{file_name}'. Reason: {e}")
        download_summary["failed"] += 1

print("\n--- Download Summary ---")
print(f"Successful: {download_summary['successful']}")
print(f"Skipped:    {download_summary['skipped']}")
print(f"Failed:     {download_summary['failed']}")

# Preview content of a downloaded CSV file for verification
csv_files = [f for f in download_summary["files"] if f.endswith('.csv')]
if csv_files:
    print(f"\n--- Preview of '{csv_files[0]}' ---")
    try:
        preview_content = mssparkutils.fs.head(csv_files[0], 1024)
        print(preview_content)
    except Exception as e:
        print(f"Could not preview file: {e}")
else:
    print("\nNo new CSV files were downloaded to preview.")


# ### 3. Convert CSV Files to Delta Tables
# 
# This section scans the download directory for `.csv` files, reads them into Spark DataFrames, and saves them as permanent, managed Delta tables. It dynamically sets the table schema based on Lakehouse configuration.

# In[ ]:


print("\n--- Starting CSV to Delta Table Conversion ---")


# 1. Determine the target schema using a try-except block for robustness
schema_prefix = ""
try:
    # Attempt to use the schema. This will fail with an exception if it doesn't exist.
    spark.sql(f"USE {TARGET_SCHEMA_NAME}")
    # If the above line succeeds, set the prefix
    schema_prefix = f"{TARGET_SCHEMA_NAME}."
    print(f"✅ Target schema '{TARGET_SCHEMA_NAME}' exists and has been selected.")
except AnalysisException:
    # If the USE command fails, we know the schema doesn't exist. Use the default.
    schema_prefix = ""
    print(f"⚠️ Target schema '{TARGET_SCHEMA_NAME}' not found. Using 'default' schema.")
# 2. Get the list of CSV files to process from the Lakehouse directory
try:
    # notebookutils.fs.ls expects the fully qualified ABFSS path.
    # We construct it dynamically to ensure it works across all workspaces.
    workspace_id = notebookutils.runtime.context['currentWorkspaceId']
    lakehouse_id = notebookutils.runtime.context['defaultLakehouseId']
    full_abfss_path = f"abfss://{workspace_id}@onelake.dfs.fabric.microsoft.com/{lakehouse_id}/{LAKEHOUSE_RAW_PATH}"
    
    files_in_dir = notebookutils.fs.ls(full_abfss_path)
    csv_file_paths = [f.path for f in files_in_dir if f.name.endswith('.csv')]
    print(f"Found {len(csv_file_paths)} CSV files to process.")
except Exception as e:
    print(f"❌ Could not list files in '{LAKEHOUSE_RAW_PATH}'. Error: {e}")
    csv_file_paths = []









# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# # Understand the Schema
#  Read theinstawdb.sql file, extract the column names for each table, and apply them to the DataFrames before saving them as Delta tables.

# CELL ********************

import re

print("--- Parsing Schemas, Delimiters, and Encodings from SQL Script ---")

# Path to the downloaded SQL script
sql_script_path = f"{LAKEHOUSE_RAW_PATH}/instawdb.sql"
sql_content = mssparkutils.fs.head(sql_script_path, 1024*1024*10)

# Dictionaries to store all our parsed metadata
table_schemas = {}
table_delimiters = {}
table_encodings = {}
table_row_terminators = {} 

# --- STEP 1: Parse ALL table schemas first ---
create_table_regex = re.compile(r'CREATE TABLE \[(\w+)\]\.\[(\w+)\]\s*\((.*?)\)\s*(?:ON\s*\[\w+\])?\s*;', re.DOTALL | re.IGNORECASE)

print("\n--- Parsing Schemas ---")
for match in create_table_regex.finditer(sql_content):
    schema_name = match.group(1)
    table_name = match.group(2)
    columns_block = match.group(3)
    
    # --- FINAL FIX ---
    # This regex now correctly finds only column names by looking for bracketed text at the start of each line.
    column_names = re.findall(r'^\s*\[([^]]+)]', columns_block, re.MULTILINE)
    
    if column_names:
        table_schemas[table_name] = column_names
        # This logging is optional now but good for verification
        # print(f"  [✔] Found schema for: {table_name} ({len(column_names)} columns)")

print(f"\n✅ Parsed schemas for {len(table_schemas)} tables.")


# --- STEP 2: Parse BULK INSERT info for each table found ---
bulk_insert_block_regex = re.compile(r"BULK INSERT.*?\[({table_name})].*?WITH\s*\((.*?)\);", re.DOTALL | re.IGNORECASE)
field_terminator_regex = re.compile(r"FIELDTERMINATOR\s*=\s*'([^']+)'", re.IGNORECASE)
row_terminator_regex = re.compile(r"ROWTERMINATOR\s*=\s*'([^']+)'", re.IGNORECASE)
data_file_type_regex = re.compile(r"DATAFILETYPE\s*=\s*'([^']+)'", re.IGNORECASE)

# print("\n--- Parsing Delimiters & Encodings ---") # Optional logging
found_delimiter_info = []
for table_name in table_schemas.keys():
    block_finder = re.compile(bulk_insert_block_regex.pattern.format(table_name=re.escape(table_name)), re.DOTALL | re.IGNORECASE)
    block_match = block_finder.search(sql_content)

    if block_match:
        with_block = block_match.group(2)
        field_match = field_terminator_regex.search(with_block)
        row_match = row_terminator_regex.search(with_block)
        type_match = data_file_type_regex.search(with_block)
        
        if field_match and row_match and type_match:
            found_delimiter_info.append(table_name)
            table_delimiters[table_name] = field_match.group(1).replace('\\t', '\t')
            table_row_terminators[table_name] = row_match.group(1).replace('\\n', '\n')
            table_encodings[table_name] = 'UTF-16' if type_match.group(1).lower() == 'widechar' else 'UTF-8'
            # print(f"  [✔] Found delimiter info for: {table_name}") # Optional logging

print(f"✅ Parsed delimiter info for {len(found_delimiter_info)} tables.")

# --- STEP 3: LOGGING - Identify missing tables ---
all_tables_with_schema = set(table_schemas.keys())
tables_without_delimiter_info = all_tables_with_schema - set(found_delimiter_info)

if tables_without_delimiter_info:
    print(f"\n⚠️ The following {len(tables_without_delimiter_info)} tables have a schema but no specific BULK INSERT info was found.")
    print("   (The script will use default CSV settings for these: comma-delimited, UTF-8)")
    print("   " + ", ".join(sorted(list(tables_without_delimiter_info))))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# # Process each AdventureWorks CSV found in the Lakehouse

# CELL ********************

from pyspark.sql.functions import col, split
import re

# --- Helper function to clean column names for Delta compatibility ---
def sanitize_column_name(name):
    # Delta doesn't like spaces or certain characters in column names
    return name.replace(' ', '_')

# --- Safety check: Ensure required variables are available ---
if 'csv_file_paths' not in locals():
    print("❌ ERROR: csv_file_paths not found. Please run the file download cell first.")
    csv_file_paths = []

if 'table_schemas' not in locals():
    print("❌ ERROR: table_schemas not found. Please run the schema parsing cell first.")
    table_schemas = {}

if 'schema_prefix' not in locals():
    print("❌ ERROR: schema_prefix not found. Please run the schema detection cell first.")
    schema_prefix = ""

# Initialize delimiter and encoding dictionaries if not available
if 'table_delimiters' not in locals():
    print("⚠️ WARNING: table_delimiters not found. Using defaults.")
    table_delimiters = {}

if 'table_encodings' not in locals():
    print("⚠️ WARNING: table_encodings not found. Using defaults.")
    table_encodings = {}

if 'table_row_terminators' not in locals():
    print("⚠️ WARNING: table_row_terminators not found. Using defaults.")
    table_row_terminators = {}

print(f"✅ Found {len(csv_file_paths)} CSV files and {len(table_schemas)} table schemas to process.")

# --- CORRECTED Manual overrides based on diagnostic findings ---
manual_overrides = {
    "CountryRegion":          {"delimiter": "\t", "quote": "", "has_header": False, "encoding": "UTF-8"},  # TAB delimited, no header, UTF-8
    "CountryRegionCurrency":  {"delimiter": "\t", "quote": "", "has_header": False, "encoding": "UTF-8"},  # TAB delimited, no header, UTF-8
    "ProductDescription":     {"delimiter": "\t", "quote": "", "has_header": False, "encoding": "UTF-8"},  # TAB delimited, no header
    "StateProvince":          {"delimiter": "\t", "quote": "", "has_header": False, "encoding": "UTF-8"},  # TAB delimited, no header
    "WorkOrderRouting":       {"delimiter": "\t", "quote": "", "has_header": False, "encoding": "UTF-8"},  # TAB delimited, no header
    "ProductReview":          {"delimiter": "\t", "quote": "", "has_header": False, "encoding": "UTF-8", "multiline": True},  # TAB delimited, no header, multiline content
    "Employee":               {"delimiter": "|~", "row_terminator": "&|\\n"},
    "Person":                 {"delimiter": "|~", "row_terminator": "&|\\n"}
}

# 3. Process each CSV file - PROCESSING ALL FILES
table_metadata = []
print(f"\n🔄 Starting to process ALL CSV files...")

# Process all CSV files
test_files = [f for f in csv_file_paths if f.endswith('.csv')]
print(f"Processing {len(test_files)} files: {[f.split('/')[-1] for f in test_files[:5]]}{'...' if len(test_files) > 5 else ''}")

for file_path in test_files:
    file_name = file_path.split('/')[-1]
    table_name = file_name.replace('.csv', '')
    
    if table_name not in table_schemas:
        if "TOREMOVE" not in table_name and "org" not in table_name: 
             print(f"❓ No schema found for '{table_name}', skipping.")
        continue

    full_table_name = f"{schema_prefix}{table_name}"
    print(f"\n🔄 Processing '{file_name}' -> Table '{full_table_name}'...")

    # Enhanced logging for problematic files
    is_problem_file = table_name in ["CountryRegion", "CountryRegionCurrency", "ProductDescription", "StateProvince", "WorkOrderRouting", "ProductReview"]
    if is_problem_file:
        print(f"   -> Using enhanced parsing for {table_name}")

    try:
        # Get schema and parsing parameters
        original_schema = table_schemas.get(table_name)
        if not original_schema:
            print(f"   -> ❌ ERROR: No schema found for table '{table_name}'")
            continue
            
        delimiter = table_delimiters.get(table_name, ',') 
        encoding = table_encodings.get(table_name, 'UTF-8')
        row_terminator = table_row_terminators.get(table_name)
        
        final_schema = [sanitize_column_name(c) for c in original_schema]
        
        # Apply manual overrides
        has_header = True  # Default assumption
        if table_name in manual_overrides:
            override = manual_overrides[table_name]
            if "delimiter" in override:
                old_delimiter = delimiter
                delimiter = override["delimiter"]
                print(f"   -> INFO: Applied manual override for delimiter: '{repr(old_delimiter)}' -> '{repr(delimiter)}'")
            if "encoding" in override:
                old_encoding = encoding
                encoding = override["encoding"]
                print(f"   -> INFO: Applied manual override for encoding: '{old_encoding}' -> '{encoding}'")
            if "row_terminator" in override:
                row_terminator = override["row_terminator"]
                print(f"   -> INFO: Applied manual override for row_terminator.")
            if override.get("has_identity_col"):
                print(f"   -> INFO: Applied schema override, removing IDENTITY column '{final_schema[0]}'.")
                final_schema = final_schema[1:]
            if "has_header" in override:
                has_header = override["has_header"]
                print(f"   -> INFO: File has header: {has_header}")
        
        print(f"   -> LOG: Using delimiter: '{repr(delimiter)}', Encoding: '{encoding}', Has header: {has_header}")
        print(f"   -> LOG: Expected {len(final_schema)} columns")
        
        final_df = None
        df = None

        # Use simplified text reader for files with special row terminators
        if row_terminator and ('&|' in row_terminator or '&|' in str(row_terminator)):
            print(f"   -> Using simplified text reader for special delimiters...")
            try:
                raw_text_df = spark.read.option("encoding", encoding).text(file_path)
                escaped_delimiter = delimiter.replace("|", "\\|").replace("+", "\\+")
                print(f"   -> LOG: Escaped delimiter for Spark SQL split: '{escaped_delimiter}'")
                
                final_df = raw_text_df.select(
                    split(col("value"), escaped_delimiter).alias("cols")
                ).select(
                    *[col("cols").getItem(i).alias(final_schema[i]) for i in range(len(final_schema))]
                )
                print(f"   -> ✅ Successfully parsed with text reader, got {len(final_df.columns)} columns")
            except Exception as text_error:
                print(f"   -> ❌ Text reader failed: {text_error}")
                final_df = None

        else: # Standard CSV files
            print(f"   -> Using standard CSV reader...")
            try:
                quote_char = manual_overrides.get(table_name, {}).get("quote", '"')
                
                # Build CSV reader options
                csv_options = {
                    "header": str(has_header).lower(),
                    "encoding": encoding,
                    "delimiter": delimiter,
                    "quote": quote_char
                }
                
                # Handle multiline content (for ProductReview)
                if manual_overrides.get(table_name, {}).get("multiline", False):
                    csv_options["multiline"] = "true"
                    print(f"   -> INFO: Enabled multiline support for complex content")
                
                df = spark.read.options(**csv_options).csv(file_path)
                
                print(f"   -> CSV reader loaded {len(df.columns)} columns, expected {len(final_schema)}")
                
                # Check column count match
                if len(df.columns) == len(final_schema):
                    final_df = df.toDF(*final_schema)
                    print(f"   -> ✅ Successfully applied schema to DataFrame")
                else:
                    print(f"   -> ❌ Column count mismatch: CSV has {len(df.columns)}, Schema expects {len(final_schema)}")
                    final_df = None
                    
            except Exception as csv_error:
                print(f"   -> ❌ CSV reader failed: {str(csv_error)[:200]}...")
                final_df = None

        # Final validation and table creation
        if final_df is None:
            actual_cols = len(df.columns) if df is not None else 'N/A'
            expected_cols = len(final_schema)
            error_msg = f'Failed (Column Count Mismatch: CSV has {actual_cols}, Schema expects {expected_cols})'
            print(f"   -> ❌ {error_msg}")
            table_metadata.append({'table_name': full_table_name, 'status': error_msg})
            continue

        # Write the table to Delta
        try:
            final_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(full_table_name)
            row_count = final_df.count()
            column_count = len(final_df.columns)
            table_metadata.append({'table_name': full_table_name, 'row_count': row_count, 'column_count': column_count, 'status': 'Success'})
            
            print(f"   -> ✅ Successfully created table '{full_table_name}' with {row_count} rows and {column_count} columns.")
        except Exception as write_error:
            error_msg = f'Failed to write Delta table: {str(write_error)[:200]}'
            print(f"   -> ❌ {error_msg}")
            table_metadata.append({'table_name': full_table_name, 'status': error_msg})
            continue

    except Exception as e:
        error_message = str(e)[:200]
        table_metadata.append({'table_name': full_table_name, 'status': f'Failed: {error_message}'})
        print(f"   -> ❌ FAILED to create table for '{file_name}'. Reason: {error_message}")

print(f"\n\n--- Processing Complete (Processed {len(test_files)} files) ---")

# Display results
if table_metadata:
    print("\n--- Results Summary ---")
    for item in table_metadata:
        status = item['status']
        name = item['table_name']
        if status == 'Success':
            print(f"✅ {name}: {item['row_count']} rows, {item['column_count']} columns")
        else:
            print(f"❌ {name}: {status}")
else:
    print("No tables were processed.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ### 5. Ready-to-Use SQL Queries
# 
# You can now query the newly created tables directly using SQL. The queries below are dynamically adjusted to use the `dbo` schema if it was detected.

# This cell uses the %%sql magic command, which is ideal for running SQL in a Fabric notebook.
# The table names are constructed using the same logic as the ingestion process.
# Just run this cell to see results from your new tables.
# Note: Python variables can be referenced in %%sql cells using curly braces {}.

# Simple query to check some of the tables
employee_table = f"{LH_PREFIX}{schema_prefix}employee"
sales_order_detail_table = f"{LH_PREFIX}{schema_prefix}salesorderdetail"

print(f"Querying table: {employee_table}")
display(spark.sql(f"SELECT NationalIDNumber, JobTitle, MaritalStatus, Gender, HireDate FROM {employee_table} LIMIT 10"))

print(f"\nQuerying table: {sales_order_detail_table}")
display(spark.sql(f"SELECT SalesOrderID, ProductID, OrderQty, UnitPrice, LineTotal FROM {sales_order_detail_table} LIMIT 10"))

# ### 6. Business Intelligence (BI) Query Examples
# 
# Here are more complex examples demonstrating how to join tables for sales analysis.

# This cell also uses the %%sql magic command for BI-style analysis.

# Example 1: Find the top 10 products by total sales quantity
product_table = f"{LH_PREFIX}{schema_prefix}product"
sales_detail_table = f"{LH_PREFIX}{schema_prefix}salesorderdetail"

top_products_query = f"""
SELECT
    p.Name AS ProductName,
    SUM(sod.OrderQty) AS TotalQuantitySold
FROM {sales_detail_table} sod
JOIN {product_table} p 
    ON sod.ProductID = p.ProductID
GROUP BY p.Name
ORDER BY TotalQuantitySold DESC
LIMIT 10
"""

print("Top 10 Products by Quantity Sold:")
display(spark.sql(top_products_query))

# Example 2: Sales performance by territory
sales_order_header_table = f"{LH_PREFIX}{schema_prefix}salesorderheader"
sales_territory_table = f"{LH_PREFIX}{schema_prefix}salesterritory"

territory_sales_query = f"""
SELECT
    st.Name AS Territory,
    COUNT(soh.SalesOrderID) AS OrderCount,
    SUM(soh.TotalDue) AS TotalSales,
    AVG(soh.TotalDue) AS AvgOrderValue
FROM {sales_order_header_table} soh
JOIN {sales_territory_table} st 
    ON soh.TerritoryID = st.TerritoryID
GROUP BY st.Name
ORDER BY TotalSales DESC
"""

print("\nSales Performance by Territory:")
display(spark.sql(territory_sales_query)) 
#     ON sod.ProductID = p.ProductID
# GROUP BY
#     p.Name
# ORDER BY
#     TotalQuantitySold DESC
# LIMIT 10
# """
# print("--- Top 10 Products by Sales Quantity ---")
# display(spark.sql(top_products_query))

# # Example 2: List employees and their department information
# employee_table = f"{LH_PREFIX}{schema_prefix}HumanResources_Employee"
# department_table = f"{LH_PREFIX}{schema_prefix}HumanResources_Department"
# employee_dept_history_table = f"{LH_PREFIX}{schema_prefix}HumanResources_EmployeeDepartmentHistory"

# employee_department_query = f"""
# WITH CurrentDepartments AS (
#     -- Get the most recent department for each employee
#     SELECT *, ROW_NUMBER() OVER(PARTITION BY BusinessEntityID ORDER BY StartDate DESC) as rn
#     FROM {employee_dept_history_table}
# )
# SELECT 
#     e.BusinessEntityID,
#     e.JobTitle,
#     d.Name as DepartmentName,
#     d.GroupName
# FROM {employee_table} e
# JOIN CurrentDepartments cdh
#     ON e.BusinessEntityID = cdh.BusinessEntityID AND cdh.rn = 1 -- only the latest record
# JOIN {department_table} d
#     ON cdh.DepartmentID = d.DepartmentID
# ORDER BY 
#     d.GroupName, d.Name, e.BusinessEntityID
# LIMIT 20
# """

# print("\n--- Employee Department Listing ---")
# display(spark.sql(employee_department_query))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
