import boto3
import json
import os
from boto3.dynamodb.conditions import Attr
from boto3.dynamodb.conditions import Key

IDENTITY_POOL_ID = os.environ['IDENTITY_POOL_ID']
COGNITO_USER_POOL = os.environ['COGNITO_USER_POOL']    
COGNITO_POOL_ID = os.environ['COGNITO_POOL_ID']    

dynamodb = boto3.resource('dynamodb')
tables = [
    dynamodb.Table(os.environ["RESULTS"]),
    dynamodb.Table(os.environ["DATASETS"]),
    dynamodb.Table(os.environ["NETWORKS"]),
    dynamodb.Table(os.environ["OTHERS"])
]
s3 = boto3.resource('s3')
bucket = s3.Bucket(os.environ["S3_BUCKET"])
cognito = boto3.client('cognito-identity')
cognitoIdp = boto3.client('cognito-idp')

      
def lambda_handler(event, context):
    """Delete user and everything he owns"""
    
    token = event["headers"]["Authorization"].replace("Bearer ", "", 1)
    event = event["body"]
    
    for table in tables:
        if table == tables[0]:
            expression = "userId, requestId"
        else:
            expression = "userId, datasetId"
            
        datasets = table.query(
            KeyConditionExpression = Key('userId').eq(event['userId']),
            ProjectionExpression = expression
        )
        
        with table.batch_writer() as batch:
            for item in datasets['Items']:
                batch.delete_item(Key=item)
                
                
    Logins = {
        COGNITO_USER_POOL: token
    }
    
    response = cognito.get_id(
        IdentityPoolId=IDENTITY_POOL_ID,
        Logins=Logins
    )
    
    toDelete  = s3.meta.client.list_objects(Bucket=os.environ["S3_BUCKET"], Prefix='private/' + response["IdentityId"] + '/')
    
    deleteKeys = {'Objects' : []}
    deleteKeys['Objects'] = [{'Key' : k} for k in [obj['Key'] for obj in toDelete.get('Contents', [])]]
    
    if deleteKeys["Objects"]: bucket.delete_objects(Delete=deleteKeys)

    response = cognito.delete_identities(
        IdentityIdsToDelete=[
            response["IdentityId"]
        ]
    )
    
    response = cognitoIdp.admin_delete_user(
        UserPoolId=COGNITO_POOL_ID,
        Username=event["userId"]
    )
    
    return {
        'statusCode': 200
    }