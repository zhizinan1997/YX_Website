import imageio
import imageio_ffmpeg
import os

input_path = r"c:\Users\Ryan\Downloads\YX_Website\Video\video4.mp4"
output_path = r"c:\Users\Ryan\Downloads\YX_Website\Video\video5_compressed.mp4"

print(f"Checking input file: {input_path}")
if not os.path.exists(input_path):
    print("Error: Input file not found!")
    exit(1)

print("Starting compression... this might take a while.")

# Get ffmpeg exe path provided by imageio_ffmpeg
ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
print(f"Using ffmpeg from: {ffmpeg_exe}")

# Using subprocess for better argument handling
import subprocess

# Target: 720p, 1.5Mbps bitrate to reduce 142MB to ~10MB
# video4.mp4 is the input
cmd = [
    ffmpeg_exe,
    '-y', # Overwrite output file
    '-i', input_path,
    '-vf', 'scale=-2:720',
    '-b:v', '1500k',
    '-c:v', 'libx264',
    '-preset', 'medium',
    '-acodec', 'copy',
    output_path
]

print(f"Executing: {' '.join(cmd)}")
try:
    subprocess.run(cmd, check=True)
    ret = 0
except subprocess.CalledProcessError:
    ret = 1

if ret == 0:
    print("Compression successful!")
    print(f"Output saved to: {output_path}")
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"New file size: {size_mb:.2f} MB")
else:
    print("Compression failed.")
