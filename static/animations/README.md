# Welcome background animation

The welcome page at `/` has a static farm image by default. No video or third-party
embed is bundled or implied to be configured. To add an animation, supply a video
you have permission to use and edit `static/js/welcome-animation-config.js`.

## Local video (recommended)

1. Put optimized `.mp4` (H.264) or `.webm` files in this folder.
2. Set `enabled: true`, keep `sourceType: "local"`, and list the files:

   ```js
   desktopSources: [
       { url: "/static/animations/welcome-desktop.webm", type: "video/webm" },
       { url: "/static/animations/welcome-desktop.mp4", type: "video/mp4" }
   ],
   mobileSources: [
       { url: "/static/animations/welcome-mobile.mp4", type: "video/mp4" }
   ],
   ```

3. Keep the video short and compressed. The page uses a muted, inline video,
   respects reduced-motion preferences, and retains the static image if playback
   is unavailable.

## HTTPS video or supported embed

For a direct file hosted elsewhere, set `sourceType: "direct"`, provide an HTTPS
`directVideoUrl`, and set `directMimeType` to `video/mp4` or `video/webm`. For an
embed, set `sourceType: "embed"` and `embedUrl` to a YouTube or Vimeo URL. The
player URL is constructed by the application; arbitrary iframe hosts are not
accepted. External media may have provider privacy, bandwidth, and availability
implications.

Do not put API keys or secrets in this public JavaScript configuration.
