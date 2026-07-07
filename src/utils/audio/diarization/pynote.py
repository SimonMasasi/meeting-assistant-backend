import io
import logging

logger = logging.getLogger(__name__)


class PyNoteDiarization:

    def __init__(self):
        # Heavy imports stay out of module scope so a Soniox-only deployment
        # never loads torch/pyannote (see SpeakerDiarizationService).
        import torch
        from pyannote.audio import Pipeline
        from config import SETTINGS

        if not SETTINGS.HUGGINGFACE_TOKEN:
            raise ValueError(
                "Local diarization requires HUGGINGFACE_TOKEN in the server .env "
                "(or set SONIOX_API_KEY to use cloud transcription instead)."
            )
        self.pipeline = Pipeline.from_pretrained(SETTINGS.PYNOTE_MODEL, token=SETTINGS.HUGGINGFACE_TOKEN)
        self.pipeline.to(torch.device(self.detect_device()))

    def diarize(self, wav_audio_bytes: bytes) -> list[dict]:
        """Speaker turns as [{"start": float_s, "end": float_s, "speaker": str}, ...]."""
        from pyannote.audio.pipelines.utils.hook import ProgressHook

        results: list[dict] = []
        with ProgressHook() as progress_hook:
            # The pipeline accepts str | Path | IOBase | Mapping — never raw bytes.
            output = self.pipeline(io.BytesIO(wav_audio_bytes), hook=progress_hook)
        # pyannote.audio 4.x returns a DiarizeOutput whose Annotation lives on
        # `.speaker_diarization`; older versions return the Annotation directly.
        annotation = getattr(output, "speaker_diarization", output)
        for turn, _track, speaker in annotation.itertracks(yield_label=True):
            results.append({
                "start": float(turn.start),
                "end": float(turn.end),
                "speaker": str(speaker),
            })
        return results

    def detect_device(self):
        # detect if GPU , mac or CPU is available
        import torch

        if torch.cuda.is_available():
            logger.info("CUDA is available. Using GPU for PyNoteDiarization.")
            return "cuda"
        elif torch.backends.mps.is_available():
            logger.info("MPS is available. Using MPS for PyNoteDiarization.")
            return "mps"
        else:
            logger.info("No GPU or MPS available. Using CPU for PyNoteDiarization.")
            return "cpu"
