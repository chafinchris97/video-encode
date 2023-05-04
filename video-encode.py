#! /usr/bin/python3
#
# video-encode
#
# by Christopher Chafin

# Dependencies: ffprobe, handbrakecli, mkvmerge, mkvextract, mkvpropedit

import os
import sys
import json
import glob
import subprocess
from fractions import Fraction
import argparse

class MediaInfo:
    def __init__(self, video_path):
        output = subprocess.run([
            'ffprobe',
            '-loglevel', 'quiet',
            '-show_streams',
            '-show_format',
            '-print_format', 'json',
            video_path
        ], capture_output=True, text=True)

        info = json.loads(output.stdout)

        # check if json is empty
        if not bool(info):
            raise ValueError
        
        found_first_audio_track = False
        found_first_eng_sub_track = False
        self.eng_forced_sub_index = -1
        sub_index_offset = -1

        for stream in info.get('streams'):
            if stream.get('codec_type') == 'video':
                self.height = int(stream.get('height'))
                self.fps = stream.get('avg_frame_rate')
                self.is_dovi = bool(stream.get('side_data_list'))
                sub_index_offset += 1

            elif stream.get('codec_type') == 'audio':
                if found_first_audio_track is False:
                    self.audio_lang = stream.get('tags').get('language')
                    found_first_audio_track = True
                sub_index_offset += 1

            elif stream.get('codec_type') == 'subtitle':
                subtitle_lang = stream.get('tags').get('language')

                if found_first_eng_sub_track is False:
                    self.eng_sub_index = -1

                    if subtitle_lang == 'eng':
                        self.eng_sub_index = int(stream.get('index')) - sub_index_offset
                        found_first_eng_sub_track = True

                if subtitle_lang == 'eng' and stream.get('disposition').get('forced') == 1:
                    self.eng_forced_sub_index = int(stream.get('index')) - sub_index_offset

        self.bitrate = float(info.get('format').get('bit_rate'))
        self.duration = float(info.get('format').get('duration'))
        self.file_path = video_path


def empty_directory(folder):
    for i in glob.glob(os.path.join(folder, '*')):
        os.remove(i)


def findCQ(media_info, bitrate):
    with open('log.txt', 'a+') as log:
        log.write(f'Finding CQ for file: {media_info.file_path}\n')

    try:
        os.mkdir('samples')
    except:
        print('Samples folder is already made')
        empty_directory('samples')

    duration = media_info.duration
    steps = 5


    low_cq = 20
    high_cq = 80
    height = media_info.height

    if height <= 1080:
        low_cq = 25
        high_cq = 75
        bitrate_target = 4000
    else:
        bitrate_target = 12000

    if bitrate != 4000:
        bitrate_target = bitrate

    while low_cq <= high_cq:
        cq = int((low_cq + high_cq) / 2)
        bitrate_sum = 0

        print(f'Trying CQ {cq}...')

        for i in range(2, steps + 1):

            start_time = duration * i / (steps + 1)

            subprocess.run([
                    'handbrakecli',
                    '--input', media_info.file_path,
                    '--output', f'samples/sample_{i}.mkv',
                    '--start-at', f'seconds:{start_time}s',
                    '--stop-at', 'seconds:20s',
                    '--previews', '1:0',
                    '--encoder', 'vt_h265_10bit',
                    '--encoder-preset', 'quality',
                    '--encoder-profile', 'auto',
                    '--encoder-level', 'auto',
                    '--crop', '0:0:0:0',
                    '--no-comb-detect',
                    '--no-decomb',
                    '--quality', str(cq),
                    '--aencoder', 'ac3',
                    '--ab', '448',
                    '--mixdown', '5point1',
                    '--arate', 'auto'
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            sample_media_info = MediaInfo(f'samples/sample_{i}.mkv')
            br = (sample_media_info.bitrate / 1000) + 2000
            bitrate_sum += br

        empty_directory('samples')
        bitrate_mean = bitrate_sum / steps

        print(f'Predicted bitrate for CQ {cq} is {bitrate_mean} kbps')

        with open('log.txt', 'a') as log:
            log.write(f'Predicted bitrate for CQ {cq} is {bitrate_mean} kbps\n')

        if bitrate_mean > bitrate_target + 900:
            high_cq = cq - 1
        elif bitrate_mean < bitrate_target:
            low_cq = cq + 1
        else:
            break

    print(f'Found target CQ: {cq}, with predicted bitrate: {bitrate_mean}')
    try:
        empty_directory('samples')
        os.rmdir('samples')
    except:
        print('Could not delete samples folder.')

    with open('log.txt', 'a') as log:
            log.write('\n')
    return cq


def detect_burn_sub(media_info):
    if media_info.is_dovi:
        return -1
    
    forced = media_info.eng_forced_sub_index
    if forced != -1:
        return forced
    
    audio_lang = media_info.audio_lang
    if audio_lang != 'eng':
        sub = media_info.eng_sub_index
        if sub != -1:
            return sub
        
    return -1


def run_handbrake(media_info, cq, burn_sub):
    path = media_info.file_path
    output = os.path.basename(path)

    burn_sub_param = []
    if burn_sub != -1:
        burn_sub_param = ['--subtitle', str(burn_sub), '--subtitle-burned']

    subprocess.run([
        'handbrakecli',
        '--input', path,
        '--output', output,
        '--previews', '60:0',
        '--crop-threshold-frames', '3',
        '--markers',
        '--encoder', 'vt_h265_10bit',
        '--encoder-preset', 'quality',
        '--encoder-profile', 'auto',
        '--encoder-level', 'auto',
        '--no-comb-detect',
        '--no-decomb',
        '--quality', str(cq),
        '--aencoder', 'ac3',
        '--ab', '448',
        '--mixdown', '5point1',
        '--arate', 'auto'
    ] + burn_sub_param
    )


def inject_dovi(media_info, encoded_file_path):
    ffmpeg = subprocess.Popen([
        'ffmpeg',
        '-loglevel', 'quiet',
        '-i', media_info.file_path,
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
        '-o', 'RPU.bin'
    ], stdin=ffmpeg.stdout)

    subprocess.run([
        'mkvextract',
        encoded_file_path,
        'tracks', '0:com.hevc'
    ])

    subprocess.run([
        'dovi_tool',
        'inject-rpu',
        '-i', 'com.hevc',
        '--rpu-in', 'RPU.bin',
        '-o', 'inj.hevc'
    ])

    old_com_file = f'{os.path.basename(encoded_file_path)}.old'
    os.rename(os.path.basename(encoded_file_path), old_com_file)

    subprocess.run([
        'mkvmerge',
        '--default-duration', f'0:{media_info.fps}fps',
        'inj.hevc',
        '-D', old_com_file,
        '-o', encoded_file_path
    ])

    os.remove('com.hevc')
    os.remove('inj.hevc')
    os.remove('RPU.bin')
    os.remove(old_com_file)


def inject_hdr(media_info, encoded_file_path):
    ffprobe_hdr = subprocess.run([
        'ffprobe',
        '-loglevel', 'quiet',
        '-select_streams', 'v:0',
        '-show_frames',
        '-read_intervals', '%+#1',
        '-show_entries', 'frame=side_data_list',
        '-print_format', 'json',
        media_info.file_path
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


def delete_audio_track_name(file):
    subprocess.run([
        'mkvpropedit',
        file,
        '--edit', 'track:a1',
        '--delete', 'name'
    ])


def encode(media_info, bitrate):
    cq = findCQ(media_info, bitrate)
    burn_sub = detect_burn_sub(media_info)
    run_handbrake(media_info, cq, burn_sub)

    encoded_file_path = os.path.basename(media_info.file_path)

    delete_audio_track_name(encoded_file_path)

    if media_info.is_dovi:
        inject_dovi(media_info, encoded_file_path)
        inject_hdr(media_info, encoded_file_path)


def main(args):
    bitrate = args.target
    file = str(args.file_path)

    if file.endswith('.mkv') is False:
        print('only provide .mkv files.')
    elif os.path.isfile(os.path.basename(file)):
        print('output file already exists.')
    else:
        try:
            media_info = MediaInfo(file)
            encode(media_info, bitrate)
        except ValueError:
            print(f'failed to scan file: {file}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Script that encodes video files with an attempted target bitrate using constant quality.')
    parser.add_argument('--target', type=int, default=4000,
                        help='set target video bitrate.')
    parser.add_argument('file_path', type=str, help='video file path.')
    args = parser.parse_args()
    main(args)