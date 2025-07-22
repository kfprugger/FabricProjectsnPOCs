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

# # This notebook cell searches for a specific Semantic Model within the current Microsoft Fabric workspace and prints its details if found.
# 
# ---
# ### What the Code Does
# 
# The script's main purpose is to verify the existence of a Semantic Model named "**redaction-semantic-model**" in the Fabric workspace where the notebook is running.
# 
# * ✅ If the model is found, the script prints a **success message** with its Display Name, ID, and creation timestamp.
# * ℹ️ If the model is **not found**, it prints an informational message.
# * ❌ If any other error occurs, it prints an **error message**.
# 
# ---
# ### How It Works
# 
# 1.  **Install Library**: The first line, `%pip install semantic-link-labs --quiet`, installs the Python library (`semantic-link-labs`) needed to interact with Fabric items like Semantic Models.
# 
# 2.  **Get Workspace Context**: It uses `fabric.get_workspace_id()` to identify the current workspace.
# 
# 3.  **List Semantic Models**: The function `fabric.list_datasets()` retrieves a list of all Semantic Models in the workspace and loads them into a **pandas DataFrame**.
# 
# 4.  **Find the Target Model**: The code then filters this DataFrame to find the row where the 'Dataset Name' column matches the target name.
# 
# 5.  **Display Results**: Based on whether the filtering found a match, it prints the appropriate success, info, or error message to the output.


# CELL ********************

%pip install semantic-link-labs --quiet

import sempy.fabric as fabric
import pandas as pd

# --- Parameters ---
target_model_name = "redaction-semantic-model" 

# Get workspace context using a sempy function
# This gets the ID of the workspace where the notebook is running.
workspace_id = fabric.get_workspace_id()
print(f"Checking in Workspace: {workspace_id}")
print(f"Looking for Semantic Model: '{target_model_name}'...")


try:
    # list_datasets() runs in the context of the current workspace
    df_datasets = fabric.list_datasets()

    # Filter the DataFrame to find our specific model by its display name
    found_model_df = df_datasets[df_datasets['Dataset Name'] == target_model_name]

    # --- 3. Process the Response ---
    if not found_model_df.empty:
        # Extract the details from the first row of the filtered DataFrame
        found_model = found_model_df.iloc[0]
        model_id = found_model['Dataset ID']
        
        print(f"\n✅ SUCCESS: Semantic Model found!")
        print(f"   - Display Name: {found_model['Dataset Name']}")
        print(f"   - ID: {model_id}")
        print(f"   - Created Timestamp: {found_model['Created Timestamp']}")
        # print(f"   - Last Update: {found_model['Last Update']}")

    else:
        print(f"\nℹ️ INFO: Semantic Model '{target_model_name}' was not found in this workspace.")

except Exception as e:
    print(f"\n❌ ERROR: An unexpected error occurred: {e}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
