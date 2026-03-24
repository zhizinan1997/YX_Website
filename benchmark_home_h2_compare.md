# Homepage & H2 Homepage Benchmark (No Browser Cache)

- Base URL: `http://localhost:8000`
- Runs per strategy: `3`
- No-cache controls: `Cache-Control/Pragma + unique cache-busting query`

## Strategy Semantics

- `initial/home`: fetch `/api/hero` -> preload all hero images concurrently -> fetch `/api/h2-home` -> full prefetch first N videos.
- `current/home`: fetch `/api/hero` -> load first hero image -> warm next 2 images -> fetch `/api/h2-home` -> range prefetch first video.
- `initial/h2`: fetch `/api/h2-home` -> range fetch first video (as first-play proxy), no next-video preload.
- `current/h2`: fetch `/api/h2-home` -> range fetch first video -> range preload next video metadata.

## Average Comparison

| Metric | Initial | Current | Delta (Current - Initial) |
|---|---:|---:|---:|
| Homepage first media ready | 4.829s | 0.909s | -3.920s |
| Homepage all resources done | 13.154s | 5.891s | -7.263s |
| H2 first media ready | 0.539s | 0.504s | -0.036s |
| H2 all resources done | 0.539s | 0.831s | 0.292s |
| Homepage all images full download | 12.152s | 12.128s | -0.024s |
| H2 all videos full download | 2.738s | 3.423s | 0.685s |

## Per-Run Detail

### initial / run 1
- homepage_first_media: 7.744s
- homepage_all_resources: 12.382s
- h2_first_media: 0.487s
- h2_all_resources: 0.487s
- homepage_all_images_full_download: 11.558s
- h2_all_videos_full_download: 2.668s

### initial / run 2
- homepage_first_media: 3.274s
- homepage_all_resources: 11.875s
- h2_first_media: 0.616s
- h2_all_resources: 0.616s
- homepage_all_images_full_download: 10.222s
- h2_all_videos_full_download: 2.888s

### initial / run 3
- homepage_first_media: 3.469s
- homepage_all_resources: 15.204s
- h2_first_media: 0.515s
- h2_all_resources: 0.515s
- homepage_all_images_full_download: 14.676s
- h2_all_videos_full_download: 2.658s

### current / run 1
- homepage_first_media: 0.750s
- homepage_all_resources: 5.744s
- h2_first_media: 0.372s
- h2_all_resources: 0.749s
- homepage_all_images_full_download: 10.475s
- h2_all_videos_full_download: 1.587s

### current / run 2
- homepage_first_media: 0.799s
- homepage_all_resources: 5.805s
- h2_first_media: 0.503s
- h2_all_resources: 0.845s
- homepage_all_images_full_download: 10.824s
- h2_all_videos_full_download: 3.982s

### current / run 3
- homepage_first_media: 1.177s
- homepage_all_resources: 6.123s
- h2_first_media: 0.636s
- h2_all_resources: 0.900s
- homepage_all_images_full_download: 15.084s
- h2_all_videos_full_download: 4.701s
