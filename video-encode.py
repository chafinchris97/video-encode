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


class Handbrake:
    def __init__(self):
        self.input_file = ''
        self.input_command = []
        self.output_command = []
        self.quality_command = []
        self.crop_command = ['--crop', '0:0:0:0']
        self.previews_command = ['--previews', '1:0']
        self.burn_subtitle_command = []
        self.encoder_command = ['--encoder', 'vt_h265_10bit',
                                '--encoder-preset', 'quality',
                                '--encoder-profile', 'auto',
                                '--encoder-level', 'auto']
        self.audio_encoder_command = ['--aencoder', 'ac3',
                                      '--ab', '448',
                                      '--mixdown', '5point1',
                                      '--arate', 'auto']

    def input(self, input_file_path):
        self.input_file = input_file_path
        # create output path in case output wasn't specified
        output_file_path = os.path.basename(self.input_file)
        self.input_command = ['--input', self.input_file]
        self.output_command = ['--output', output_file_path]

    def output(self, output_file_path):
        self.output_command = ['--output', output_file_path]

    def quality(self, cq_number):
        self.quality_command = ['--quality', str(cq_number)]

    def crop(self):
        self.crop_command = ['--crop-threshold-frames', '3']

    def previews(self, previews_number):
        self.previews_command = ['--previews', f'{previews_number}:0']

    def burn_subtitle(self, subtitle_track):
        self.burn_subtitle_command = ['--subtitle', str(subtitle_track), '--subtitle-burned']

    def run(self):
        if not self.input_command:
            raise IOError('handbrakecli missing input option')
        elif not self.quality_command:
            raise IOError('handbrakecli missing quality option')

        command = ['handbrakecli']
        command += self.input_command
        command += self.output_command
        command += self.previews_command
        command += self.crop_command
        command += ['--markers']
        command += self.encoder_command
        command += ['--no-comb-detect', '--no-decomb']
        command += self.quality_command
        command += self.audio_encoder_command
        command += self.burn_subtitle_command

        print(f'Encoding command for file: {self.input_file}')
        print(*command)
        #subprocess.run(command)


def verify_ffprobe():
    print('Verifying ffprobe...')
    try:
        subprocess.check_call(['ffprobe', '-h'], 
                              stdout=subprocess.DEVNULL, 
                              stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise IOError('ffprobe not found')
    

def verify_handbrakecli():
    print('Verifying handbrakecli...')
    try:
        subprocess.check_call(['handbrakecli', '-h'],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise IOError('handbrakecli not found')


def parse_arguments():
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
                        default=0,
                        help='choose a bitrate to target (DEFAULT: 1080p=4000, 2160p=12000)')
    parser.add_argument('--quality',
                        type=int,
                        choices=range(1,101),
                        help='choose a cq number to use to encode (overrides finding cq)')
    parser.add_argument('--burn-subtitle',
                        type=str,
                        metavar='auto|none|TRACK',
                        default='auto',
                        help='pick which subtitle track to burn in (DEFAULT: auto - burns only image based subtitles that are forced or if main audio is foriegn)')
    parser.add_argument('--crop',
                        action='store_true',
                        help='choose to auto crop (DEFAULT: no crop)')
    
    arguments = parser.parse_args()

    if arguments.burn_subtitle != 'auto' and \
        arguments.burn_subtitle != 'none' and \
            arguments.burn_subtitle.isdigit() == False:
        raise argparse.ArgumentTypeError('Invalid option. Please choose \'none\', \'auto\', or a track number')

    return arguments


def find_quality_option(target_bit_rate):
    # TODO: binary search algorithm for finding optimal cq value
    return 50

if __name__ == '__main__':
    arguments = parse_arguments()

    verify_ffprobe()
    verify_handbrakecli()

    media_info = FFProbe(arguments.file_name)
    target_bit_rate = arguments.target
    quality_option = arguments.quality
    should_crop = arguments.crop
    burn_subtitle_track = arguments.burn_subtitle

    if target_bit_rate == 0:
        if media_info.height > 1080:
            target_bit_rate = 12000
        else:
            target_bit_rate = 4000

    if quality_option is None:
        quality_option = find_quality_option(target_bit_rate)

    encoder = Handbrake()
    encoder.input(media_info.file_path)
    encoder.quality(quality_option)
    if should_crop:
        encoder.previews(60)
        encoder.crop()
    if burn_subtitle_track.isdigit():
        encoder.burn_subtitle(int(burn_subtitle_track))
    elif burn_subtitle_track == 'auto':
        for subtitle in media_info.subtitles:
            if subtitle.forced:
                encoder.burn_subtitle(subtitle.index)
                break
            elif media_info.audios[0].language != 'eng' and subtitle.language == 'eng':
                encoder.burn_subtitle(subtitle.index)
                break

    encoder.run()