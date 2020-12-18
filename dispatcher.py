import boto3
import datetime
import json
import os
import time


QUEUE_NAME = os.environ['QUEUE_NAME']
IDENTITY_POOL_ID = os.environ['IDENTITY_POOL_ID']
COGNITO_USER_POOL = os.environ['COGNITO_USER_POOL']
AMI = os.environ['AMI']
INSTANCE_TYPE = os.environ['INSTANCE_TYPE']
IAM_ARN = os.environ['IAM_ARN']

DAYS = 3

ec2 = boto3.client('ec2')
client = boto3.client('sqs')
url = client.get_queue_url(QueueName=QUEUE_NAME).get('QueueUrl')
sqs = boto3.resource('sqs')
queue = sqs.Queue(url)
cognito = boto3.client('cognito-identity')
cognito_idp = boto3.client('cognito-idp')
dynamodb = boto3.resource('dynamodb')
output_table = dynamodb.Table(os.environ["RESULTS"])
lambda_client = boto3.client('lambda')

def add_identity_id(token, sub):
    Logins = {
        COGNITO_USER_POOL: token
    }
    
    id = cognito.get_id(
         IdentityPoolId=IDENTITY_POOL_ID,
         Logins=Logins
    ).get("IdentityId")
    
    cognito_idp.admin_update_user_attributes(
        UserPoolId=COGNITO_USER_POOL.split("/")[1],
        Username=sub,
        UserAttributes=[{
            'Name':'custom:identity_id','Value':id
        }]
    )    
    
    return id
    


def lambda_handler(event, context):
    """Create result, launch lambda worker, enqueue request and launch EC2"""
        
    token = event["headers"]["Authorization"].replace("Bearer ", "", 1)
   
    arr = event["body"]["api"]

    for key, value in arr.items():
        event["body"]["original"][key] = value
        

    event = event["body"]["original"]
    
    if event["userId"]["S3id"] == '':
        event["userId"]['S3id'] = add_identity_id(token, event["userId"]["dynamoDBid"])

    item = {
        'userId': event["userId"]["dynamoDBid"],
        'requestId': event.get("requestId"),
        'requestName': event.get("requestName"),
        'done': False,
        'errors': False,
        'TTL': int(time.time() + DAYS*24*60*60)
    }
    
    output_table.put_item(
        Item = item
    )
    
    event["link"] = os.environ["WEBSITE_URL"]
    event["time"] = datetime.datetime.utcnow().isoformat()
    
    lambda_client.invoke(
        FunctionName='lambda-broker',
        InvocationType='Event',
        Payload=json.dumps(event)
    )
    
    queue.send_message(MessageBody=json.dumps(event), MessageGroupId=event["requestId"])
    
    init_script = """#!/bin/bash
if [ $UID -eq 0 ]; then
  sudo chmod 777 "$0"
  exec su ec2-user "$0"
fi
cd /home/ec2-user
sudo yum update -y
sudo amazon-linux-extras install -y docker
sudo service docker start &> logs-docker-start
sudo docker run --rm -e DEFAULT_EMAIL={} -e RESULTS={} -e DATASETS={} -e NETWORKS={} -e S3_BUCKET={} -e QUEUE={} -e AWS_DEFAULT_REGION={} quay.io/vascocandeias/worker &> logs-docker-run
echo finished > finished
sudo halt""".format(os.environ["DEFAULT_EMAIL"], os.environ["RESULTS"], os.environ["DATASETS"], os.environ["NETWORKS"], os.environ["S3_BUCKET"], os.environ["QUEUE_NAME"], os.environ["AWS_REGION"])

    try:
        instance = ec2.run_instances(
            ImageId=AMI,
            InstanceType=INSTANCE_TYPE,
            MinCount=1, # required by boto
            MaxCount=1,
            InstanceInitiatedShutdownBehavior='terminate', # make shutdown in script terminate ec2
            IamInstanceProfile={"Arn":IAM_ARN},
            UserData=init_script # file to run on instance init.
        )
    except Exception as e:
        print(e)
    
    return {
      'statusCode': 200,
      'body': event['requestId']
    }