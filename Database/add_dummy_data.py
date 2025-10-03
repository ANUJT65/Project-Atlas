import os
import json
import asyncio
from datetime import datetime
from azure.cosmos.aio import CosmosClient
from azure.cosmos.exceptions import CosmosResourceExistsError
from azure.cosmos.partition_key import PartitionKey
from azure.storage.blob import BlobServiceClient, ContentSettings
import uuid

# Cosmos DB Configuration
COSMOS_URL = "https://barclaysdb.documents.azure.com:443/"
COSMOS_KEY = ""
DATABASE_NAME = 'RequirementsDB'

# Blob Storage Configuration
BLOB_CONNECTION_STRING = 'DefaultEndpointsProtocol=https;AccountName=barclaysstorage;AccountKey=w7fJMnkuaZR4RX9LJbTRld8v90S6KDupj1BDHNZ1+Ch9Do7Et56nQKAd2HVXJqgZYEVbcGY/CGRj+AStE2NEXQ==;EndpointSuffix=core.windows.net'
BLOB_CONTAINER_NAME = 'requirements-data'

# Dummy data for testing
DUMMY_USERS = [
    {"id": "user1", "email": "client@example.com", "name": "John Client", "roles": ["Client"]},
    {"id": "user2", "email": "ba@example.com", "name": "Sarah BA", "roles": ["BA"]},
    {"id": "user3", "email": "sde@example.com", "name": "Mike SDE", "roles": ["SDE"]},
    {"id": "user4", "email": "devops@example.com", "name": "Lisa DevOps", "roles": ["DevOps"]}
]

DUMMY_PROJECT = {
    "id": "proj1",
    "name": "E-Commerce Platform",
    "created_at": datetime.utcnow().isoformat(),
    "created_by": "user1",
    "status": "active",
    "integrations": {
        "jira_project_key": "ECOM",
        "github_repo_url": "https://github.com/org/ecommerce",
        "jira_api_key": "dummy-jira-key",
        "github_api_key": "dummy-github-key"
    }
}

DUMMY_TEAMS = [
    {
        "id": "team1",
        "project_id": "proj1",
        "role": "Client",
        "members": [{"user_id": "user1", "email": "client@example.com", "name": "John Client"}],
        "created_at": datetime.utcnow().isoformat()
    },
    {
        "id": "team2",
        "project_id": "proj1",
        "role": "BA",
        "members": [{"user_id": "user2", "email": "ba@example.com", "name": "Sarah BA"}],
        "created_at": datetime.utcnow().isoformat()
    }
]

DUMMY_RESOURCES = [
    {
        "id": "res1",
        "project_id": "proj1",
        "team_id": "team1",
        "uploaded_by": "user1",
        "file_name": "client_requirements.pdf",
        "file_type": "PDF",
        "blob_url": "https://barclaysstorage.blob.core.windows.net/requirements-data/client_requirements.pdf",
        "metadata": {
            "meeting_date": datetime.utcnow().isoformat(),
            "attendees": ["John Client", "Sarah BA"],
            "main_discussion_points": ["User Interface", "Payment Integration"]
        },
        "version": 1,
        "created_at": datetime.utcnow().isoformat()
    }
]

DUMMY_REQUIREMENT_DOCS = [
    {
        "id": "req1",
        "project_id": "proj1",
        "team_id": "team1",
        "role": "Client",
        "content": "Client requirements for e-commerce platform...",
        "version": 1,
        "status": "draft",
        "created_at": datetime.utcnow().isoformat(),
        "resource_ids": ["res1"]
    }
]

DUMMY_STANDARD_DOCS = [
    {
        "id": "std1",
        "project_id": "proj1",
        "doc_type": "SRS",
        "content": "Software Requirements Specification...",
        "version": 1,
        "status": "draft",
        "created_at": datetime.utcnow().isoformat(),
        "requirement_doc_ids": ["req1"]
    }
]

DUMMY_USER_STORIES = [
    {
        "id": "story1",
        "project_id": "proj1",
        "standard_doc_id": "std1",
        "title": "User Login",
        "description": "As a user, I want to log in to the system...",
        "priority": "Must",
        "jira_issue_id": "ECOM-1",
        "status": "To Do",
        "created_at": datetime.utcnow().isoformat()
    }
]

DUMMY_TEST_CASES = [
    {
        "id": "test1",
        "project_id": "proj1",
        "standard_doc_id": "std1",
        "user_story_id": "story1",
        "title": "Valid Login Test",
        "description": "Test login with valid credentials",
        "test_steps": ["Enter valid email", "Enter valid password", "Click login"],
        "expected_results": "User should be logged in successfully",
        "github_issue_id": "ECOM-TEST-1",
        "status": "To Do",
        "created_at": datetime.utcnow().isoformat()
    }
]

async def create_cosmos_containers(database):
    """Create all required containers in Cosmos DB"""
    containers = {
        'Users': '/id',
        'Projects': '/id',
        'Teams': '/project_id',
        'Resources': '/project_id',
        'RequirementDocs': '/project_id',
        'StandardDocs': '/project_id',
        'UserStories': '/project_id',
        'TestCases': '/project_id'
    }
    
    created_containers = {}
    for container_name, partition_key in containers.items():
        try:
            container = await database.create_container(
                id=container_name,
                partition_key=PartitionKey(path=partition_key)
            )
            print(f"Created container: {container_name}")
            created_containers[container_name] = container
        except CosmosResourceExistsError:
            container = database.get_container_client(container_name)
            print(f"Container {container_name} already exists")
            created_containers[container_name] = container
    
    return created_containers

async def add_dummy_data_to_cosmos(containers):
    """Add dummy data to all containers"""
    # Add users
    for user in DUMMY_USERS:
        await containers['Users'].upsert_item(user)
    
    # Add project
    await containers['Projects'].upsert_item(DUMMY_PROJECT)
    
    # Add teams
    for team in DUMMY_TEAMS:
        await containers['Teams'].upsert_item(team)
    
    # Add resources
    for resource in DUMMY_RESOURCES:
        await containers['Resources'].upsert_item(resource)
    
    # Add requirement docs
    for doc in DUMMY_REQUIREMENT_DOCS:
        await containers['RequirementDocs'].upsert_item(doc)
    
    # Add standard docs
    for doc in DUMMY_STANDARD_DOCS:
        await containers['StandardDocs'].upsert_item(doc)
    
    # Add user stories
    for story in DUMMY_USER_STORIES:
        await containers['UserStories'].upsert_item(story)
    
    # Add test cases
    for test in DUMMY_TEST_CASES:
        await containers['TestCases'].upsert_item(test)

def create_dummy_files():
    """Create dummy files for blob storage"""
    # Create a dummy PDF file with more content
    dummy_pdf_path = "dummy_client_requirements.pdf"
    with open(dummy_pdf_path, "w", encoding="utf-8") as f:
        f.write("""DUMMY PDF CONTENT
This is a dummy PDF file for testing purposes.

Project: E-Commerce Platform
Client Requirements:
1. User Interface
   - Clean, modern design
   - Mobile responsive
   - Easy navigation

2. Payment Integration
   - Support for major credit cards
   - Secure payment processing
   - Order confirmation emails

3. Product Management
   - Easy product upload
   - Inventory tracking
   - Price management

4. User Management
   - User registration and login
   - Profile management
   - Order history

This document is for testing the requirements engineering platform.
""")
    
    return [dummy_pdf_path]

def upload_to_blob_storage(file_paths):
    """Upload dummy files to blob storage"""
    blob_service_client = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
    
    # Check if container exists, create if it doesn't
    container_exists = False
    for container in blob_service_client.list_containers():
        if container.name == BLOB_CONTAINER_NAME:
            container_exists = True
            break
    
    if not container_exists:
        print(f"Creating container: {BLOB_CONTAINER_NAME}")
        blob_service_client.create_container(BLOB_CONTAINER_NAME)
    
    container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
    
    uploaded_files = []
    for file_path in file_paths:
        file_name = os.path.basename(file_path)
        blob_client = container_client.get_blob_client(file_name)
        
        # Set content type based on file extension
        content_type = 'application/pdf' if file_path.endswith('.pdf') else 'text/plain'
        content_settings = ContentSettings(content_type=content_type)
        
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True, content_settings=content_settings)
        
        uploaded_files.append({
            "name": file_name,
            "url": blob_client.url
        })
        
        # Clean up local file
        os.remove(file_path)
    
    return uploaded_files

async def main():
    # Create Cosmos DB client and database
    async with CosmosClient(COSMOS_URL, credential=COSMOS_KEY) as client:
        try:
            database = await client.create_database(DATABASE_NAME)
            print(f"Created database: {DATABASE_NAME}")
        except CosmosResourceExistsError:
            database = client.get_database_client(DATABASE_NAME)
            print(f"Database {DATABASE_NAME} already exists")
        
        # Create containers and add dummy data
        containers = await create_cosmos_containers(database)
        await add_dummy_data_to_cosmos(containers)
    
    # Create and upload dummy files to blob storage
    dummy_files = create_dummy_files()
    uploaded_files = upload_to_blob_storage(dummy_files)
    print("\nUploaded files to blob storage:")
    for file in uploaded_files:
        print(f"- {file['name']}: {file['url']}")

if __name__ == "__main__":
    asyncio.run(main()) 
