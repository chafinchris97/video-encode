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

if __name__ == '__main__':
    print('hello world')