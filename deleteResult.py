import boto3
import json
import os
from boto3.dynamodb.conditions import Attr
from boto3.dynamodb.conditions import Key

IDENTITY_POOL_ID = os.environ['IDENTITY_POOL_ID']
COGNITO_USER_POOL = os.environ['COGNITO_USER_POOL']    

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['RESULTS'])
networksTable = dynamodb.Table(os.environ['NETWORKS'])
datasetsTable = dynamodb.Table(os.environ['DATASETS'])
s3 = boto3.resource('s3')
bucket = s3.Bucket(os.environ['S3_BUCKET'])
cognito = boto3.client('cognito-identity')

      
def lambda_handler(event, context):
    """Delete result and corresponding files"""
 
    token = event["headers"]["Authorization"].replace("Bearer ", "", 1)
    event = event["body"]

    items = table.delete_item(
        Key={
            "userId": event["userId"],
            "requestId": event["requestId"]
        },
        ReturnValues="ALL_OLD"
    )

    if not items.get("Attributes"):
        return None
        
    networksTable.delete_item(
        Key={
            "userId": event["userId"],
            "datasetId": event["requestId"] + "_dbn.ser"
        }
    )
    
    datasets = datasetsTable.query(
        KeyConditionExpression = Key('userId').eq(event['userId']),
        ProjectionExpression = "datasetId"
    )

    results = set()
    
    for dataset in datasets.get("Items"):
        results.add(dataset["datasetId"])
        
    toDelete = []
    
    Logins = {
        COGNITO_USER_POOL: token
    }
    
    response = cognito.get_id(
        IdentityPoolId=IDENTITY_POOL_ID,
        Logins=Logins
    )
    
    files = items.get("Attributes").get("files")
    
    for item in files:
        if files[item]["datasetId"] not in results:
            toDelete.append({
                    'Key': 'private/' + response["IdentityId"] + '/' + files[item]["datasetId"]
                })
                
    if not toDelete:
        return {
            'statusCode': 200
        }
        
    response = bucket.delete_objects(
        Delete={
            'Objects': toDelete,
            'Quiet': True
        }
    )
    
    return {
        'statusCode': 200
    }