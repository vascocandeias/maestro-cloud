import boto3
from botocore.exceptions import ClientError
import time
import decimal
from jsoncomment import JsonComment
import json
import os

tables = {
    "datasets": os.environ.get("DATASETS"),
    "networks": os.environ.get("NETWORKS")
}

RESULTS_TABLE = os.environ.get("RESULTS")
S3_BUCKET = os.environ.get("S3_BUCKET")

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
client = boto3.client('ses')
DAYS = 3 # TTL for items in database
parser = JsonComment(json)
TIMEOUT = 60*60*24*3 # Timeout of 3 days


def get_user_table_id(user):
    return user["S3id"]

def download_file(user, filename, fd):
    filename = "private/" + user["S3id"] + '/' + filename
    s3.download_fileobj(S3_BUCKET, filename, fd)

def send_email(address, body, subject, sender):

    CHARSET = "UTF-8"
    
    try:
        response = client.send_email(
            Destination={
                'ToAddresses': [
                    address,
                ],
            },
            Message={
                'Body': {
                    'Text': {
                        'Charset': CHARSET,
                        'Data': body,
                    },
                },
                'Subject': {
                    'Charset': CHARSET,
                    'Data': subject,
                },
            },
            Source=sender,
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])

def parse_output(output):
    try:
        return parser.loads(output, parse_float=decimal.Decimal)
    except:
        return output

def writeOutput(item, user, id):

    key = {
        'userId': user["dynamoDBid"],
        'requestId': id
    }

    table = dynamodb.Table(RESULTS_TABLE)

    item["TTL"] = int(time.time() + DAYS*24*60*60)
    update_expression = 'SET {}'.format(','.join(f'#{k}=:{k}' for k in item))
    expression_attribute_values = {f':{k}': v for k, v in item.items()}
    expression_attribute_names = {f'#{k}': k for k in item}
    condition_expression = "#done=:cond_done or #errors=:cond_error"
    expression_attribute_values[":cond_done"] = False
    expression_attribute_values[":cond_error"] = True

    try:
        response = table.update_item(
            Key=key,
            ConditionExpression=condition_expression,
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_attribute_values,
            ExpressionAttributeNames=expression_attribute_names,
            ReturnValues='ALL_OLD',
        )
        return response
    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException :
        return False


def upload_file(data, user, id):
    s3.upload_fileobj(data, S3_BUCKET, 'private/' + user["S3id"] + "/" + id)

def get_metadata(table, user, id):
    table = tables.get(table)

    if table:
        data = dynamodb.Table(table).get_item(Key={
            "userId": user["dynamoDBid"],
            "datasetId": id
        })
    else:
        return None

    return data.get("Item")


def post_metadata(table, user, requestId, datasetId, datasetName, content):
    tableName = tables.get(table)

    if tableName:
        dynamodb.Table(tableName).put_item(
            Item={
                "userId": user["dynamoDBid"],
                "datasetId": datasetId,
                "datasetName": datasetName,
                "requestId": requestId,
                "TTL": int(time.time() + DAYS*24*60*60),
                **content
            }
        )
    
    return {
        "datasetName": datasetName,
        "datasetId": datasetId
    }


def update_result(files, user, requestId):

    key = {
        'userId': user["dynamoDBid"],
        'requestId': requestId
    }

    table = dynamodb.Table(RESULTS_TABLE)

    update_expression = 'SET files=:files,pending=:pending,#TTL=:TTL'
    expression_attribute_names = {'#TTL': 'TTL'}
    expression_attribute_values = {
        ':files': files,
        ':pending': False,
        ':TTL': int(time.time() + DAYS*24*60*60)
    }

    response = table.update_item(
        Key=key,
        UpdateExpression=update_expression,
        ExpressionAttributeValues=expression_attribute_values,
        ExpressionAttributeNames=expression_attribute_names,
        ReturnValues='ALL_OLD',
    )

    return response