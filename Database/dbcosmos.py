import os
import json
import asyncio
from azure.cosmos.aio import CosmosClient
from azure.cosmos.exceptions import CosmosResourceExistsError, CosmosHttpResponseError
from azure.cosmos.partition_key import PartitionKey

URL = "https://barclaysdb.documents.azure.com:443/"
KEY = ""

# Create all database operations inside an async function
async def cosmos_operations():
    # Create the client
    async with CosmosClient(URL, credential=KEY) as client:
        DATABASE_NAME = 'ToDoList'
        CONTAINER_NAME = 'Items1'
        
        # Create a database
        try:
            database = await client.create_database(DATABASE_NAME)
            print(f"Created database: {DATABASE_NAME}")
        except CosmosResourceExistsError:
            database = client.get_database_client(DATABASE_NAME)
            print(f"Database {DATABASE_NAME} already exists")
        
        # Create a container
        try:
            container = await database.create_container(
                id=CONTAINER_NAME, 
                partition_key=PartitionKey(path='/id', kind='Hash')
            )
            print(f"Created container: {CONTAINER_NAME}")
        except CosmosResourceExistsError:
            container = database.get_container_client(CONTAINER_NAME)
            print(f"Container {CONTAINER_NAME} already exists")
        
        # Create records
        print("Creating records...")
        for i in range(1, 10):
            await container.upsert_item({
                'id': f'item{i}',
                'TYkey': '1',
                'productName': 'Widget',
                'productModel': f'Model {i}'
            })
            print(f"Created item{i}")
        
        # Query the database - using parameters object instead of enable_cross_partition_query
        print("\nQuerying for item3...")
        query = "SELECT * FROM Items1 i WHERE i.id=@itemId"
        parameters = [{"name": "@itemId", "value": "item3"}]
        
        # Using query_items with parameters
        async for item in container.query_items(
            query=query,
            parameters=parameters,
            partition_key="item3"  # If you know the partition key, use it
        ):
            print(json.dumps(item, indent=2))
        
        # Query by product model - using parameters
        print("\nQuerying for Model 2...")
        model_query = "SELECT * FROM Items1 i WHERE i.productModel = @model"
        model_parameters = [{"name": "@model", "value": "Model 2"}]
        
        # Using query_items with parameters
        items_to_delete = []
        async for item in container.query_items(
            query=model_query,
            parameters=model_parameters
        ):
            items_to_delete.append(item)
            print(json.dumps(item, indent=2))
        
        # Demonstrate deleting items (commented out by default)
        print("\nItems that would be deleted if uncommented:")
        for item in items_to_delete:
            print(f"  {item['id']} (Model {item['productModel']})")
            # Uncomment the next line to actually delete the items
            # await container.delete_item(item, partition_key=item['id'])
            # print(f"Deleted item with id: {item['id']}")

# Run the async function
asyncio.run(cosmos_operations())
