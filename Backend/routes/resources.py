from flask import Blueprint, request, jsonify, send_file
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions, ContentSettings
from azure.cosmos import CosmosClient, PartitionKey, exceptions
from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from datetime import datetime, timedelta
import urllib.parse
import uuid
import os
import sys  # Added missing import for sys module
from io import BytesIO
from werkzeug.utils import secure_filename
import requests
from bs4 import BeautifulSoup
import httpx
import time
from urllib.parse import urlparse
from openai import AzureOpenAI
import traceback
import json
from flask_cors import CORS


resources = Blueprint('resources', __name__, url_prefix='/resources')

# Enable CORS for this blueprint with specific headers
CORS(resources, 
     resources={r"/*": {
         "origins": "http://localhost:5173",
         "allow_headers": ["Content-Type", "x-user-id"],
         "methods": ["GET", "POST", "OPTIONS"]
     }})

# Azure OpenAI Configuration
OPENAI_ENDPOINT = "https://suraj-m9lgdbv9-eastus2.cognitiveservices.azure.com/"
OPENAI_DEPLOYMENT = "gpt-4o"
OPENAI_API_KEY = " "
OPENAI_API_VERSION = "2024-12-01-preview"

# Azure Storage Configuration
ACCOUNT_NAME = 'barclaysstorage'
ACCOUNT_KEY = ' '
BLOB_CONTAINER = 'resources'

# Create Blob Service Client
connect_str = f'DefaultEndpointsProtocol=https;AccountName={ACCOUNT_NAME};AccountKey={ACCOUNT_KEY};EndpointSuffix=core.windows.net'
blob_service_client = BlobServiceClient.from_connection_string(connect_str)

# Get or create container
try:
    container_client = blob_service_client.get_container_client(BLOB_CONTAINER)
    container_client.get_container_properties()
except Exception:
    container_client = blob_service_client.create_container(BLOB_CONTAINER)

# Cosmos DB Configuration
COSMOS_URL = "https://barclaysdb.documents.azure.com:443/"
COSMOS_KEY = " "
DATABASE_NAME = "RequirementsDB"
RESOURCES_CONTAINER = "Resources"

# Initialize Cosmos DB client
cosmos_client = CosmosClient(COSMOS_URL, credential=COSMOS_KEY)
database = cosmos_client.get_database_client(DATABASE_NAME)
resources_container = database.get_container_client(RESOURCES_CONTAINER)

# Form Recognizer Configuration
FORM_RECOGNIZER_ENDPOINT = "https://barclaysform.cognitiveservices.azure.com/"
FORM_RECOGNIZER_KEY = " "

# Initialize Azure OpenAI client
openai_client = AzureOpenAI(
    azure_endpoint=OPENAI_ENDPOINT,
    api_key=OPENAI_API_KEY,
    api_version=OPENAI_API_VERSION,
    http_client=httpx.Client()
)

# Confluence Configuration
email = "prathamgadkari@gmail.com"
api_token = " "
base_url = "https://prathamgadkari.atlassian.net/wiki"

def validate_url(url):
    """Validate if a string is a proper URL"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def scrape_website(url):
    """Scrape website content"""
    try:
        if not validate_url(url):
            return "Invalid URL format"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        # Add basic rate limiting
        time.sleep(1)
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove unwanted elements
        for element in soup(['script', 'style', 'header', 'footer', 'nav']):
            element.decompose()

        # Extract text from multiple important tags
        text_elements = []
        important_tags = ['p', 'h1', 'h2', 'h3', 'article', 'section']
        
        for tag in important_tags:
            elements = soup.find_all(tag)
            text_elements.extend([elem.get_text() for elem in elements])

        # Clean and join the text
        text = ' '.join(text_elements)
        text = ' '.join(text.split())  # Remove extra whitespace
        return text.strip()

    except requests.Timeout:
        return "Error: Request timed out"
    except requests.RequestException as e:
        return f"Error scraping the site: {str(e)}"

def summarize_content(content):
    """Summarize website content using Azure OpenAI"""
    try:
        if not content or content.startswith("Error"):
            return "No valid content to summarize."

        prompt = (
            "Provide a professional analysis of this website content following this structure:\n\n"
            "**Website Overview:**\n"
            "- Main purpose and target audience\n\n"
            "**Key Components:**\n"
            "- Important sections and features\n"
            "- Notable products or services\n\n"
            "**Notable Elements:**\n"
            "- Recent updates or announcements\n"
            "- Special features or unique selling points\n\n"
            "**Summary:**\n"
            "- Overall value proposition\n\n"
            f"Content to analyze:\n{content}"
        )

        response = openai_client.chat.completions.create(
            model=OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are a professional web content analyst."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"Error summarizing content: {str(e)}"

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg', 'tiff', 'docx', 'txt', 'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_content_type(file_ext):
    content_types = {
        '.pdf': 'application/pdf',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.csv': 'text/csv',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.txt': 'text/plain',
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.ogg': 'audio/ogg',
        '.m4a': 'audio/mp4',
        '.flac': 'audio/flac'
    }
    return content_types.get(file_ext.lower(), 'application/octet-stream')

def generate_sas_url(blob_name):
    """Generate a SAS URL for the blob that expires in 24 hours"""
    sas_token = generate_blob_sas(
        account_name=ACCOUNT_NAME,
        container_name=BLOB_CONTAINER,
        blob_name=blob_name,
        account_key=ACCOUNT_KEY,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(hours=24)
    )
    
    encoded_blob_name = urllib.parse.quote(blob_name)
    return f'https://{ACCOUNT_NAME}.blob.core.windows.net/{BLOB_CONTAINER}/{encoded_blob_name}?{sas_token}'

def extract_text_from_bytes(file_bytes):
    """Extract text from a document using Azure Form Recognizer"""
    try:
        document_analysis_client = DocumentAnalysisClient(
            endpoint=FORM_RECOGNIZER_ENDPOINT,
            credential=AzureKeyCredential(FORM_RECOGNIZER_KEY)
        )

        poller = document_analysis_client.begin_analyze_document(
            "prebuilt-document", file_bytes
        )
        result = poller.result()

        text_content = []
        for paragraph in getattr(result, 'paragraphs', []):
            text_content.append(paragraph.content)

        return "\n".join(text_content)

    except Exception as e:
        print(f"Error extracting text: {str(e)}")
        return None

def upload_to_blob_storage_from_memory(file_bytes, blob_name, content_type):
    """Upload file from memory to Azure Blob Storage with proper content type"""
    try:
        print(f"Starting blob upload: {blob_name} (size: {len(file_bytes)} bytes, type: {content_type})")
        
        # Make sure we have a valid content type
        if not content_type:
            print("Warning: No content type specified, using default")
            content_type = 'application/octet-stream'
        
        # Create content settings
        content_settings = ContentSettings(content_type=content_type)
        print(f"Created content settings with type: {content_type}")
        
        # Get blob client
        blob_client = container_client.get_blob_client(blob_name)
        print(f"Got blob client for: {blob_name}")
        
        # Upload the blob
        print(f"Uploading blob...")
        upload_result = blob_client.upload_blob(
            file_bytes,
            overwrite=True,
            content_settings=content_settings
        )
        print(f"Upload successful, etag: {upload_result.get('etag', 'unknown')}")
        
        # Generate SAS URL
        sas_url = generate_sas_url(blob_name)
        print(f"Generated SAS URL: {sas_url[:50]}...")
        
        return sas_url

    except Exception as e:
        print(f"ERROR uploading to blob storage: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Try a simpler upload as fallback
        try:
            print("Attempting simplified upload as fallback...")
            blob_client = blob_service_client.get_blob_client(container=BLOB_CONTAINER, blob=blob_name)
            blob_client.upload_blob(file_bytes, overwrite=True)
            sas_url = generate_sas_url(blob_name)
            print("Fallback upload successful")
            return sas_url
        except Exception as inner_e:
            print(f"ERROR in fallback upload: {str(inner_e)}")
            traceback.print_exc()
            return None

@resources.route('/add', methods=['POST'])
def add_resource():
    try:
        project_id = request.form.get('projectId')
        resource_name = request.form.get('resourceName')
        tagged_users = request.form.getlist('taggedUsers[]')
        
        if not project_id or not resource_name:
            return jsonify({
                'success': False,
                'message': 'Project ID and resource name are required'
            }), 400

        file = request.files.get('file')
        text_content = request.form.get('textContent')
        
        resource_data = {
            'id': str(uuid.uuid4()),
            'project_id': project_id,
            'name': resource_name,
            'tagged_users': tagged_users,
            'created_at': datetime.utcnow().isoformat(),
            'created_by': request.headers.get('X-User-ID'),
            'type': 'text' if text_content else 'file'
        }

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_bytes = file.read()
            
            # Extract text using Form Recognizer
            extracted_text = extract_text_from_bytes(file_bytes)
            
            # Upload to Blob Storage
            blob_name = f"{project_id}/{resource_data['id']}/{filename}"
            content_type = get_content_type(os.path.splitext(filename)[1])
            blob_url = upload_to_blob_storage_from_memory(file_bytes, blob_name, content_type)
            
            resource_data.update({
                'file_name': filename,
                'context': extracted_text,
                'url': blob_url,
                'content_type': content_type
            })
            
        elif text_content:
            resource_data.update({
                'context': text_content,
                'content_type': 'text/plain'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No content provided'
            }), 400

        # Save to Cosmos DB
        resources_container.create_item(resource_data)

        return jsonify({
            'success': True,
            'message': 'Resource added successfully',
            'resource': resource_data
        }), 201

    except Exception as e:
        print(f"Error adding resource: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error adding resource: {str(e)}'
        }), 500

@resources.route('/project/<project_id>', methods=['GET'])
def get_project_resources(project_id):
    try:
        query = "SELECT * FROM c WHERE c.project_id = @project_id ORDER BY c.created_at DESC"
        parameters = [{"name": "@project_id", "value": project_id}]
        
        resources = list(resources_container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))

        # Generate fresh SAS URLs for file resources
        for resource in resources:
            if resource.get('type') == 'file' and resource.get('url'):
                blob_name = f"{project_id}/{resource['id']}/{resource['file_name']}"
                resource['url'] = generate_sas_url(blob_name)

        return jsonify({
            'success': True,
            'resources': resources
        }), 200

    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error fetching resources: {str(e)}'
        }), 500

@resources.route('/scrape-website', methods=['POST'])
def scrape_website_route():
    """Scrape a website, analyze its content, and save it as a resource"""
    try:
        # Extract request data
        data = request.json
        if not data or not data.get('url') or not data.get('projectId') or not data.get('resourceName'):
            return jsonify({
                'success': False,
                'message': 'URL, Project ID, and Resource Name are required'
            }), 400

        url = data.get('url')
        project_id = data.get('projectId')
        resource_name = data.get('resourceName')
        tagged_users = data.get('taggedUsers', [])

        # Validate URL
        if not validate_url(url):
            return jsonify({
                'success': False,
                'message': 'Invalid URL format'
            }), 400

        # Scrape website content
        print(f"Scraping website: {url}")
        scraped_content = scrape_website(url)
        
        if scraped_content.startswith("Error"):
            return jsonify({
                'success': False,
                'message': scraped_content
            }), 400

        # Generate summary using Azure OpenAI
        summary = summarize_content(scraped_content)
        
        # Create resource data
        resource_data = {
            'id': str(uuid.uuid4()),
            'project_id': project_id,
            'name': resource_name,
            'url': url,
            'tagged_users': tagged_users,
            'created_at': datetime.utcnow().isoformat(),
            'created_by': request.headers.get('X-User-ID'),
            'type': 'website',
            'content_type': 'text/html',
            'original_content': scraped_content[:20000],  # Limit content size (CosmosDB has document size limits)
            'summary': summary,
            'source_url': url
        }

        # Save to Cosmos DB
        resources_container.create_item(resource_data)

        return jsonify({
            'success': True,
            'message': 'Website scraped and saved successfully',
            'resource': {
                'id': resource_data['id'],
                'name': resource_data['name'],
                'summary': summary,
                'url': url,
                'created_at': resource_data['created_at']
            }
        }), 201

    except Exception as e:
        print(f"Error scraping website: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error scraping website: {str(e)}'
        }), 500

@resources.route('/transcribe-audio', methods=['POST'])
def transcribe_audio_route():
    """Transcribe an audio file, generate a summary, and save it as a resource"""
    try:
        # Check if required fields are present
        if 'file' not in request.files or not request.form.get('projectId') or not request.form.get('resourceName'):
            return jsonify({
                'success': False,
                'message': 'Audio file, Project ID, and Resource Name are required'
            }), 400

        project_id = request.form.get('projectId')
        resource_name = request.form.get('resourceName')
        tagged_users = request.form.getlist('taggedUsers[]')
        file = request.files['file']
        
        # Validate file
        if file.filename == '':
            return jsonify({
                'success': False,
                'message': 'No audio file selected'
            }), 400
            
        # Allow common audio formats
        allowed_audio = {'mp3', 'wav', 'ogg', 'm4a', 'flac'}
        if not ('.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_audio):
            return jsonify({
                'success': False,
                'message': 'Unsupported audio format'
            }), 400
            
        # Generate a unique ID for the resource
        resource_id = str(uuid.uuid4())
        filename = secure_filename(file.filename)
        file_ext = os.path.splitext(filename)[1]
        file_bytes = file.read()
        
        # Upload audio directly to Blob Storage without creating a local file
        blob_name = f"{project_id}/{resource_id}/{filename}"
        content_type = get_content_type(file_ext) or 'audio/mpeg'
        print(f"Uploading audio to Azure Blob Storage: {blob_name}")
        blob_url = upload_to_blob_storage_from_memory(file_bytes, blob_name, content_type)
        print(f"Blob URL: {blob_url[:50]}...")
        
        # Import the necessary functions from speech_to_summary module
        sys_path_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        models_path = os.path.join(sys_path_parent, '..', 'Models')
        sys.path.append(models_path)
        print(f"Added Models path to sys.path: {models_path}")
        
        # Import the summarization function only
        from speech_to_summary import start_transcription, poll_transcription, summarize_text
        
        # Use AssemblyAI to start transcription directly with the blob URL
        print(f"Starting transcription with blob URL: {blob_url}")
        transcript_id = start_transcription(blob_url)
        print(f"Transcription started with ID: {transcript_id}")
        
        # Poll for transcription results
        transcript = poll_transcription(transcript_id)
        print(f"Transcription completed, received {len(transcript)} characters")
        
        # Generate summary
        summary = summarize_text(transcript)
        print(f"Summary generated, received {len(summary)} characters")
        
        # Create resource data
        resource_data = {
            'id': resource_id,
            'project_id': project_id,
            'name': resource_name,
            'tagged_users': tagged_users,
            'created_at': datetime.utcnow().isoformat(),
            'created_by': request.headers.get('X-User-ID'),
            'type': 'audio',
            'file_name': filename,
            'context': transcript,
            'summary': summary,
            'url': blob_url,
            'content_type': content_type
        }
        
        # Save to Cosmos DB
        print(f"Saving audio resource to Cosmos DB with ID: {resource_id}")
        resources_container.create_item(resource_data)
        print("Audio resource saved successfully to Cosmos DB")
        
        return jsonify({
            'success': True,
            'message': 'Audio transcribed and saved successfully',
            'resource': {
                'id': resource_id,
                'name': resource_name,
                'transcript': transcript[:500] + '...' if len(transcript) > 500 else transcript,
                'summary': summary,
                'url': blob_url,
                'created_at': resource_data['created_at']
            }
        }), 201
        
    except Exception as e:
        print(f"ERROR in transcribe_audio_route: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'Error transcribing audio: {str(e)}'
        }), 500

def get_confluence_spaces():
    """Fetch all available spaces in Confluence."""
    spaces_url = f"{base_url}/rest/api/space"
    
    try:
        response = requests.get(
            spaces_url,
            auth=(email, api_token),
            headers={"Accept": "application/json"}
        )
        
        if response.status_code == 200:
            spaces = response.json().get('results', [])
            return [{"key": space['key'], "name": space['name']} for space in spaces]
        else:
            print(f"Failed to fetch spaces: Status {response.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching spaces: {str(e)}")
        return []

def get_confluence_pages(space_key):
    """Fetch all pages in a specific space."""
    api_endpoint = f"{base_url}/rest/api/content"
    
    params = {
        'expand': 'space',
        'limit': 100,
        'spaceKey': space_key
    }

    try:
        response = requests.get(
            api_endpoint,
            auth=(email, api_token),
            headers={"Accept": "application/json"},
            params=params
        )

        if response.status_code == 200:
            pages = response.json().get('results', [])
            return [{"id": page['id'], "title": page['title']} for page in pages]
        else:
            print(f"Failed to fetch pages: Status {response.status_code}")
            return []
    except Exception as e:
        print(f"Error fetching pages: {str(e)}")
        return []

def get_confluence_page_content(page_id, title):
    """Fetch Confluence page content and return as JSON."""
    content_url = f"{base_url}/rest/api/content/{page_id}"
    params = {
        "expand": "body.storage,space"
    }

    try:
        print(f"\n=== Fetching Confluence Page ===")
        print(f"URL: {content_url}")
        print(f"Params: {params}")
        
        response = requests.get(
            content_url,
            auth=(email, api_token),
            headers={"Accept": "application/json"},
            params=params
        )

        print(f"\n=== Response Details ===")
        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {response.headers}")
        print(f"Response Content Preview: {response.text[:500]}")

        if response.status_code == 200:
            content = response.json()
            print(f"\n=== Content Structure ===")
            print(f"Content Keys: {content.keys()}")
            
            if 'body' not in content:
                raise Exception("No 'body' field in response")
            if 'storage' not in content['body']:
                raise Exception("No 'storage' field in body")
            
            # Get the raw content
            raw_content = content['body']['storage']['value']
            print(f"\n=== Raw Content Preview ===")
            print(f"First 200 chars: {raw_content[:200]}")
            
            # Create a structured response
            result = {
                "title": title,
                "content": raw_content,
                "space_key": content['space']['key'],
                "version": content.get('version', {}).get('number', 1)
            }
            
            print(f"\n=== Final Result ===")
            print(f"Result Structure: {result.keys()}")
            print(f"Content Length: {len(raw_content)}")
            
            return result
        else:
            raise Exception(f"Failed to get content for '{title}': Status {response.status_code}, Response: {response.text}")
    except Exception as e:
        print(f"\n=== Error Details ===")
        print(f"Error: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        raise Exception(f"Error processing '{title}': {str(e)}")

@resources.route('/confluence/spaces', methods=['GET'])
def get_confluence_spaces_route():
    try:
        spaces = get_confluence_spaces()
        return jsonify({
            'success': True,
            'spaces': spaces
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@resources.route('/confluence/pages/<space_key>', methods=['GET'])
def get_confluence_pages_route(space_key):
    try:
        pages = get_confluence_pages(space_key)
        return jsonify({
            'success': True,
            'pages': pages
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@resources.route('/confluence/page/<page_id>', methods=['GET', 'OPTIONS'])
def get_confluence_page_route(page_id):
    if request.method == 'OPTIONS':
        # Handle preflight request
        response = jsonify({'status': 'ok'})
        response.headers.add('Access-Control-Allow-Origin', 'http://localhost:5173')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, x-user-id')
        response.headers.add('Access-Control-Allow-Methods', 'GET, OPTIONS')
        return response

    try:
        title = request.args.get('title')
        project_id = request.args.get('projectId')
        tagged_users = request.args.getlist('taggedUsers[]')
        user_id = request.headers.get('x-user-id')
        
        print(f"\n=== Processing Confluence Import ===")
        print(f"Project ID: {project_id}")
        print(f"Tagged Users: {tagged_users}")
        print(f"User ID: {user_id}")
        
        if not title:
            return jsonify({"error": "Missing title"}), 400
            
        content = get_confluence_page_content(page_id, title)
        
        # Construct the proper Confluence URL
        confluence_url = f"{base_url}/spaces/{content['space_key']}/pages/{page_id}"
        print(f"\n=== Generated Confluence URL ===")
        print(f"URL: {confluence_url}")
        
        # Create resource in database
        resource = {
            "id": f"confluence_{page_id}",
            "project_id": project_id,
            "name": f"Confluence: {title}",
            "tagged_users": tagged_users,
            "created_at": datetime.utcnow().isoformat(),
            "created_by": user_id or "system",
            "type": "confluence",
            "context": content['content'],
            "content_type": "application/json",
            "source_url": confluence_url,  # Use the constructed URL
            "metadata": {
                "space_key": content['space_key'],
                "version": content['version']
            }
        }
        
        print(f"\n=== Resource to be saved ===")
        print(f"Resource ID: {resource['id']}")
        print(f"Source URL: {resource['source_url']}")
        
        # Save to Cosmos DB
        try:
            container = cosmos_client.get_database_client('RequirementsDB').get_container_client('Resources')
            container.create_item(body=resource)
            print(f"Successfully saved Confluence page to database: {title}")
        except Exception as db_error:
            print(f"Error saving to database: {str(db_error)}")
            raise db_error
        
        response = jsonify({
            "success": True,
            "resource": resource
        })
        
        # Add CORS headers to the response
        response.headers.add('Access-Control-Allow-Origin', 'http://localhost:5173')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, x-user-id')
        return response
        
    except Exception as e:
        print(f"\n=== Error in get_confluence_page_route ===")
        print(f"Error: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        response = jsonify({"error": str(e)})
        response.headers.add('Access-Control-Allow-Origin', 'http://localhost:5173')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, x-user-id')
        return response, 500
