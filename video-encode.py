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
                        metavar='bitrate',
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