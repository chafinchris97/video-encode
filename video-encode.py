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
import tempfile
import logging
from fractions import Fraction

logger = logging.getLogger(__name__)

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
    channels: int


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
                if stream.get('side_data_list'):
                    self.is_dolby_vision = stream.get('side_data_list')[0].get('side_data_type') == 'DOVI configuration record'
            elif stream.get('codec_type') == 'audio':
                audio_index += 1
                audio = Audio(
                    index=audio_index,
                    language=stream.get('tags').get('language'),
                    channels=stream.get('channels')
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

        self.bitrate = float(media_info.get('format').get('bit_rate'))
        self.duration_in_seconds = float(media_info.get('format').get('duration'))


class Handbrake:
    def __init__(self):
        self.input_file = ''
        self.input_command = []
        self.output_command = []
        self.quality_command = []
        self.crop_command = ['--crop', '0:0:0:0']
        self.previews_command = ['--previews', '1:0']
        self.burn_subtitle_command = []
        self.start_at_command = []
        self.stop_at_command = []
        self.encoder_command = ['--encoder', 'vt_h265_10bit',
                                '--encoder-preset', 'quality',
                                '--encoder-profile', 'auto',
                                '--encoder-level', 'auto']
        self.audio_encoder_command = []

    def input(self, input_file_path):
        self.input_file = input_file_path
        # create output path in case output wasn't specified
        output_file_path = os.path.basename(self.input_file)
        self.input_command = ['--input', self.input_file]
        self.output_command = ['--output', output_file_path]

    def output(self, output_file_path):
        self.output_command = ['--output', output_file_path]

    def start_time(self, time_in_seconds):
        self.start_at_command = ['--start-at', f'seconds:{time_in_seconds}s']

    def stop_at(self, time_in_seconds):
        self.stop_at_command = ['--stop-at', f'seconds:{time_in_seconds}s']

    def quality(self, cq_number):
        self.quality_command = ['--quality', str(cq_number)]

    def crop(self):
        self.crop_command = ['--crop-threshold-frames', '3']

    def previews(self, previews_number):
        self.previews_command = ['--previews', f'{previews_number}:0']

    def burn_subtitle(self, subtitle_track):
        self.burn_subtitle_command = ['--subtitle', str(subtitle_track), '--subtitle-burned']

    def audio_encoder(self, aencoder):
        if aencoder == 'ac3':
            self.audio_encoder_command = ['--aencoder', 'ac3',
                                      '--ab', '448',
                                      '--mixdown', '5point1',
                                      '--arate', 'auto']
        elif aencoder == 'aac':
            self.audio_encoder_command = ['--aencoder', 'aac',
                                      '--ab', '256',
                                      '--mixdown', 'stereo',
                                      '--arate', 'auto']
        else:
            raise ValueError(f'{aencoder} is an invalid option for audio encoder')

    def run(self, quiet_run=False):
        if not self.input_command:
            raise TypeError('handbrakecli missing input option')
        elif not self.quality_command:
            raise TypeError('handbrakecli missing quality option')
        elif not self.audio_encoder_command:
            raise TypeError('handbrakecli missing audio options')

        command = ['handbrakecli']
        command += self.input_command
        command += self.output_command
        command += self.start_at_command
        command += self.stop_at_command
        command += self.previews_command
        command += self.crop_command
        command += ['--markers']
        command += self.encoder_command
        command += ['--no-comb-detect', '--no-decomb']
        command += self.quality_command
        command += self.audio_encoder_command
        command += self.burn_subtitle_command

        if quiet_run:
            subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            logger.info(f'Encoding command for file: {os.path.basename(self.input_file)}:')
            logger.info(' '.join(command))
            subprocess.run(command)


def verify_ffprobe():
    print('Verifying ffprobe...')
    try:
        subprocess.check_call(['ffprobe', '-version'], 
                              stdout=subprocess.DEVNULL, 
                              stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise IOError('ffprobe not found')
    

def verify_handbrakecli():
    print('Verifying handbrakecli...')
    try:
        subprocess.check_call(['handbrakecli', '--version'],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise IOError('handbrakecli not found')
    

def verify_ffmpeg():
    print('Verifying ffmpeg...')
    try:
        subprocess.check_call(['ffmpeg', '-version'],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise IOError('ffmpeg not found')
    

def verify_dovi_tool():
    print('Verifying dovi_tool...')
    try:
        subprocess.check_call(['dovi_tool', '--version'],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise IOError('dovi_tool not found')
    

def verify_mkvmerge():
    print('Verifying mkvmerge...')
    try:
        subprocess.check_call(['mkvmerge', '--version'],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise IOError('mkvmerge not found')
    

def verify_mkvextract():
    print('Verifying mkvextract...')
    try:
        subprocess.check_call(['mkvextract', '--version'],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise IOError('mkvextract not found')
    

def verify_mkvpropedit():
    print('Verifying mkvpropedit...')
    try:
        subprocess.check_call(['mkvpropedit', '--version'],
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        raise IOError('mkvpropedit not found')


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


def find_quality_option(media_info, target_bit_rate):
    logger.info(f'Finding optimal cq value for {os.path.basename(media_info.file_path)}')
    temporary_directory = tempfile.TemporaryDirectory()
    duration = media_info.duration_in_seconds
    steps = 5
    low_cq = 20
    high_cq = 80
    if media_info.height <= 1080:
        low_cq = 25
        high_cq = 75
    
    while low_cq <= high_cq:
        cq = int((low_cq + high_cq) / 2)
        bit_rate_sum = 0
        logger.info(f'Trying CQ {cq}...')
        for sample_index in range(1, steps):
            sample_file_name = f'{temporary_directory.name}/cq_{cq}_sample_{sample_index}.mkv'
            start_time_in_seconds = duration * sample_index / (steps + 1)
            encoder = Handbrake()
            encoder.input(media_info.file_path)
            encoder.output(sample_file_name)
            if media_info.audios[0].channels <= 2:
                encoder.audio_encoder('aac')
            else:
                encoder.audio_encoder('ac3')
            encoder.start_time(start_time_in_seconds)
            encoder.stop_at(20)
            encoder.quality(cq)
            encoder.run(quiet_run=True)

            sample_media_info = FFProbe(sample_file_name)
            sample_bit_rate = sample_media_info.bitrate / 1000 + 2000
            bit_rate_sum += sample_bit_rate
        
        bit_rate_mean = bit_rate_sum / steps
        logger.info(f'Predicted bit rate for CQ {cq} is {bit_rate_mean}')
        if bit_rate_mean > target_bit_rate + 900:
            high_cq = cq - 1
        elif bit_rate_mean < target_bit_rate:
            low_cq = cq + 1
        else:
            break

    logger.info(f'Using CQ {cq} for a predicted bit rate of {bit_rate_mean}')
    temporary_directory.cleanup()
    return cq


def find_burn_subtitle_track(subtitles):
    for subtitle in subtitles:
        if subtitle.forced:
            return subtitle.index
        elif media_info.audios[0].language != 'eng' and subtitle.language == 'eng':
            return subtitle.index
    return 0


def inject_dolby_vision(raw_file_path, encoded_file_path, frames_per_second):
    temporary_directory = tempfile.TemporaryDirectory()
    rpu_directory = f'{temporary_directory.name}/RPU.bin'
    encoded_file_stream_directory = f'{temporary_directory.name}/com.hevc'
    injected_file_stream_directory = f'{temporary_directory.name}/inj.hevc'

    logger.info('Extracting dolby vision metadata')
    ffpmeg = subprocess.Popen([
        'ffmpeg',
        '-loglevel', 'quiet',
        '-i', raw_file_path,
        '-c:v', 'copy',
        '-vbsf', 'hevc_mp4toannexb',
        '-f', 'hevc',
        '-'
    ], stdout=subprocess.PIPE)

    subprocess.run([
        'dovi_tool',
        '-m', '2',
        '--crop',
        'extract-rpu',
        '-',
        '-o', rpu_directory
    ], stdin=ffpmeg.stdout)

    logger.info('extracting encoded video stream')
    subprocess.run([
        'mkvextract',
        encoded_file_path,
        'tracks', f'0:{encoded_file_stream_directory}'
    ])
    logger.info('injecting dolby vision metadata into encoded stream')
    subprocess.run([
        'dovi_tool',
        'inject-rpu',
        '-i', encoded_file_stream_directory,
        '--rpu-in', rpu_directory,
        '-o', injected_file_stream_directory
    ])

    old_encoded_file = f'{encoded_file_path}.old'
    os.rename(encoded_file_path, old_encoded_file)

    logger.info('remuxing video file with dolby vision')
    subprocess.run([
        'mkvmerge',
        '--default-duration', f'0:{frames_per_second}fps',
        injected_file_stream_directory,
        '-D', old_encoded_file,
        '-o', encoded_file_path
    ])

    os.remove(old_encoded_file)
    temporary_directory.cleanup()


def inject_hdr(raw_file_path, encoded_file_path):
    logger.info('extracting hdr metadata')
    ffprobe_hdr = subprocess.run([
        'ffprobe',
        '-loglevel', 'quiet',
        '-select_streams', 'v:0',
        '-show_frames',
        '-read_intervals', '%+#1',
        '-show_entries', 'frame=side_data_list',
        '-print_format', 'json',
        raw_file_path
    ], capture_output=True, text=True)

    hdr_info = json.loads(ffprobe_hdr.stdout)

    md = ''
    cll = ''

    for frame in hdr_info['frames']:
        for side_data in frame['side_data_list']:
            if side_data['side_data_type'] == 'Content light level metadata':
                cll = side_data
            elif side_data['side_data_type'] == 'Mastering display metadata':
                md = side_data

    if cll == '' or md == '':
        return
    
    max_content = cll['max_content']
    max_average = cll['max_average']

    red_x = float(Fraction(md['red_x']))
    red_y = float(Fraction(md['red_y']))
    green_x = float(Fraction(md['green_x']))
    green_y = float(Fraction(md['green_y']))
    blue_x = float(Fraction(md['blue_x']))
    blue_y = float(Fraction(md['blue_y']))
    white_x = float(Fraction(md['white_point_x']))
    white_y = float(Fraction(md['white_point_y']))
    max_luminance = float(Fraction(md['max_luminance']))
    min_luminance = float(Fraction(md['min_luminance']))

    logger.info('injecting hdr metadata into encode stream')
    subprocess.run([
        'mkvpropedit',
        encoded_file_path,
        '--edit', 'track:v1',
        '--set', f'max-content-light={max_content}',
        '--set', f'max-frame-light={max_average}',
        '--set', f'chromaticity-coordinates-red-x={red_x}',
        '--set', f'chromaticity-coordinates-red-y={red_y}',
        '--set', f'chromaticity-coordinates-green-x={green_x}',
        '--set', f'chromaticity-coordinates-green-y={green_y}',
        '--set', f'chromaticity-coordinates-blue-x={blue_x}',
        '--set', f'chromaticity-coordinates-blue-y={blue_y}',
        '--set', f'white-coordinates-x={white_x}',
        '--set', f'white-coordinates-y={white_y}',
        '--set', f'max-luminance={max_luminance}',
        '--set', f'min-luminance={min_luminance}'
    ])

if __name__ == '__main__':
    arguments = parse_arguments()
    output_path = os.path.basename(arguments.file_name)

    logging_name = f'{output_path}.log.txt'
    logging.basicConfig(level=logging.INFO,
                        format='%(message)s')
    file_handler = logging.FileHandler(logging_name)
    logger.addHandler(file_handler)

    verify_ffprobe()
    verify_handbrakecli()
    verify_ffmpeg()
    verify_dovi_tool()
    verify_mkvmerge()
    verify_mkvextract()
    verify_mkvpropedit()

    media_info = FFProbe(arguments.file_name)
    target_bit_rate = arguments.target
    quality_option = arguments.quality
    should_crop = arguments.crop
    burn_subtitle_track = arguments.burn_subtitle

    if os.path.isfile(output_path):
        raise IOError('file output already exists')

    if target_bit_rate == 0:
        if media_info.height > 1080:
            target_bit_rate = 12000
        else:
            target_bit_rate = 4000

    if quality_option is None:
        quality_option = find_quality_option(media_info, target_bit_rate)

    encoder = Handbrake()
    encoder.input(media_info.file_path)
    encoder.output(output_path)
    encoder.quality(quality_option)

    if media_info.audios[0].channels <= 2:
        encoder.audio_encoder('aac')
    else:
        encoder.audio_encoder('ac3')

    if should_crop:
        encoder.previews(60)
        encoder.crop()

    if burn_subtitle_track.isdigit():
        subtitle_track = int(burn_subtitle_track)
        encoder.burn_subtitle(subtitle_track)
    elif burn_subtitle_track == 'auto' and media_info.is_dolby_vision == False:
        subtitle_track = find_burn_subtitle_track(media_info.subtitles)
        encoder.burn_subtitle(subtitle_track)

    encoder.run()

    output_media_info = FFProbe(output_path)
    if media_info.is_dolby_vision:
        inject_dolby_vision(media_info.file_path, output_path, media_info.frame_rate)
        inject_hdr(media_info.file_path, output_path)