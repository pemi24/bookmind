"""Compressing synthesized speech before it is cached and sent.

Piper (and Google's voices) produce raw 16-bit PCM: as WAV that is ~44 KB per second of speech.
With TTS_AUDIO_FORMAT=mp3 (the default) it is encoded to constant-bitrate MP3 with LAME
(pip install lameenc, a small self-contained wheel), ~5 KB per second at 40 kbps: about 9x
smaller. Without lameenc, or with TTS_AUDIO_FORMAT=wav, clips stay WAV.

An MP3 encoder adds silence at both ends of a clip (the encoder delay, and padding up to a whole
frame), ~50-75 ms at 22 kHz. Sentences are played one clip after another, so that silence would
add up between sentences. The file therefore starts with a LAME "Info" frame that records the
exact delay and padding, as the lame command-line encoder writes it; browsers read it and drop
the added samples (gapless playback), so a clip plays exactly as long as the WAV would.

Encoding is CPU work (a few ms per sentence): call these functions off the event loop.
"""
from __future__ import annotations

import logging
import struct

from app.tts.base import Audio, wav_bytes

log = logging.getLogger("bookmind.tts")

ENCODER_DELAY = 576  # samples LAME adds before the audio (lame_get_encoder_delay with no resampling)
_warned = False


def mp3_available() -> bool:
    try:
        import lameenc  # noqa: F401
    except ImportError:
        return False
    return True


def pcm_audio(pcm: bytes, sample_rate: int, fmt: str = "mp3", bitrate: int = 40) -> Audio:
    """Mono 16-bit PCM as a playable clip: MP3 when asked for and possible, else WAV."""
    global _warned
    if fmt.lower() == "mp3" and pcm:
        if mp3_available():
            try:
                return Audio(encode_mp3(pcm, sample_rate, bitrate), "audio/mpeg")
            except Exception as e:  # noqa: BLE001 - an odd sample rate or bitrate: WAV still plays
                if not _warned:
                    log.warning("MP3 encoding failed (%s); sending WAV instead.", e)
                    _warned = True
        elif not _warned:
            log.warning("TTS_AUDIO_FORMAT=mp3 but lameenc isn't installed (pip install lameenc); "
                        "sending uncompressed WAV.")
            _warned = True
    return Audio(wav_bytes(pcm, sample_rate), "audio/wav")


# --- MP3 -------------------------------------------------------------------------------------

_BITRATES = {  # kbps by bitrate index, for Layer III
    1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],  # MPEG-1
    2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160],  # MPEG-2 and 2.5
}
_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}  # by version bits


def _frame(header: bytes) -> tuple[int, int, int, int] | None:
    """(frame length, samples per frame, sample rate, side-info size) of a Layer III frame header."""
    if len(header) < 4 or header[0] != 0xFF or header[1] & 0xE0 != 0xE0:
        return None
    version = (header[1] >> 3) & 3  # 3 = MPEG-1, 2 = MPEG-2, 0 = MPEG-2.5
    if version == 1 or (header[1] >> 1) & 3 != 1:  # reserved, or not Layer III
        return None
    br_index, sr_index = header[2] >> 4, (header[2] >> 2) & 3
    if br_index in (0, 15) or sr_index == 3:
        return None
    mpeg1 = version == 3
    kbps = _BITRATES[1 if mpeg1 else 2][br_index]
    rate = _RATES[version][sr_index]
    padding = (header[2] >> 1) & 1
    mono = header[3] >> 6 == 3
    length = (144 if mpeg1 else 72) * kbps * 1000 // rate + padding
    side = (17 if mono else 32) if mpeg1 else (9 if mono else 17)
    return length, 1152 if mpeg1 else 576, rate, side


def _crc_table() -> list[int]:
    table = []
    for n in range(256):
        for _ in range(8):
            n = (n >> 1) ^ 0xA001 if n & 1 else n >> 1
        table.append(n)
    return table


_CRC = _crc_table()


def _crc16(data: bytes, crc: int = 0) -> int:
    """CRC-16/ARC, the checksum of the LAME tag."""
    for b in data:
        crc = (crc >> 8) ^ _CRC[(crc ^ b) & 0xFF]
    return crc


def encode_mp3(pcm: bytes, sample_rate: int, bitrate: int = 40) -> bytes:
    """Mono 16-bit PCM → CBR MP3 led by a LAME Info frame (exact length, for gapless playback)."""
    import lameenc

    enc = lameenc.Encoder()
    enc.set_channels(1)
    enc.set_in_sample_rate(sample_rate)
    enc.set_out_sample_rate(sample_rate)  # no resampling: the encoder delay stays 576 samples
    enc.set_bit_rate(bitrate)
    enc.set_quality(5)  # LAME's default speed/quality trade-off; far faster than real time
    audio = bytes(enc.encode(pcm)) + bytes(enc.flush())
    return _with_info_tag(audio, len(pcm) // 2)


def _with_info_tag(audio: bytes, samples: int) -> bytes:
    first = _frame(audio[:4])
    if first is None:
        raise ValueError("the encoder's output doesn't start with an MP3 frame")
    _, per_frame, _, side = first
    frames, at = 0, 0
    while at < len(audio):
        f = _frame(audio[at:at + 4])
        if f is None:
            raise ValueError(f"unexpected bytes in the encoder's output at {at}")
        at += f[0]
        frames += 1
    padding = frames * per_frame - ENCODER_DELAY - samples
    if not 0 <= padding < 4096:
        raise ValueError(f"unexpected MP3 padding ({padding} samples)")

    # The tag frame: same stream parameters as the audio, with the smallest bitrate whose frame
    # holds the whole tag (silent audio for a decoder that doesn't know the tag).
    tag_len = 4 + side + 156
    header = bytearray(audio[:4])
    header[1] |= 1  # no CRC
    header[2] &= 0x0D  # clear the bitrate index and the padding bit
    for index in range(1, 15):
        header[2] = (header[2] & 0x0F) | (index << 4)
        size = _frame(bytes(header))[0]
        if size >= tag_len:
            break
    else:
        raise ValueError("no MP3 frame is big enough for the LAME tag")
    total = size + len(audio)

    tag = bytearray(size)
    tag[0:4] = header
    t = 4 + side
    toc = bytes(min(255, i * 256 // 100) for i in range(100))  # constant bitrate: a straight line
    # flags (frames, bytes, TOC, quality), audio frames (not counting this one), file size
    tag[t:t + 120] = b"Info" + struct.pack(">III", 0x0F, frames, total) + toc + struct.pack(">I", 0)
    t += 120
    lame = bytearray(36)
    lame[0:9] = b"LAME3.100"
    lame[9] = 0x01  # tag revision 0, CBR
    lame[19] = 0  # encoding flags
    lame[20] = min(255, _BITRATES[1 if per_frame == 1152 else 2][audio[2] >> 4])
    lame[21:24] = ((ENCODER_DELAY << 12) | padding).to_bytes(3, "big")
    lame[28:32] = struct.pack(">I", total)  # music length: the whole file, tag frame included
    lame[32:34] = struct.pack(">H", _crc16(audio))  # music CRC
    tag[t:t + 34] = lame[:34]
    tag[t + 34:t + 36] = struct.pack(">H", _crc16(bytes(tag[:t + 34])))  # tag CRC
    return bytes(tag) + audio
