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

# CELL ********************

# 1. CONFIGURE: Set the name of your Lakehouse
# In Fabric, the Lakehouse name serves as the database name.
LAKEHOUSE_NAME = "bronze_aoai_lh"

print(f"--- Starting truncate process for all tables in Lakehouse: '{LAKEHOUSE_NAME}' ---")
print("⚠️ WARNING: This is a destructive operation and will delete all rows from all tables.")

try:
    # 2. ENUMERATE: Get a list of all tables in the specified Lakehouse
    tables_list = spark.catalog.listTables(LAKEHOUSE_NAME)

    # Filter for only managed tables, ignoring any views
    managed_tables = [table for table in tables_list if table.tableType == 'MANAGED']

    if not managed_tables:
        print(f"\nNo managed tables found in '{LAKEHOUSE_NAME}'. Nothing to do.")
    else:
        print(f"\nFound {len(managed_tables)} tables to truncate.")
        
        # 3. LOOP and TRUNCATE: Iterate through each table and delete all its rows
        for table in managed_tables:
            full_table_name = f"`{table.database}`.`{table.name}`"
            print(f"  > Truncating table: {full_table_name}...")
            
            try:
                spark.sql(f"TRUNCATE TABLE {full_table_name}")
                print(f"    ✅ Success.")
            except Exception as e:
                print(f"    ❌ FAILED to truncate {full_table_name}. Error: {e}")

except Exception as e:
    print(f"\n❌ An error occurred trying to list tables for Lakehouse '{LAKEHOUSE_NAME}'.")
    print(f"Please ensure the Lakehouse name is correct. Error: {e}")

print(f"\n--- Process complete. ---")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
