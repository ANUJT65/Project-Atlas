import os
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential

class FormRecognizerExtractor:
    def __init__(self, endpoint, api_key):
        """Initialize the Form Recognizer client with Azure credentials."""
        if not endpoint or not api_key:
            raise ValueError("Both endpoint and API key are required")
            
        self.endpoint = endpoint
        self.api_key = api_key
        try:
            self.document_analysis_client = DocumentAnalysisClient(
                endpoint=self.endpoint,
                credential=AzureKeyCredential(self.api_key)
            )
        except Exception as e:
            raise Exception(f"Failed to initialize Form Recognizer client: {str(e)}")

    def extract_text_from_file(self, file_path):
        """Extract text from a document file."""
        try:
            # Verify file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            print(f"Analyzing document: {file_path}")

            # Read and analyze the document
            with open(file_path, "rb") as document:
                poller = self.document_analysis_client.begin_analyze_document(
                    "prebuilt-document", document
                )
                result = poller.result()

            # Extract text from paragraphs
            text_content = []
            for paragraph in getattr(result, "paragraphs", []):
                text_content.append(paragraph.content)

            return "\n".join(text_content)

        except Exception as e:
            print(f"Error extracting text from document: {str(e)}")
            return None

if __name__ == "__main__":
    # Azure credentials
    endpoint = "https://barclaysform.cognitiveservices.azure.com/"
    api_key = ""

    # Initialize extractor
    extractor = FormRecognizerExtractor(endpoint, api_key)

    while True:
        print("\nDocument Text Extractor")
        print("=====================")
        print("Enter 'exit' to quit")
        
        # Get file path from user
        file_path = input("\nEnter the path to your document: ").strip()
        
        if file_path.lower() == 'exit':
            print("Goodbye!")
            break
        
        # Extract and display text
        text = extractor.extract_text_from_file(file_path)
        if text:
            print("\nExtracted Text:")
            print("==============")
            print(text)
