import boto3
import json
import os

IDENTITY_POOL_ID = os.environ['IDENTITY_POOL_ID']
COGNITO_USER_POOL = os.environ['COGNITO_USER_POOL']
S3_BUCKET = os.environ['S3_BUCKET']


dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE'])
s3 = boto3.resource('s3')
bucket = s3.Bucket(S3_BUCKET)
cognito = boto3.client('cognito-identity')

      
def lambda_handler(event, context):
    """Delete a file from the table corresponding to the TABLE environment variable"""
    
    token = event["headers"]["Authorization"].replace("Bearer ", "", 1)
    event = event["body"]

    table.delete_item(Key={
        "userId": event["userId"],
        "datasetId": event["datasetId"]
    })
    
    Logins = {
        COGNITO_USER_POOL: token
    }
    
    response = cognito.get_id(
        IdentityPoolId=IDENTITY_POOL_ID,
        Logins=Logins
    )
    
    response = bucket.delete_objects(
        Delete={
            'Objects': [
                {
                    'Key': 'private/' + response["IdentityId"] + '/' + event['datasetId']
                },
            ],
            'Quiet': True
        },
    )
    
    return {
        'statusCode': 200
    }