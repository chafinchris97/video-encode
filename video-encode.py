#! /usr/bin/python3
#
# video-encode
#
# by Christopher Chafin

# description:
# A python script which utulizes Apple's VideoToolBox encoder to create high quality,
# h265 10 bit encodes for Blu Ray and 4k Blu Ray rips.
# This script attempts to find a constant quality value that will result in a predictied
# output bitrate. It uses constant quality rate factor rather than average bitrate because
# constant quality produces a higher quality output compared to average bitrate, even if the
# resulting file size is the same.
#
# dependencies: handbrakecli, ffprobe, ffmpeg, dovi_tool, mkvmerge, mkvpropedit, mkvextract

import argparse
import subprocess
import os
import json
from dataclasses import dataclass

@dataclass
class Subtitle:
    index: int
    language: str
    forced: bool
    type: str

@dataclass
class Audio:
    index: int
    language: str


class FFProbe:
    def __init__(self, input_file_path):
        self.file_path = input_file_path
        if os.path.isfile(self.file_path) == False:
            raise IOError(f'file does not exist: {self.file_path}')
        
        output = subprocess.run([
            'ffprobe',
            '-loglevel', 'quiet',
            '-show_streams',
            '-show_format', 
            '-print_format', 'json',
            self.file_path
        ], capture_output=True, text=True)

        media_info = json.loads(output.stdout)

        self.height = 0
        self.duration_in_seconds = 0
        self.bitrate = 0
        self.frame_rate = 0
        self.is_dolby_vision = False
        self.subtitles = []
        self.audios = []

        audio_index = 0
        subtitle_index = 0
        for stream in media_info.get('streams'):
            if stream.get('codec_type') == 'video':
                self.height = int(stream.get('height'))
                self.frame_rate = stream.get('avg_frame_rate')
                self.is_dolby_vision = bool(stream.get('side_data_list'))
            elif stream.get('codec_type') == 'audio':
                audio_index += 1
                audio = Audio(
                    index=audio_index,
                    language=stream.get('tags').get('language')
                )
                self.audios.append(audio)
            elif stream.get('codec_type') == 'subtitle':
                subtitle_index += 1
                subtitle = Subtitle(
                    index=subtitle_index,
                    language=stream.get('tags').get('language'),
                    forced=stream.get('disposition').get('forced') == 1,
                    type=stream.get('codec_name')
                )
                self.subtitles.append(subtitle)

        self.bitrate = media_info.get('format').get('bit_rate')
        self.duration_in_seconds = media_info.get('format').get('duration')


def verify_ffprobe():
    print('Verifying ffprobe...')
    try:
        subprocess.check_call(['ffprobe', '-h'], 
                              stdout=subprocess.DEVNULL, 
                              stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise IOError('ffprobe not found')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        prog='Video Encode',
        description='Creates high quality encodes in h265 10 bit, using Apple\'s VideoToolBox.'
    )

    parser.add_argument('file_name',
                        type=str,
                        help='directory for blu ray rip to encode')
    parser.add_argument('--target',
                        type=int,
                        metavar='BITRATE',
                        default=4000,
                        help='choose a bitrate to target (DEFAULT: 1080p=4000, 2160p=12000)')
    parser.add_argument('--quality',
                        type=int,
                        help='choose a cq number to use to encode (overrides finding cq)')
    parser.add_argument('--burn_subtitle',
                        type=str,
                        metavar='auto|none|TRACK',
                        default='auto',
                        help='pick which subtitle track to burn in (DEFAULT: auto - burns only image based subtitles that are forced or if main audio is foriegn)')
    parser.add_argument('--crop',
                        action='store_true',
                        help='choose to auto crop (DEFAULT: no crop)')
    
    arguments = parser.parse_args()

    verify_ffprobe()