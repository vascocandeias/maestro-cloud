import boto3
import json
import decimal
import time

dynamodb = boto3.resource('dynamodb')

# Helper class to convert a DynamoDB item to JSON.
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
      if isinstance(o, decimal.Decimal):
        if o % 1 != 0:
          return float(o)
        else:
          return int(o)
      return super(DecimalEncoder, self).default(o)
      
      
def lambda_handler(event, context):
  """Retrieve a result or network if it is ready"""
  
  table = dynamodb.Table(event.pop("table"))
  
  response = table.get_item(Key=event)
  
  if not response.get("Item"):
    return {
      'statusCode': 404
    }

  while not response.get("Item").get("done") or response.get("Item").get("pending"):
    response = table.get_item(Key=event)
    time.sleep(1)
    
  return {
    'statusCode': 200,
    'body': json.dumps(response["Item"], cls=DecimalEncoder)
  }
