import time
import boto3
import json
import common
import os

QUEUE = os.environ.get("QUEUE")

client = boto3.client('sqs')
url = client.get_queue_url(QueueName=QUEUE).get('QueueUrl')
sqs = boto3.resource('sqs')
queue = sqs.Queue(url)

def getMessage(start):

    msg = queue.receive_messages()

    if msg:
        msg = msg[0]
        print("Retrieved queue message")
    else:
        print("Queue timed out")
        return None

    body = json.loads(msg.body)
    msg.delete()

    return body


def run():
    """Loop until message is received or queue times out and execute task"""
    start = common.log(time.time(), "Getting from queue")
    body = getMessage(start)

    while body != None:
        start = common.log(start, "Retrieved from queue")
        common.exec(body)
        body = getMessage(start)

if __name__ == '__main__':
    run()
