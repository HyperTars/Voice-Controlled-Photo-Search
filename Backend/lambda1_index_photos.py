import boto3
import json
import requests

from datetime import datetime

REGION = 'us-east-1'
ES_URL = 'https://vpc-photos-xllcimkwckbd67opw6tymh3uaq.us-east-1.es.amazonaws.com/photos/Photo'

def lambda_handler(event, context):
    client = boto3.client('rekognition')

    # detect the labels for each image
    for each_photo in event['Records']:
        bucket = each_photo['s3']['bucket']['name']
        key = each_photo['s3']['object']['key']
        
        rekog_result = client.detect_labels(
            Image = {
                'S3Object': {
                    'Bucket': bucket,
                    'Name': key
                }
            },
            MaxLabels = 10,
            MinConfidence = 85
        )
        print(rekog_result['Labels'])

    # Store a JSON index object in an ElasticSearch index
    json_obj = {
        "objectKey": key,
        "bucket": bucket,
        "createdTimestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "labels": []
    }
    for each_label in rekog_result['Labels']:
        json_obj["labels"].append(each_label['Name'])

    # send post request to add index to elasticsearch
    response = requests.post(ES_URL, data = json.dumps(json_obj).encode("utf-8"), headers = { "Content-Type": "application/json" })
    print(response.text)

    return {
        'statusCode': 200,
        'headers': {
            "Access-Control-Allow-Origin": "*"
        },
        'body': json.dumps("Photo lables added successfully!")
    }
