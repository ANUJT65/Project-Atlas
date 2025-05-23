import json
import os
import re
import requests
from openai import AzureOpenAI
import httpx
from pprint import pprint
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
from flask import Blueprint, jsonify, request
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions, ContentSettings
from azure.cosmos import CosmosClient, exceptions
import traceback
import tempfile
import zipfile
import io

# Create blueprint
testcode_bp = Blueprint('testcode', __name__)

# Azure OpenAI Configuration
AZURE_ENDPOINT = "https://suraj-m9lgdbv9-eastus2.cognitiveservices.azure.com/"
AZURE_API_KEY = " "
AZURE_API_VERSION = "2024-12-01-preview"  # Updated API version
DEPLOYMENT_NAME = "gpt-4.1"  # Updated deployment name

# Initialize Azure OpenAI client
client = AzureOpenAI(
    azure_endpoint=AZURE_ENDPOINT,
    api_key=AZURE_API_KEY,
    api_version=AZURE_API_VERSION
)

# Jira configuration 
JIRA_DOMAIN = "prathamgadkari.atlassian.net"
JIRA_API_URL = f"https://{JIRA_DOMAIN}/rest/api/2/search"
JIRA_EMAIL = "prathamgadkari@gmail.com"
JIRA_API_TOKEN = "ATATT3xFfGF0LXSWvbAlLm1lVXyxSroefrBXONpTLDg5mzfknXUUxTYAjQ0u59wKKGh3ObCEnducPVGqRwCLoxDu8oc4xx3aBAHj6A9Tzuj2OqiUszHVo3UvYrpmblYC2xHttFxo5ULieeRE2LNIfR3w_l2YNJTvACQ_zmBnkt6Tjvenqyu2pEM=99E9EA51"
PROJECT_KEY = "SCRUM"

# Validate configurations
if not all([JIRA_DOMAIN, JIRA_EMAIL, JIRA_API_TOKEN, PROJECT_KEY]):
    raise ValueError("Missing required Jira configuration")

# Azure Blob Storage Configuration
account_name = 'barclaysstorage'
account_key = 'w7fJMnkuaZR4RX9LJbTRld8v90S6KDupj1BDHNZ1+Ch9Do7Et56nQKAd2HVXJqgZYEVbcGY/CGRj+AStE2NEXQ=='
container_name = 'data'

# Create a client to interact with blob storage
connect_str = f'DefaultEndpointsProtocol=https;AccountName={account_name};AccountKey={account_key};EndpointSuffix=core.windows.net'
blob_service_client = BlobServiceClient.from_connection_string(connect_str)

# Use the client to connect to the container
try:
    container_client = blob_service_client.get_container_client(container_name)
    # Create container if it doesn't exist
    if not container_client.exists():
        container_client = blob_service_client.create_container(container_name)
        print(f"Container {container_name} created successfully")
    else:
        print(f"Container {container_name} already exists")
except Exception as e:
    print(f"Error initializing blob storage: {str(e)}")
    raise

# Initialize Cosmos DB client
COSMOS_ENDPOINT = "https://barclaysdb.documents.azure.com:443/"
COSMOS_KEY = "ercuc7wFNt4RPsxcx2QTzKP8AhKUDnjJrt0mpZrW2Yi2IQGAa7wDrEbhKRHsurGu0P7GuGny4IZRACDbtecfNQ=="
COSMOS_DATABASE = "RequirementsDB"
COSMOS_CONTAINER = "TestCases"

cosmos_client = CosmosClient(COSMOS_ENDPOINT, COSMOS_KEY)
database = cosmos_client.get_database_client(COSMOS_DATABASE)
test_cases_container = database.get_container_client(COSMOS_CONTAINER)

def get_jira_issues(jql: str = None, max_results: int = 50) -> list:
    """
    Retrieve Jira issues with retry mechanism and validation.
    """
    # Debug environment variables (without exposing sensitive data)
    print("Checking Jira configuration...")
    print(f"JIRA_DOMAIN: {JIRA_DOMAIN}")
    print(f"PROJECT_KEY: {PROJECT_KEY}")
    print(f"JIRA_EMAIL configured: {'Yes' if JIRA_EMAIL else 'No'}")
    print(f"JIRA_API_TOKEN configured: {'Yes' if JIRA_API_TOKEN else 'No'}")
    
    if not all([JIRA_EMAIL, JIRA_API_TOKEN]):
        error_msg = "Jira credentials not properly configured"
        print(error_msg)
        raise ValueError(error_msg)

    if jql is None:
        jql = f"project = {PROJECT_KEY} AND issuetype = Story ORDER BY created DESC"
    
    print(f"Using JQL query: {jql}")  # Debug log
    
    params = {
        "jql": jql,
        "maxResults": max_results,
        "fields": "summary,description,priority,status,assignee,created,updated"
    }
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {"Content-Type": "application/json"}

    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"Attempt {attempt + 1}: Making request to Jira API...")  # Debug log
            r = requests.get(JIRA_API_URL, params=params, auth=auth, headers=headers, timeout=10)
            r.raise_for_status()
            data = r.json()
            issues_count = len(data.get("issues", []))
            print(f"Successfully retrieved {issues_count} issues")
            if issues_count == 0:
                print("Warning: No issues found with the current query")
            return data.get("issues", [])
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {str(e)}")  # Debug log
            if attempt == max_retries - 1:
                print(f"Failed to retrieve issues after {max_retries} attempts: {str(e)}")
                return []
            print(f"Attempt {attempt + 1} failed, retrying...")
            continue

def delete_jira_issue(issue_key: str) -> bool:
    """
    Delete a Jira issue using the Jira API.
    
    Args:
        issue_key: The key of the issue to delete
        
    Returns:
        True if deletion was successful, False otherwise
    """
    try:
        # Jira API endpoint for deleting an issue
        delete_url = f"https://{JIRA_DOMAIN}/rest/api/2/issue/{issue_key}"
        
        # Set up authentication and headers
        auth = (JIRA_EMAIL, JIRA_API_TOKEN)
        headers = {"Content-Type": "application/json"}
        
        # Make the DELETE request
        response = requests.delete(delete_url, auth=auth, headers=headers)
        
        # Check if the request was successful
        if response.status_code == 204:  # 204 No Content is the expected response for successful deletion
            print(f"Successfully deleted Jira issue {issue_key}")
            return True
        else:
            print(f"Failed to delete Jira issue {issue_key}. Status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"Error deleting Jira issue {issue_key}: {str(e)}")
        return False

def get_test_cases_from_db(story_key: str) -> dict:
    """
    Get test cases for a specific story from the database.
    
    Args:
        story_key: The key of the story
        
    Returns:
        Dictionary containing test case information or None if not found
    """
    try:
        # Query for test cases with the given story key
        query = f"SELECT * FROM c WHERE c.story_key = '{story_key}'"
        items = list(test_cases_container.query_items(query=query, enable_cross_partition_query=True))
        
        if items:
            return items[0]
        return None
    except Exception as e:
        print(f"Error getting test cases from database: {str(e)}")
        return None

def save_test_cases_to_db(story_key: str, project_id: str, standard_doc_id: str, user_story_id: str, test_files: list, blob_url: str) -> str:
    """
    Save test cases to the database.
    
    Args:
        story_key: The key of the story
        project_id: The project ID
        standard_doc_id: The standard document ID
        user_story_id: The user story ID
        test_files: List of test files with name and content
        blob_url: URL of the blob storage
        
    Returns:
        The ID of the saved test case or None if saving failed
    """
    try:
        # Generate a unique test case ID
        test_case_id = f"test_{project_id}_{standard_doc_id}_{user_story_id}_{int(datetime.now().timestamp())}"
        
        # Extract test steps and expected results from the first test file
        test_steps = []
        expected_results = ""
        if test_files and len(test_files) > 0:
            first_test = test_files[0]
            content = first_test.get('content', '')
            
            # Simple parsing to extract test steps and expected results
            lines = content.split('\n')
            for line in lines:
                if line.strip().startswith('def test_'):
                    # This is likely a test function, extract steps
                    test_steps = [step.strip() for step in lines if step.strip() and not step.strip().startswith(('def', 'import', 'from', 'class', '@'))]
                elif 'assert' in line:
                    expected_results = line.strip()
        
        # Create the test case document with the required structure
        test_case_doc = {
            "id": test_case_id,
            "project_id": project_id,
            "standard_doc_id": standard_doc_id,
            "user_story_id": user_story_id,
            "title": f"Test Cases for {story_key}",
            "description": f"Automated test cases for story {story_key}",
            "test_steps": test_steps,
            "expected_results": expected_results or "Tests should pass successfully",
            "github_issue_id": story_key,
            "status": "To Do",
            "created_at": datetime.utcnow().isoformat(),
            "blob_url": blob_url  # Add the blob URL to access the test files
        }
        
        # Create the item in Cosmos DB
        test_cases_container.create_item(body=test_case_doc)
        print(f"Test case for story {story_key} successfully stored in Cosmos DB.")
        return test_case_id
    except Exception as e:
        print(f"Error saving test case to database: {str(e)}")
        return None

def delete_test_cases_from_db(story_key: str) -> bool:
    """
    Delete test cases for a specific story from the database.
    
    Args:
        story_key: The key of the story
        
    Returns:
        True if deletion was successful, False otherwise
    """
    try:
        # Query for test cases with the given story key
        query = f"SELECT * FROM c WHERE c.story_key = '{story_key}'"
        items = list(test_cases_container.query_items(query=query, enable_cross_partition_query=True))
        
        if not items:
            print(f"No test cases found for story {story_key}")
            return False
        
        # Delete each test case
        for item in items:
            test_cases_container.delete_item(item=item['id'], partition_key=item['id'])
            print(f"Deleted test case {item['id']} for story {story_key}")
        
        return True
    except Exception as e:
        print(f"Error deleting test cases from database: {str(e)}")
        return False

def generate_test_cases(story: dict, language: str = "javascript", framework: str = "jest", context: str = "") -> dict:
    """
    Generate test cases for a user story in the specified language and framework.
    
    Args:
        story: The user story dictionary from Jira
        language: The programming language for test cases (javascript or python)
        framework: The testing framework to use (jest, mocha, pytest, etc.)
        context: Additional context provided by the user for regeneration
        
    Returns:
        Dictionary containing test case files with their content
    """
    summary = story.get("fields", {}).get("summary", "")
    description = story.get("fields", {}).get("description", "")
    issue_key = story.get("key", "NO_KEY")
    
    # Determine file extension based on language
    file_ext = ".js" if language.lower() == "javascript" else ".py"
    
    # Determine test file naming based on language and framework
    if language.lower() == "javascript":
        if framework.lower() == "jest":
            test_file = f"{issue_key}.test{file_ext}"
        elif framework.lower() == "mocha":
            test_file = f"{issue_key}.spec{file_ext}"
        else:
            test_file = f"{issue_key}.test{file_ext}"
    else:  # Python
        if framework.lower() == "pytest":
            test_file = f"test_{issue_key}{file_ext}"
        else:
            test_file = f"{issue_key}_test{file_ext}"
    
    # Build the prompt with context if provided
    base_prompt = f"""Generate comprehensive test cases for the following user story.
Output a valid JSON object with the following structure:
{{
    "{test_file}": "Complete test code for the user story"
}}

User Story:
Title: {summary}
Description: {description}

Technical Requirements:
- Language: {language}
- Framework: {framework}
- Include both positive and negative test cases
- Cover all acceptance criteria in the user story
- Include proper setup and teardown
- Use modern syntax and best practices
- Include comments explaining the purpose of each test
- Follow the naming conventions for {framework} tests
- Include proper error handling and assertions
"""

    # Add context to prompt if provided
    if context:
        prompt = f"{base_prompt}\n\nAdditional Context:\n{context}\n\nIMPORTANT: Consider the additional context when generating test cases."
    else:
        prompt = base_prompt + "\n\nIMPORTANT: Respond with ONLY the JSON object, no additional text or notes."
    
    try:
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": f"You are a QA engineer that creates comprehensive {language} test cases using {framework}. Always respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000,
            temperature=0.3,
            top_p=0.9
        )
        
        # Clean and validate the response
        cleaned_text = response.choices[0].message.content.strip()
        
        # Remove any markdown code block markers and extra text
        if "```" in cleaned_text:
            # Extract text between first ``` and last ```
            start = cleaned_text.find("```") + 3
            end = cleaned_text.rfind("```")
            if start < end:
                cleaned_text = cleaned_text[start:end]
            
            # Remove language identifier if present (e.g., ```json)
            if cleaned_text.lower().startswith("json\n"):
                cleaned_text = cleaned_text[5:]
        
        # Remove any text after the last closing brace
        last_brace = cleaned_text.rfind("}")
        if last_brace != -1:
            cleaned_text = cleaned_text[:last_brace + 1]

        # Remove any text before the first opening brace
        first_brace = cleaned_text.find("{")
        if first_brace != -1:
            cleaned_text = cleaned_text[first_brace:]
        
        cleaned_text = cleaned_text.strip()
        
        try:
            # First attempt to parse the JSON
            test_cases = json.loads(cleaned_text)
            return test_cases
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON from generated test cases: {str(e)}")
            print("Raw output length:", len(cleaned_text))
            print("First 500 characters of raw output:", cleaned_text[:500])
            print("Last 500 characters of raw output:", cleaned_text[-500:])
            
            # Attempt to fix common JSON issues
            try:
                # Try to fix truncated JSON
                if not cleaned_text.endswith("}"):
                    cleaned_text = cleaned_text + "}"
                if cleaned_text.count("{") > cleaned_text.count("}"):
                    cleaned_text = cleaned_text + "}" * (cleaned_text.count("{") - cleaned_text.count("}"))
                
                # Remove any trailing commas before closing braces
                cleaned_text = re.sub(r',(\s*})', r'\1', cleaned_text)
                
                # Fix any missing quotes around property names
                cleaned_text = re.sub(r'([{,]\s*)(\w+)(:)', r'\1"\2"\3', cleaned_text)
                
                test_cases = json.loads(cleaned_text)
                print("Successfully fixed and parsed JSON")
                return test_cases
            except:
                print("Failed to fix JSON")
                return {}
            
    except Exception as e:
        print(f"Error generating test cases: {str(e)}")
        return {}

def save_test_cases(test_cases: dict, issue_key: str, language: str) -> str:
    """
    Save the generated test cases to files.
    
    Args:
        test_cases: Dictionary containing test case files with their content
        issue_key: Jira issue key
        language: The programming language for test cases
        
    Returns:
        Path to the generated test cases folder
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = f"generated_tests/{issue_key}_{timestamp}"
    
    try:
        # Create main directory
        os.makedirs(folder, exist_ok=True)
        
        # Create language-specific directory
        language_dir = os.path.join(folder, language.lower())
        os.makedirs(language_dir, exist_ok=True)
        
        # Save test files
        for file_name, content in test_cases.items():
            file_path = os.path.join(language_dir, file_name)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Saved {file_path}")
        
        # Create a README.md with information about the test cases
        readme_content = f"""# Test Cases for {issue_key}

Generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## Language
{language.title()}

## Test Files
"""
        for file_name in test_cases.keys():
            readme_content += f"- {file_name}\n"
        
        readme_content += """
## Running the Tests
"""
        if language.lower() == "javascript":
            readme_content += """```bash
# Install dependencies
npm install

# Run tests
npm test
```
"""
        else:  # Python
            readme_content += """```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest
```
"""
        
        with open(os.path.join(folder, "README.md"), "w", encoding="utf-8") as f:
            f.write(readme_content)
        print(f"Saved README.md")
        
        return folder
        
    except Exception as e:
        print(f"Error saving test case files: {str(e)}")
        return None

def upload_to_blob_storage(folder_path: str, issue_key: str) -> str:
    """
    Upload the generated test cases folder to Azure Blob Storage.
    Returns the URL of the uploaded folder.
    """
    try:
        # Create a zip file of the folder
        zip_path = f"{folder_path}.zip"
        import shutil
        shutil.make_archive(folder_path, 'zip', folder_path)
        
        # Generate blob name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        blob_name = f"testcases/{issue_key}_{timestamp}.zip"
        
        # Create blob client
        blob_client = container_client.get_blob_client(blob_name)
        
        # Set content settings for zip file
        content_settings = ContentSettings(
            content_type='application/zip',
            content_disposition=f'attachment; filename="{os.path.basename(zip_path)}"'
        )
        
        # Upload the file
        with open(zip_path, "rb") as data:
            blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings=content_settings
            )
        
        # Generate URL
        blob_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"
        
        # Clean up the zip file
        os.remove(zip_path)
        
        print(f"Successfully uploaded {blob_name} to blob storage")
        return blob_url
        
    except Exception as e:
        print(f"Error uploading to blob storage: {str(e)}")
        print(f"Stack trace: {traceback.format_exc()}")
        return None

@testcode_bp.route('/stories', methods=['GET'])
def get_stories():
    """Get all Jira stories for the configured project."""
    try:
        issues = get_jira_issues()
        if not issues:
            return jsonify({
                'success': False,
                'error': 'No stories found'
            }), 404
            
        stories = []
        for issue in issues:
            stories.append({
                'key': issue.get('key'),
                'summary': issue.get('fields', {}).get('summary'),
                'description': issue.get('fields', {}).get('description'),
                'status': issue.get('fields', {}).get('status', {}).get('name'),
                'priority': issue.get('fields', {}).get('priority', {}).get('name')
            })
            
        return jsonify({
            'success': True,
            'stories': stories
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@testcode_bp.route('/stories/<story_key>', methods=['DELETE'])
def delete_story(story_key):
    """Delete a Jira story and its associated test cases."""
    try:
        # First, delete the story from Jira
        jira_deleted = delete_jira_issue(story_key)
        
        # Then, delete the test cases from the database
        db_deleted = delete_test_cases_from_db(story_key)
        
        if jira_deleted or db_deleted:
            return jsonify({
                'success': True,
                'message': f'Story {story_key} deleted successfully',
                'jira_deleted': jira_deleted,
                'db_deleted': db_deleted
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Failed to delete story {story_key}'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@testcode_bp.route('/preview-tests', methods=['POST'])
def preview_tests():
    """
    Generate test cases for preview without saving to storage.
    """
    try:
        data = request.get_json()
        story_key = data.get('story_key')
        language = data.get('language', 'python')
        framework = data.get('framework', 'pytest')

        if not story_key:
            return jsonify({'success': False, 'error': 'Missing story_key parameter'}), 400

        # Get story details from Jira
        jql = f'key = {story_key}'
        issues = get_jira_issues(jql, 1)
        
        if not issues:
            return jsonify({'success': False, 'error': f'Story {story_key} not found'}), 404

        story = issues[0]
        story_summary = story['fields']['summary']
        story_description = story['fields'].get('description', '')

        # Generate test cases using Azure OpenAI
        prompt = f"""
        Generate test cases for the following user story in {language} using {framework}:
        
        Story: {story_summary}
        Description: {story_description}
        
        Generate comprehensive test cases that cover the main functionality and edge cases.
        Return the test cases in a clear, well-structured format.
        Include proper setup and teardown procedures.
        Add descriptive comments explaining the test cases.
        """

        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {"role": "system", "content": "You are a test automation expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )

        # Extract and format the test cases
        test_content = response.choices[0].message.content
        
        # Create a test file with proper naming and extension
        file_extension = '.py' if language.lower() == 'python' else '.js'
        test_files = [{
            'name': f'test_{story_key.lower()}{file_extension}',
            'content': test_content
        }]

        return jsonify({
            'success': True,
            'test_files': test_files,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"Error generating test preview: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@testcode_bp.route('/generate-tests', methods=['POST'])
def generate_tests():
    """
    Save and upload test cases to blob storage.
    """
    try:
        data = request.get_json()
        story_key = data.get('story_key')
        project_id = data.get('project_id')  # This should be provided by the frontend
        test_files = data.get('test_files', [])

        print(f"Received request to generate tests for story {story_key} with project ID {project_id}")

        if not story_key or not test_files:
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

        if not project_id:
            return jsonify({'success': False, 'error': 'Project ID is required'}), 400

        # Create a temporary directory for the test files
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a folder for the test files using the provided project_id
            folder_name = f"{project_id}/{story_key}/tests_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            folder_path = os.path.join(temp_dir, folder_name)
            os.makedirs(folder_path, exist_ok=True)

            # Save test files to the temporary directory
            for test_file in test_files:
                file_path = os.path.join(folder_path, test_file['name'])
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(test_file['content'])

            # Create a zip file
            zip_path = os.path.join(temp_dir, f"{story_key}_tests.zip")
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for root, _, files in os.walk(folder_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, folder_path)
                        zipf.write(file_path, arcname)

            # Upload to blob storage
            blob_name = f"{folder_name}/tests.zip"
            blob_client = container_client.get_blob_client(blob_name)

            # Upload the zip file
            with open(zip_path, 'rb') as data:
                blob_client.upload_blob(data, overwrite=True)
        
            # Generate SAS token for the blob
            sas_token = generate_blob_sas(
                account_name=account_name,
                container_name=container_name,
                blob_name=blob_name,
                account_key=account_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.utcnow() + timedelta(hours=24)
            )

            # Construct the blob URL with SAS token
            blob_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"

            # Save to Cosmos DB with the correct structure
            test_case_id = save_test_cases_to_db(
                story_key=story_key,
                project_id=project_id,
                standard_doc_id=f"std_{story_key}",  # Generate a standard doc ID based on story key
                user_story_id=story_key,  # Use story key as user story ID
                test_files=test_files,
                blob_url=blob_url
            )

            if not test_case_id:
                return jsonify({'success': False, 'error': 'Failed to save test cases to database'}), 500

            return jsonify({
                'success': True,
                'folder': folder_name,
                'blob_url': blob_url,
                'test_case_id': test_case_id
            })
        
    except Exception as e:
        print(f"Error generating and uploading tests: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@testcode_bp.route('/regenerate-tests', methods=['POST'])
def regenerate_tests():
    """
    Regenerate test cases with additional context from the user.
    """
    try:
        data = request.get_json()
        story_key = data.get('story_key')
        project_id = data.get('project_id')
        test_files = data.get('test_files', [])
        user_context = data.get('context', '')  # Additional context provided by user
        language = data.get('language', 'python')
        framework = data.get('framework', 'pytest')

        print(f"Received request to regenerate tests for story {story_key} with project ID {project_id}")
        print(f"User context: {user_context}")

        if not story_key or not test_files or not project_id:
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400

        # Get story details from Jira
        jql = f'key = {story_key}'
        issues = get_jira_issues(jql, 1)
        
        if not issues:
            return jsonify({'success': False, 'error': f'Story {story_key} not found'}), 404

        story = issues[0]
        
        # Generate new test cases with the provided context
        test_cases = generate_test_cases(
            story=story,
            language=language,
            framework=framework,
            context=user_context
        )
        
        if not test_cases:
            return jsonify({'success': False, 'error': 'Failed to generate test cases'}), 500

        # Convert the test cases to the expected format
        test_files = [{
            'name': name,
            'content': content
        } for name, content in test_cases.items()]

        return jsonify({
            'success': True,
            'test_files': test_files,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error regenerating tests: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@testcode_bp.route('/push-to-github', methods=['POST'])
def push_to_github():
    try:
        data = request.json
        owner = data.get('owner')
        repo = data.get('repo')
        file_url = data.get('fileUrl')
        path = data.get('path')

        if not all([owner, repo, file_url, path]):
            return jsonify({
                'success': False,
                'error': 'Missing required parameters'
            }), 400

        # Make request to GitHub bot
        github_bot_url = "https://git-hub-bot-git-main-anujs-projects-b5a04637.vercel.app/push_test_using_url"
        payload = {
            "owner": owner,
            "repo": repo,
            "fileUrl": file_url,
            "path": path
        }
        headers = {
            "Content-Type": "application/json"
        }

        response = requests.post(github_bot_url, json=payload, headers=headers)

        if response.ok:
            return jsonify({
                'success': True,
                'message': 'Successfully pushed to GitHub',
                'data': response.json()
            })
        else:
            return jsonify({
                'success': False,
                'error': f'GitHub bot error: {response.text}'
            }), response.status_code

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@testcode_bp.route('/generate-code', methods=['POST'])
def generate_code():
    """
    Generate code based on user input using Azure OpenAI.
    """
    try:
        data = request.get_json()
        user_input = data.get('input')
        language = data.get('language', 'python')
        framework = data.get('framework', '')
        context = data.get('context', '')

        if not user_input:
            return jsonify({
                'success': False,
                'error': 'Missing input parameter'
            }), 400

        # Build the prompt
        prompt = f"""
        Generate a complete implementation code that satisfies the following test cases:

        Test File Content:
        {user_input}

        Technical Requirements:
        - Language: {language}
        - Framework: {framework}
        {context if context else ''}

        Instructions:
        1. Analyze the test cases carefully to understand the required functionality
        2. Extract all function signatures, class definitions, and expected behaviors from the tests
        3. Implement all necessary functions and classes that will make the tests pass
        4. Follow the exact naming conventions used in the test cases
        5. Include all required imports and dependencies
        6. Ensure proper error handling for edge cases shown in the tests
        7. Add comprehensive documentation:
           - Module-level docstring explaining the purpose
           - Function/class docstrings with parameters and return types
           - Inline comments for complex logic
        8. Maintain clean code principles:
           - Follow language-specific best practices
           - Use meaningful variable names
           - Keep functions focused and single-purpose
           - Implement proper encapsulation and data validation

        Expected Output Format:
        ```{language}
        # Imports and dependencies

        # Main implementation code

        # Helper functions/classes (if needed)

        # Example usage (if applicable)
        ```

        IMPORTANT:
        - The implementation must pass all test cases provided
        - Use only standard library unless specific packages are mentioned in tests
        - Follow the exact function/class signatures from the test file
        - Include type hints and docstrings (if language supports)
        - Handle all edge cases implied by the test assertions
        """

        # Make the API call
        response = client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=[
                {
                    "role": "system",
                    "content": f"You are a {language} programming expert. Generate clean, efficient, and well-documented code."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=4096,
            temperature=0.7,
            top_p=0.9
        )

        generated_code = response.choices[0].message.content

        return jsonify({
            'success': True,
            'code': generated_code,
            'timestamp': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"Error generating code: {str(e)}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@testcode_bp.route('/push-code-to-github', methods=['POST'])
def push_code_to_github():
    try:
        print("Starting push-code-to-github route...")
        data = request.get_json()
        code = data.get('code')
        language = data.get('language', 'python')
        framework = data.get('framework', '')
        path = data.get('path', '')
        is_test_case = data.get('is_test_case', False)  # New parameter to identify test cases

        print(f"Received request with language: {language}, framework: {framework}, path: {path}, is_test_case: {is_test_case}")
        print(f"Code length: {len(code) if code else 0}")

        if not code:
            print("Error: No code provided")
            return jsonify({
                'success': False,
                'error': 'Missing code parameter'
            }), 400

        # Create zip file in memory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"code_{timestamp}.zip"
        
        # Create a BytesIO object to hold the zip file
        zip_buffer = io.BytesIO()
        
        # Determine file extension and name based on language and framework
        if language.lower() == 'python':
            if framework.lower() == 'pytest':
                file_extension = '.py'
                file_name = f"test_{timestamp}{file_extension}" if is_test_case else f"code{file_extension}"
            else:
                file_extension = '.py'
                file_name = f"{timestamp}_test{file_extension}" if is_test_case else f"code{file_extension}"
        else:  # JavaScript
            if framework.lower() == 'jest':
                file_extension = '.js'
                file_name = f"{timestamp}.test{file_extension}" if is_test_case else f"code{file_extension}"
            elif framework.lower() == 'mocha':
                file_extension = '.js'
                file_name = f"{timestamp}.spec{file_extension}" if is_test_case else f"code{file_extension}"
            else:
                file_extension = '.js'
                file_name = f"{timestamp}_test{file_extension}" if is_test_case else f"code{file_extension}"
        
        # Create the zip file
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # Add the code file to the zip with appropriate name
            zipf.writestr(file_name, code)
        
        # Reset the buffer position to the beginning
        zip_buffer.seek(0)
        
        # Upload the zip file to blob storage
        blob_name = f"generated_code/{zip_filename}"
        print(f"Uploading zip file to blob: {blob_name}")
        
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(zip_buffer, overwrite=True)
        print("Zip file uploaded successfully to blob storage")

        # Generate SAS token for the blob
        print("Generating SAS token...")
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=24)
        )
        print("SAS token generated successfully")

        # Construct the blob URL with SAS token
        blob_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"
        print(f"Generated blob URL: {blob_url}")

        # Make request to GitHub bot
        github_bot_url = "https://git-hub-bot-git-main-anujs-projects-b5a04637.vercel.app/push_test_using_url"
        print(f"Making request to GitHub bot: {github_bot_url}")
        
        # Ensure the path is properly formatted for test cases
        if is_test_case:
            if not path:
                path = f"tests/{file_name}"
            elif not path.endswith(file_extension):
                path = f"{path}/{file_name}" if path.endswith('/') else f"{path}{file_extension}"
        else:
            if not path:
                path = f"src/{file_name}"
            elif not path.endswith(file_extension):
                path = f"{path}/{file_name}" if path.endswith('/') else f"{path}{file_extension}"
        
        payload = {
            "owner": "ANUJT65",
            "repo": "Jira_Testcases",
            "fileUrl": blob_url,
            "path": path
        }
        print(f"Request payload: {json.dumps(payload, indent=2)}")
        
        headers = {
            "Content-Type": "application/json"
        }

        print("Sending request to GitHub bot...")
        response = requests.post(github_bot_url, json=payload, headers=headers)
        print(f"GitHub bot response status: {response.status_code}")
        print(f"GitHub bot response: {response.text}")

        if response.ok:
            print("Successfully pushed code to GitHub")
            return jsonify({
                'success': True,
                'message': 'Successfully pushed code to GitHub',
                'data': response.json()
            })
        else:
            print(f"GitHub bot error: {response.text}")
            return jsonify({
                'success': False,
                'error': f'GitHub bot error: {response.text}'
            }), response.status_code

    except Exception as e:
        print(f"Error in push-code-to-github: {str(e)}")
        print(f"Stack trace: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == "__main__":
    main() 
