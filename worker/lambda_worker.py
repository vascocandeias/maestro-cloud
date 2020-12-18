import common

def lambda_handler(event, context):
    """Lambda worker main function"""

    common.exec(event)
    
    return
