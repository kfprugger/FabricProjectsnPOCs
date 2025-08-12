# ![redaction-icon](/FabricProjectsnPOCs/imgs/redaction-icon.png) Audio Redaction in Microsoft Fabric

> [!NOTE]
> This project is a Proof of Concept demonstrating how to use **Azure AI Services** within a **Microsoft Fabric Notebook** to automatically redact Personally Identifiable Information (PII) from audio files stored in a Lakehouse.

This solution leverages the compute power of Fabric along with Azure's **Speech Service**, **Language Service**, and **OpenAI Service** to create a robust redaction pipeline. The entire workflow runs within the Fabric ecosystem, reading source audio from a Lakehouse and writing the redacted output back to it. 

There are two notebooks in this project: one to transcribe and idenitify PHI/PII timestamps in the transcription and a second to either "bleep" or silence the audio when PHI/PII is mentioned based on the timestamps from the first notebook. 

## Workflow Diagram

![Fabric workflow diagram](/FabricProjectsnPOCs/imgs/Call%20Center%20Project.png) 
---

## ✨ Features

* **Audio Transcription**: Converts speech in an audio file into text with detailed word-level timestamps using Azure Speech Service.
* **PII Detection**: Analyzes the transcribed text to identify and categorize PII entities (e.g., names, phone numbers, addresses) using Azure Language Service.
* **Timestamp Calculation**: Maps the identified PII entities back to their exact start and end times in the original audio file.
* **Audio Muting**: Programmatically silences the specific segments of the audio that contain PII.
* **Lakehouse Integration**: Reads source audio and writes redacted audio directly within a Fabric Lakehouse.

---

## 🔧 Prerequisites

Before you begin, ensure you have the following:

1.  **Microsoft Fabric Capacity**: An active Fabric capacity (F64, P1, or a Fabric trial) that supports running notebooks.
2.  **Fabric Workspace**: A workspace where you can create a Lakehouse and Notebooks.
3.  **Azure AI Services**: You must create the following three resources in the Azure portal:
    * A **Speech Service** resource.
    * A **Language Service** resource.
    * An **Azure OpenAI** resource (with a model like `gpt-3.5-turbo` or `gpt-4` deployed).
    * Keep the **Key** and **Endpoint/Region** for these services handy.
4.  **Sample Audio**: A `.wav` audio file containing speech.

    > 💡 [TIP]
    > If you don't have sample audio files with Protected Health Information (PHI), you can easily generate them using the **[PHI Call Center Generator](https://github.com/kfprugger/cc-proj)** project.

---

## ⚙️ Setup & Usage in Fabric

Follow these steps to deploy and run the solution in your Fabric workspace.

### 1. Set up the Lakehouse

1.  In your Fabric workspace, create a new **Lakehouse**.
2.  Once created, select your Lakehouse and navigate to the `Files` section.
3.  Create these new folders in your Lakehouse: `audio-files`, `sdk-logs`, `failed`, `processed-audio`, `transcripts` and `redacted-audio`.
4.  Upload your sample `.wav` file into the `audio-files` folder. **NOTE**: Ensure the `.wav` file is correctly encoded for the [Speech Service](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-use-codec-compressed-audio-input-streams?tabs=windows%2Cdebian%2Cjava-android%2Cterminal&pivots=programming-language-csharp).

> 💡 [TIP]
    > If you don't have sample audio files with Protected Health Information (PHI), you can easily generate them using the **[PHI Call Center Generator](https://github.com/kfprugger/cc-proj)** project.


### 2. Configure Fabric Secrets

To securely store your Azure credentials, use Fabric's built-in secrets.

1.  Go to your Fabric workspace settings.
2.  Select **Azure Key Vault** and either connect an existing Key Vault or use the default Fabric secrets store.
3.  Create the following new secrets:
    * `LanguageKey`: Your Azure Language Service key.
    * `LanguageEndpoint`: Your Azure Language Service endpoint URL.
    * `SpeechKey`: Your Azure Speech Service key.
    * `SpeechRegion`: The region for your Azure Speech Service (e.g., `eastus`).
    * `OpenAIKey`: Your Azure OpenAI Service key.
    * `OpenAIEndpoint`: Your Azure OpenAI Service endpoint URL.

### 3. Create and Configure the Notebook

1.  In your workspace, upload [this notebook](/FabricProjectsnPOCs/audio-redaction/AOAInAzSpeech_mk6_1.Notebook/)
2.  Attach your Lakehouse to the notebook using the "Add Lakehouse" explorer.
3.  Execute the code from the `AOAInAzSpeech_mk6_1.ipynb` file in this repository.

### 4. Update the Notebook Code

Make the following critical changes to the code inside your Fabric Notebook:

1.  **Ensure the first 3 cells run, Install Libraries**: In the very first cell, add the following magic command to install the required Python packages for the notebook session.
    ```python
    %pip install azure-cognitiveservices-speech openai azure-keyvault-secrets azure-identity
    ```

2.  **In Cell 4, Load Secrets**: Replace the hardcoded Azure Key Vault variables with calls to the provisioned Azure Key Vault in your subscription. Ensure that you can access the Key Vault from your Fabric notebook.
    ```python
    # --- Azure Key Vault Configuration ---
    key_vault_name = "akv-rjb-wu3-01" # ⚠️ REPLACE WITH YOUR AZURE KEY VAULT NAME ⚠️
    key_vault_uri = f"https://{key_vault_name}.vault.azure.net"


    # --- Retrieve Secrets using Fabric's Native mssparkutils ---
    # This is the most direct and recommended method for Fabric notebooks. ⚠️ ENSURE THESE SECRETS EXIST IN YOUR AZURE KEY VAULT ⚠️
        try:
        print(f"Retrieving secrets from Azure Key Vault '{key_vault_name}' using mssparkutils...")

        SPEECH_KEY = notebookutils.credentials.getSecret(key_vault_uri, "SPEECH-KEY")
        SPEECH_REGION = notebookutils.credentials.getSecret(key_vault_uri, "SPEECH-REGION")
        AZURE_OPENAI_API_KEY = notebookutils.credentials.getSecret(key_vault_uri, "AZURE-OPENAI-API-KEY")
        AZURE_OPENAI_ENDPOINT = notebookutils.credentials.getSecret(key_vault_uri, "AZURE-OPENAI-ENDPOINT")
        AZURE_OPENAI_GPT_DEPLOYMENT = notebookutils.credentials.getSecret(key_vault_uri, "AZURE-OPENAI-GPT-DEPLOYMENT")

        print("✅ Secrets retrieved successfully.")

    ```



### 5. Run the Transcript Redaction Notebook (AOAInAzSpeech_mk6_1.ipynb)

Run all the cells in the notebook. The script will:
1.  Read the audio file from your Lakehouse.
2.  Process it using Azure AI Services.
3.  Save the new PHI/PII timestamp .json file used for audio redaction file to the `/Files/transcripts` folder in your Lakehouse.
    - Note: When working on productionalizing this repo, you'd want to ensure that enable [OneLake Data Access Roles](https://learn.microsoft.com/en-us/fabric/onelake/security/get-started-data-access-roles) to ensure that improper access is prevented
4. Write the results to the `transcripts` and log tables in your Lakehouse.


### 6. Run the Audio Redaction Notebook (Audio File Redaction.ipynb)
1. Read the transcription and timestamp file
2. Insert either "bleeps" or silences over the sensitive PII/PHI 
3. Output the redacted files to `/Files/redacted-audio` folder in your Lakehouse.

---

## 📁 Fabric Environment Structure

Your final setup in the Microsoft Fabric workspace will consist of these key artifacts:

* **Workspace**: The container for all your project components.
* **Lakehouse**:
    * `/Files/sample-audio/`: Stores the original audio files.
    * `/Files/output/`: Stores the processed, redacted audio files.
* **Notebooks**: The `AOAInAzSpeech_mk6_1` notebook containing the Python code for transcription and PHI/PII timestamp isolation and the `Audio File Redaction` notebook for audio file redaction.
* **Secrets**: Credentials for Azure services stored securely in the workspace settings.