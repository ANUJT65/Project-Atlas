from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions, ContentSettings, BlobProperties
import pandas as pd
import urllib.parse
import os
from collections import Counter

# Enter credentials
account_name = 'barclaysstorage'
account_key = ''
container_name = 'data'

# Create a client to interact with blob storage
connect_str = f'DefaultEndpointsProtocol=https;AccountName={account_name};AccountKey={account_key};EndpointSuffix=core.windows.net'
blob_service_client = BlobServiceClient.from_connection_string(connect_str)

# Use the client to connect to the container
container_client = blob_service_client.get_container_client(container_name)

# Function to generate download URL with SAS token
def generate_download_url(blob_name, version_id=None):
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(hours=24),
        version_id=version_id
    )
    
    encoded_blob_name = urllib.parse.quote(blob_name)
    sas_url = f'https://{account_name}.blob.core.windows.net/{container_name}/{encoded_blob_name}?{sas_token}'
    if version_id:
        sas_url += f'&versionid={version_id}'
    return sas_url

# Function to generate view URL for browser-compatible files
def generate_view_url(blob_name, file_type, version_id=None):
    """Generate a URL that can be used to view the file in a browser if supported"""
    download_url = generate_download_url(blob_name, version_id)
    
    # For files that can be viewed directly in browser
    viewable_types = {
        'pdf': True,
        'jpg': True, 'jpeg': True, 'png': True, 'gif': True,
        'txt': True, 'csv': True,
        'mp4': True, 'mp3': True,
        'html': True, 'htm': True
    }
    
    if file_type.lower() in viewable_types:
        return download_url
    else:
        return None  # For file types that typically need to be downloaded first

# Function to upload a file to the container
def upload_file(local_file_path, enable_versioning=True):
    # Get just the file name from the path
    file_name = os.path.basename(local_file_path)
    
    # Get file extension to set content type
    file_ext = os.path.splitext(file_name)[1].lower()
    content_type = None
    
    # Set appropriate content type based on file extension
    if file_ext == '.pdf':
        content_type = 'application/pdf'
    elif file_ext == '.docx':
        content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    elif file_ext == '.xlsx':
        content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    elif file_ext == '.csv':
        content_type = 'text/csv'
    elif file_ext in ['.jpg', '.jpeg']:
        content_type = 'image/jpeg'
    elif file_ext == '.png':
        content_type = 'image/png'
    elif file_ext == '.mp3':
        content_type = 'audio/mpeg'
    elif file_ext == '.mp4':
        content_type = 'video/mp4'
    elif file_ext == '.txt':
        content_type = 'text/plain'
    elif file_ext == '.html' or file_ext == '.htm':
        content_type = 'text/html'
    
    # Create blob client for the new file
    blob_client = container_client.get_blob_client(file_name)
    
    # Set content settings if content type is determined
    content_settings = None
    if content_type:
        content_settings = ContentSettings(content_type=content_type)
    
    # Upload the file
    try:
        with open(local_file_path, "rb") as data:
            response = blob_client.upload_blob(
                data, 
                overwrite=True,
                content_settings=content_settings
            )
        version_id = response.get('version_id', None)
        print(f"File {file_name} uploaded successfully!")
        
        # Generate and return download URL for the uploaded file
        download_url = generate_download_url(file_name)
        print(f"Download URL: {download_url}")
        
        if version_id:
            print(f"Version ID: {version_id}")
            
        return True, download_url, version_id
    except Exception as e:
        print(f"Error uploading {file_name}: {str(e)}")
        return False, None, None

# Function to list versions of a blob
def list_blob_versions(blob_name):
    """List all versions of a specific blob"""
    try:
        # Get the container client with include_versions=True
        versions = []
        
        # List blobs including versions that match this name
        for blob in container_client.list_blobs(name_starts_with=blob_name, include=["versions"]):
            if blob.name == blob_name:
                version_info = {
                    'name': blob.name,
                    'version_id': blob.version_id,
                    'creation_time': blob.creation_time,
                    'last_modified': blob.last_modified,
                    'size_kb': blob.size / 1024,
                    'is_current_version': blob.is_current_version
                }
                versions.append(version_info)
        
        return versions
    except Exception as e:
        print(f"Error listing versions for {blob_name}: {str(e)}")
        return []

# Function to restore a previous version of a blob
def restore_blob_version(blob_name, version_id):
    """Restore a previous version of a blob by copying it over the current version"""
    try:
        # Create clients for source and destination
        source_blob_client = container_client.get_blob_client(blob=blob_name, version_id=version_id)
        destination_blob_client = container_client.get_blob_client(blob=blob_name)
        
        # Copy the old version to the current version
        destination_blob_client.start_copy_from_url(source_blob_client.url)
        print(f"Restored version {version_id} of {blob_name}")
        return True
    except Exception as e:
        print(f"Error restoring version {version_id} of {blob_name}: {str(e)}")
        return False

# Function to download a blob to local file
def download_blob(blob_name, local_path=None, version_id=None):
    # If no local path is specified, download to current directory with same name
    if local_path is None:
        local_path = os.path.join(os.getcwd(), blob_name)
    
    # Create blob client
    blob_client = container_client.get_blob_client(blob_name, version_id=version_id)
    
    try:
        # Download the blob
        with open(local_path, "wb") as download_file:
            download_file.write(blob_client.download_blob().readall())
        
        version_text = f" (version {version_id})" if version_id else ""
        print(f"Downloaded {blob_name}{version_text} to {local_path} successfully")
        return True
    except Exception as e:
        print(f"Error downloading {blob_name}: {str(e)}")
        return False

# Function to delete a blob
def delete_blob(blob_name, version_id=None, delete_all_versions=False):
    if delete_all_versions:
        blob_client = container_client.get_blob_client(blob_name)
        try:
            blob_client.delete_blob(delete_snapshots="include")
            print(f"Deleted {blob_name} and all its versions successfully")
            return True
        except Exception as e:
            print(f"Error deleting {blob_name} and its versions: {str(e)}")
            return False
    else:
        blob_client = container_client.get_blob_client(blob_name, version_id=version_id)
        try:
            if version_id:
                blob_client.delete_blob(version_id=version_id)
                print(f"Deleted version {version_id} of {blob_name} successfully")
            else:
                blob_client.delete_blob()
                print(f"Deleted current version of {blob_name} successfully")
            return True
        except Exception as e:
            print(f"Error deleting {blob_name}: {str(e)}")
            return False

# Demonstrate versioning with a sample file
def demonstrate_versioning():
    print("\n=== DEMONSTRATING BLOB VERSIONING ===")
    print("This will upload multiple versions of a file and show how to access them")
    print("-" * 50)
    
    # 1. Create a simple text file with version 1 content
    test_file = "version_test.txt"
    with open(test_file, "w") as f:
        f.write("This is version 1 of the test file.")
    
    # 2. Upload the file (version 1)
    print("\nUploading version 1...")
    success, url, version_1 = upload_file(test_file)
    
    # 3. Update the file content to version 2
    with open(test_file, "w") as f:
        f.write("This is version 2 of the test file with more content.")
    
    # 4. Upload the updated file (version 2)
    print("\nUploading version 2...")
    success, url, version_2 = upload_file(test_file)
    
    # 5. Update the file content to version 3
    with open(test_file, "w") as f:
        f.write("This is version 3 of the test file with even more content and changes.")
    
    # 6. Upload the updated file (version 3)
    print("\nUploading version 3...")
    success, url, version_3 = upload_file(test_file)
    
    # 7. List all versions of the file
    print("\nListing all versions of the file:")
    versions = list_blob_versions(test_file)
    
    print(f"\nFound {len(versions)} versions of {test_file}:")
    for i, version in enumerate(versions):
        print(f"\nVersion {i+1}:")
        print(f"  Version ID: {version['version_id']}")
        print(f"  Created: {version['creation_time']}")
        print(f"  Size: {version['size_kb']:.2f} KB")
        print(f"  Current version: {'Yes' if version['is_current_version'] else 'No'}")
        
        # Generate download URL for this version
        version_url = generate_download_url(test_file, version['version_id'])
        print(f"  Download URL: {version_url}")
    
    # 8. Restore version 1 (optional demonstration)
    print("\nRestoring version 1...")
    restore_blob_version(test_file, version_1)
    
    # 9. Clean up by deleting the local test file
    os.remove(test_file)
    print(f"\nDeleted local file {test_file}")
    print("\nVersioning demonstration complete!")
    print("=" * 50)

print("\n=== FILES IN THE CONTAINER ===")
print(f"Container name: {container_name}")
print("-" * 50)

# List all blobs in the container and display detailed information
file_count = 0
file_types = Counter()  # Counter to track file extensions
blob_info = []  # Store blob information for sorting

for blob in container_client.list_blobs():
    file_count += 1
    file_type = blob.name.split('.')[-1].lower() if '.' in blob.name else 'unknown'
    size_kb = blob.size / 1024
    
    # Generate URLs
    download_url = generate_download_url(blob.name)
    view_url = generate_view_url(blob.name, file_type)
    
    # Add to file type counter
    file_types[file_type] += 1
    
    # Store blob info for display
    blob_info.append({
        'name': blob.name,
        'type': file_type,
        'size_kb': size_kb,
        'last_modified': blob.last_modified,
        'download_url': download_url,
        'view_url': view_url
    })
    
    print(f"{file_count}. {blob.name}")
    print(f"   Type: {file_type.upper()}")
    print(f"   Size: {size_kb:.2f} KB")
    print(f"   Last modified: {blob.last_modified}")
    print(f"   Download URL: {download_url}")
    if view_url:
        print(f"   View in Browser: {view_url}")
    print("-" * 50)

# Print file count statistics
print(f"\nTotal files: {file_count}")
print("\n=== FILE TYPE COUNTS ===")
for file_type, count in sorted(file_types.items()):
    print(f"{file_type.upper()}: {count} files")
print("=" * 50)

# Group files by type
print("\n=== FILES GROUPED BY TYPE ===")
for file_type in sorted(file_types.keys()):
    print(f"\n{file_type.upper()} FILES:")
    print("-" * 30)
    type_count = 0
    for blob in sorted([b for b in blob_info if b['type'] == file_type], key=lambda x: x['name']):
        type_count += 1
        print(f"{type_count}. {blob['name']}")
        print(f"   Size: {blob['size_kb']:.2f} KB")
        print(f"   Download URL: {blob['download_url']}")
        if blob.get('view_url'):
            print(f"   View in Browser: {blob['view_url']}")
    print(f"Total {file_type.upper()} files: {file_types[file_type]}")
    print("-" * 30)

# Upload a file example
upload_file(r"C:\Users\Suraj Chavan\Downloads\research_paper.pdf")

# Run the versioning demonstration
demonstrate_versioning()

print("\n=== USAGE EXAMPLES ===")
print("# Upload a file")
print("upload_file('C:/path/to/your/file.pdf')")
print("\n# List versions of a file")
print("list_blob_versions('filename.pdf')")
print("\n# Download a specific version")
print("download_blob('filename.pdf', version_id='2025-04-17T16:45:23.1234567Z')")
print("\n# Restore a previous version")
print("restore_blob_version('filename.pdf', '2025-04-17T16:45:23.1234567Z')")
print("\n# Delete a specific version")
print("delete_blob('filename.pdf', version_id='2025-04-17T16:45:23.1234567Z')")
print("\n# Delete a file and all its versions")
print("delete_blob('filename.pdf', delete_all_versions=True)")
print("=" * 50)
