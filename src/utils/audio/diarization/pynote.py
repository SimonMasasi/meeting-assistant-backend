import io
import logging
import os

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

    def diarize(self, audio: bytes | str) -> list[dict]:
        """Speaker turns as [{"start": float_s, "end": float_s, "speaker": str}, ...].

        Accepts either the audio bytes or a path to a local file. Prefer the path
        form for large recordings — it keeps the file off the heap."""
        from pyannote.audio.pipelines.utils.hook import ProgressHook

        # The pipeline accepts str | Path | IOBase | Mapping — never raw bytes.
        source = audio if isinstance(audio, (str, os.PathLike)) else io.BytesIO(audio)

        results: list[dict] = []
        with ProgressHook() as progress_hook:
            output = self.pipeline(source, hook=progress_hook)
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
