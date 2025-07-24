# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# CELL ********************

import datetime
import time
from pyspark.sql import SparkSession
from pyspark.sql.functions import current_timestamp, current_timezone

def get_os_and_spark_time_info():
    """
    Initializes a Spark session and prints time information from both the
    local OS and the Spark session's context.
    """
    # --- 1. Get Local OS Time Information (Driver Node) ---
    print("--- 1. Local Operating System (Driver) Clock Information ---")
    try:
        # Get current local time from the OS
        os_now = datetime.datetime.now()
        formatted_os_time = os_now.strftime("%A, %B %d, %Y at %I:%M:%S %p")

        # Get current timezone setting from the OS
        is_dst = time.localtime().tm_isdst
        os_timezone = time.tzname[is_dst]

        print(f"OS Local Time:    {formatted_os_time}")
        print(f"OS Timezone:      {os_timezone}")
        print(f"DST in effect:    {'Yes' if is_dst > 0 else 'No'}")

    except Exception as e:
        print(f"Could not retrieve OS time information: {e}")


    print("\n--- 2. Spark Session Clock Information ---")
    spark = None # Initialize spark variable to None
    try:
        # --- 2. Initialize Spark Session ---
        # This creates a local Spark session. In a real cluster environment,
        # this would connect to the cluster manager.
        spark = SparkSession.builder \
            .appName("Timezone Info") \
            .getOrCreate()

        # --- 3. Get Time Information from Spark's Context ---
        # We execute a Spark action to get the current timestamp and timezone
        # as seen by the Spark engine. This will reflect the timezone
        # configuration of the Spark cluster (or the local machine if running locally).
        
        # Create a DataFrame with one row to run the functions
        time_df = spark.sql("SELECT current_timestamp() as spark_time, current_timezone() as spark_timezone")
        
        # Collect the results back to the driver
        spark_time_info = time_df.first()

        if spark_time_info:
            spark_time = spark_time_info["spark_time"]
            spark_timezone = spark_time_info["spark_timezone"]
            
            # Format the Spark timestamp for readability
            formatted_spark_time = spark_time.strftime("%A, %B %d, %Y at %I:%M:%S %p")

            print(f"Spark Session Time: {formatted_spark_time}")
            print(f"Spark Session Timezone: {spark_timezone}")
            print(f"Spark Config (spark.sql.session.timeZone): {spark.conf.get('spark.sql.session.timeZone', 'Not Set (Using System Default)')}")

        else:
            print("Could not retrieve time information from Spark.")

    except Exception as e:
        print(f"An error occurred with Spark: {e}")

    finally:
        # --- 4. Stop the Spark Session ---
        # It's important to stop the session to release resources.
        if spark:
            spark.stop()
            print("\nSpark session stopped.")


# Run the function
if __name__ == "__main__":
    get_os_and_spark_time_info()


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
