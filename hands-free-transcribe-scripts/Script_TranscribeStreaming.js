'use strict';

// The sumerian object can be used to access Sumerian engine
// types.
//
/* global sumerian */

// Called when play mode starts.
function setup(args, ctx) {
	ctx.events = {
		input: {
			startTranscribing: "microphone.startTranscribing",
			stopTranscribing: "microphone.stopTranscribing",
			clearTranscript: "microphone.clearTranscript",
		},
		output: {
			onAudioTranscribed: "microphone.onAudioTranscribed",
			onAudioTranscribedError: "microphone.onAudioTranscribedError",
			onAudioDataAnalyzed: "microphone.onAudioDataAnalyzed"
		}
	}
	
	clearTranscript = clearTranscript.bind(this, args, ctx);
	startTranscribing = startTranscribing.bind(this, args, ctx);
	stopTranscribing = stopTranscribing.bind(this, args, ctx);
	
	ctx.fullTranscript = "";
	
	// register events
	sumerian.SystemBus
		.addListener(ctx.events.input.startTranscribing, startTranscribing)
		.addListener(ctx.events.input.stopTranscribing, stopTranscribing)
		.addListener(ctx.events.input.clearTranscript, clearTranscript);
}

// clear the full transcription
function clearTranscript(args, ctx){
	ctx.fullTranscript = "";
}

// start recording and transcription socket
function startTranscribing(args, ctx) {
	if(!window.AWS){
		// make sure to set up Cognito credentials
		console.error('Could not load AWS JavaScript SDK, make sure to set up a Cognito Identity Pool ID! For more information, visit https://docs.aws.amazon.com/sumerian/latest/userguide/scene-aws.html');
		return;
	}

	const onSocketOpen = () => {
		// socket is now open, let's start recording
		ctx.microphone.startRecording();
	}
	
	const onTranscriptionResponse = (isPartial, transcript) => {
		// Audio has been transcribed, let's emit an event with metadata.
		const fullTranscript = ctx.fullTranscript + transcript + "\n";
		const params = {
			isPartial,
			transcript,
			fullTranscript
		}

		// emit transcription
		sumerian.SystemBus.emit(ctx.events.output.onAudioTranscribed, params);

		// if this transcript segment is final, add it to the overall transcription
		if (!isPartial) {
		  ctx.fullTranscript += transcript + "\n";
		}
	}
	
	const onTranscriptionError = (err) => {
		// Something went wrong with the transcription, emit an error
		sumerian.SystemBus.emit(ctx.events.output.onAudioTranscribedError, err)
	}
	
	const onMicrophoneAudioEvent = (audioEvent) => {
		// After we fill the audio buffer, stream it to the websocket connected to Amazon Transcribe
		if(ctx.transcribeStreaming) {
			ctx.transcribeStreaming.sendData(audioEvent.inputBuffer.getChannelData(0));
		}
	}
	
	// Get AWS Credentials to pass to the Amazon Transcribe Streaming Client
	window.AWS.config.credentials.get(err => {
		if(err) { console.log(err); }
		else {
			const credentials = window.AWS.config.credentials;
			const region = window.AWS.config.region;
			const constraints = {
				audio: true
			}
			
			// ask user for audio permissions
			navigator.mediaDevices.getUserMedia(constraints).then((stream) => {
					// setup microphone recording
					ctx.microphone = new Microphone(stream, onMicrophoneAudioEvent, args.bufferSize);
					// setup transcribe streaming client
					ctx.transcribeStreaming = new window.TranscribeStreaming(region, credentials, args.languageCode, ctx.microphone.sampleRate, args.downSampleRate);
					// open the web socket
					ctx.transcribeStreaming.openSocket(onSocketOpen, onTranscriptionResponse, onTranscriptionError);
			}).catch(err => console.log(err));
		}
	});
}

// stop microphone and close transcription socket
function stopTranscribing(args, ctx) {	
	if(ctx.transcribeStreaming) {
		ctx.transcribeStreaming.closeSocket();
		ctx.transcribeStreaming = null;
	}

	if(ctx.microphone) {
		ctx.microphone.stopRecording();
		ctx.microphone = null
	}
}

// on every frame emit raw audio events to visualize
function update(args, ctx) {
	if(ctx.microphone && ctx.microphone.isRecording) {
		const dataArray = ctx.microphone.getByteTimeDomainData();
		sumerian.SystemBus.emit(ctx.events.output.onAudioDataAnalyzed, dataArray);
	}
}


// Called when play mode stops.
//
function cleanup(args, ctx) {
	sumerian.SystemBus
		.removeListener(ctx.events.input.startTranscribing, startTranscribing)
		.removeListener(ctx.events.input.stopTranscribing, stopTranscribing)
		.removeListener(ctx.events.input.clearTranscript, clearTranscript);
	
	stopTranscribing();
}

// Defines script parameters.
//
var parameters = [
	{ type: "int", key: "downSampleRate", name: "Sample Rate", default: 48000, description: "The rate in Hz to down sample the audio to. For highest quality audio, set it to 48000 but note not all languages support it. 8000 covers all supported languages. Refer to Amazon Transcribe guidelines for best practices"},
	{ type: "int", key: "bufferSize", name: "Buffer Size", default: 4096, description: "The size of the audio buffer recorded before streaming"},
	{ type: "string", key: "languageCode", name: "Language Code", default: 'en-US', description: "The language to use for transcription"}
];

// Simple microphone recording class with configurable parameters
class Microphone {
	
	constructor(stream, onAudioBufferCallback, bufferSize = 4096, inputChannels = 1, outputChannels = 1) {
		this.stream = stream;
		this.bufferSize = bufferSize;
		this.inputChannels = inputChannels;
		this.outputChannels = outputChannels;
		
		this.context = new (window.AudioContext || window.webkitAudioContext)();
		this.onAudioBufferCallback = onAudioBufferCallback;
	};
	
	get isRecording() {
		return this.recording;
	};
	
	get sampleRate() {
		return this.context.sampleRate;
	};
	
	getByteTimeDomainData() {
		const bufferLength = this.analyser.fftSize;
		const dataArray = new Uint8Array(bufferLength);
		this.analyser.getByteTimeDomainData(dataArray);
		return dataArray;
	};
	
	startRecording() {
		this.recording = true;
		
		// Setup audio analyser
		this.analyser = this.context.createAnalyser();
		
		// Setup audio processor
		this.recorder = this.context.createScriptProcessor(this.bufferSize, this.inputChannels, this.outputChannels);
		this.recorder.onaudioprocess = this.onAudioBufferCallback;
		
		// start audio recording
		this.audioInput = this.context.createMediaStreamSource(this.stream);
		
		// connect them
		this.audioInput.connect(this.analyser);
		this.analyser.connect(this.recorder);
		this.recorder.connect(this.context.destination);
	};

	stopRecording() {
		this.recording = false;
		
		try {
			if(this.stream)
		 		this.stream.getTracks()[0].stop();
		} catch (ex) {
		}
		
		if(this.recorder)
			this.recorder.disconnect();
		if(this.audioInput)
			this.audioInput.disconnect();
		if(this.analyser)
			this.analyser.disconnect();
		
		 try {
		 	if(this.context)
		  		this.context.close();
		} catch (ex) {
		}
	};
}