import torch
from pyannote.audio import Pipeline
from pyannote.audio.pipelines.utils.hook import ProgressHook
from config import SETTINGS

import logging
logger = logging.getLogger(__name__)



class PyNoteDiarization:

    def __init__(self):
        self.pipeline = Pipeline.from_pretrained(SETTINGS.PYNOTE_MODEL, token=SETTINGS.HUGGINGFACE_TOKEN)
        self.pipeline.to(torch.device(self.detect_device()))
    
    def diarize(self, wav_audio_bytes: bytes):
        results = []
        with ProgressHook() as progress_hook:
            diarization = self.pipeline(wav_audio_bytes , hook=progress_hook)
            for turn, speaker in diarization.speaker_diarization:
                results.append({
                    "start": turn.start,
                    "end": turn.end,
                    "speaker": speaker
                })
        return results
            
    def detect_device(self):
        # detect if GPU , mac or CPU is available
        if torch.cuda.is_available():
            logger.info("CUDA is available. Using GPU for PyNoteDiarization.")
            return "cuda"
        elif torch.backends.mps.is_available():
            logger.info("MPS is available. Using MPS for PyNoteDiarization.")
            return "mps"
        else:
            logger.info("No GPU or MPS available. Using CPU for PyNoteDiarization.")
            return "cpu"