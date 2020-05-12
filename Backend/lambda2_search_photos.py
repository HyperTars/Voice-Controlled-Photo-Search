import json
import boto3
import os
import sys
import uuid
import time
import requests

# https://github.com/NikhilNar/PhotoAlbum/blob/3648e5e3bdb910fcee084abcc2497ea64a43537c/lambda-functions/image_search.py
# https://github.com/ayush159/NLP-Controlled-Photo-Album/blob/master/LambdaFunctions/search-photos.py
# https://github.com/hisenberg08/aws-photo-search-app/blob/master/search-elastic.py
# https://github.com/MercuryTian/AWS-AI-Photo-Album-Web-Application/blob/master/Lambda/search-photos.py

ES_HOST = 'https://vpc-photos-xllcimkwckbd67opw6tymh3uaq.us-east-1.es.amazonaws.com'
REGION = 'us-east-1'
BOT_NAME = 'ai_search'
BOT_ALIAS = 'ai_search'
S3_BUCKET = 'photos-s3-bucket'
HEADERS = {"Content-Type": "application/json"}
LEX_USER_ID = 'user'

ES_INDEX = 'photos'
ES_TYPE = 'Photo'

S3_VOICE = 'test.mp3'
S3_TEXT = 'test.txt'

transcribe_client = boto3.client('transcribe')
lex_client = boto3.client('lex-runtime')
s3_client = boto3.client('s3')

def get_url(key):
	url = ES_HOST + '/' + ES_INDEX + '/' + ES_TYPE + '/_search?q=' + key.lower()
	print('get url:', url)
	return url

def get_slots(query):
	print('get_slots: query:{}'.format(query))
	lex_response = lex_client.post_text(
		botName=BOT_NAME,
		botAlias=BOT_ALIAS,
		userId=LEX_USER_ID,
		inputText=query
	)
	print('get_slots: Lex RESPONSE --- {}'.format(json.dumps(lex_response)))
	# res = lex_response['currentIntent']['slots']
	if 'slots' in lex_response.keys():
		res = lex_response['slots'], True
	else:
		res = {}, False
	return res

def get_response(code, body):
	response = {
		'statusCode': code,
		'headers': {
			'Content-Type': 'application/json',
			'Access-Control-Allow-Origin': '*',
			'Access-Control-Allow-Methods': 'GET, POST, PUT',
			'Access-Control-Allow-Headers': 'Content-Type'
		},
		'body': json.dumps(body),
		'isBase64Encoded': False
	}
	print('get_response:', response)
	return response

def search_intent(slots):
	img_list = []
	objKeys = set()
	print('search intent, slots: {}'.format(slots))
	for i, tag in slots.items():
		if tag:
			tag = plural(tag)
			url = get_url(tag)
			print('ES URL --- {}'.format(url))

			es_response = requests.get(url, headers=HEADERS).json()
			print('ES RESPONSE --- {}'.format(json.dumps(es_response)))

			if 'hits' in es_response:
				es_src = es_response['hits']['hits']
				print('ES HITS --- {}'.format(json.dumps(es_src)))
				for photo in es_src:
					labels = [obj.lower() for obj in photo['_source']['labels']]
					if tag.lower() in labels:
						objKey = photo['_source']['objectKey']
						if objKey not in objKeys:
							objKeys.add(objKey)
							img_url = 'https://' + S3_BUCKET + '.s3.amazonaws.com/' + objKey
							img_list.append(img_url)
	print('img_list: {}'.format(img_list))
	return img_list

def trans_voice():
	print('transcribe voice to text')
	job_name = time.strftime('%a %b %d %H:%M:%S %Y', time.localtime()).replace(':', '-').replace(' ', '')
	job_uri = 'https://s3.amazonaws.com/' + S3_BUCKET + '/' + S3_VOICE
	print('trans job uri', job_uri)
	transcribe_client.start_transcription_job(
		TranscriptionJobName=job_name,
		Media={'MediaFileUri': job_uri},
		MediaFormat='mp3',
		LanguageCode='en-US',
		OutputBucketName=S3_BUCKET
	)
	while True:
		status = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
		if status['TranscriptionJob']['TranscriptionJobStatus'] in ['COMPLETED', 'FAILED']:
			break
		print('Transcription not ready yet.')
		time.sleep(5)
	print('Transcript URL: ', status)
	transcriptURL = status['TranscriptionJob']['Transcript']['TranscriptFileUri']
	trans_text = requests.get(transcriptURL).json()
		
	print('Transcripts: ', trans_text)
	print(trans_text['results']['transcripts'][0]['transcript'])
		
	response = s3_client.delete_object(
		Bucket=S3_BUCKET,
		Key=S3_VOICE
	)
	query = trans_text['results']['transcripts'][0]['transcript']
	s3_client.put_object(Body=query, Bucket=S3_BUCKET, Key=S3_TEXT)
	
def get_text():
	print('get text from S3')
	data = s3_client.get_object(Bucket=S3_BUCKET, Key=S3_TEXT)
	query = data.get('Body').read().decode('utf-8')
	# data_decode = data.get()['Body'].read().decode('utf-8').replace("'", '"')
	# query = json.loads(data_decode)['results']['transcripts'][0]['transcript']
	print('Voice query: ', query)
	s3_client.delete_object(
		Bucket=S3_BUCKET,
		Key=S3_TEXT
	)
	return query

def plural(word):
	if word.endswith('s'):
		return word[:-1]
	return word

def lambda_handler(event, context):
	# recieve from API Gateway
	print('EVENT --- {}'.format(json.dumps(event)))
	queryParam = event['queryStringParameters']
	if not queryParam:
		return get_response(400, 'Bad request, nothing in query params.')
	query = queryParam['q']

	print('query string parameters:', query)

	if query == 'voiceSearch':
		print('voiceSearch: starting trans voice to text.')
		trans_voice()
		return get_response(200, 'Transcribe completed.')
	if query == 'voiceResult':
		print('voiceResult: getting text transcribed.')
		query = get_text()
	
	slots, valid = get_slots(query)
	if not valid:
		get_response(200, 'Lex does not comprehend.')
	img_list = search_intent(slots)
	print('img_list:{}'.format(img_list))
	if img_list:
		return get_response(200, img_list)
	else:
		res = 'slots: ' + json.dumps(slots) + ', no photos matching the keyword.'
		return get_response(200, res)