// content.js - Content Script for YouTube pages

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getVideoInfo') {
    sendResponse(getVideoInfo());
  } else if (request.action === 'startSubtitleSync') {
    startSubtitleSync(request.subtitles);
    sendResponse({ success: true });
  } else if (request.action === 'stopSubtitleSync') {
    stopSubtitleSync();
    sendResponse({ success: true });
  }
  return true;
});

// Get video information from YouTube page
function getVideoInfo() {
  try {
    // Get video ID from URL
    const urlParams = new URLSearchParams(window.location.search);
    const videoId = urlParams.get('v');

    if (!videoId) {
      console.warn('No video ID found in URL');
      return null;
    }

    // Get video title
    const titleElement = document.querySelector('h1.ytd-video-primary-info-renderer yt-formatted-string') ||
                        document.querySelector('h1.title') ||
                        document.querySelector('#title h1') ||
                        document.querySelector('h1.ytd-watch-metadata yt-formatted-string');

    const title = titleElement ? titleElement.textContent.trim() : document.title.replace(' - YouTube', '');

    // Get channel name
    const channelElement = document.querySelector('#channel-name a') ||
                          document.querySelector('ytd-channel-name a') ||
                          document.querySelector('.ytd-channel-name a');

    const channel = channelElement ? channelElement.textContent.trim() : '';

    // Get thumbnail
    const thumbnail = `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`;

    return {
      title,
      channel,
      thumbnail,
      videoId
    };
  } catch (error) {
    console.error('Error getting video info:', error.message, error.stack);
    // Return fallback info with at least the video ID
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const videoId = urlParams.get('v');
      if (videoId) {
        return {
          title: document.title.replace(' - YouTube', ''),
          channel: '',
          thumbnail: `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`,
          videoId
        };
      }
    } catch (fallbackError) {
      console.error('Fallback also failed:', fallbackError);
    }
    return null;
  }
}

// Inject subtitles overlay (optional feature)
function createSubtitleOverlay() {
  // Check if overlay already exists
  if (document.getElementById('ai-subtitle-overlay')) return;
  
  const overlay = document.createElement('div');
  overlay.id = 'ai-subtitle-overlay';
  overlay.innerHTML = `
    <div class="ai-subtitle-container">
      <div class="ai-subtitle-text"></div>
    </div>
  `;
  
  // Find video player
  const player = document.querySelector('.html5-video-player');
  if (player) {
    player.appendChild(overlay);
  }
}

// Update subtitle text
function updateSubtitle(text, originalText = null) {
  const subtitleText = document.querySelector('.ai-subtitle-text');
  if (subtitleText) {
    if (text) {
      // Show both original and translation if available
      if (originalText && originalText !== text) {
        subtitleText.innerHTML = `
          <div style="margin-bottom: 4px;">${escapeHtml(originalText)}</div>
          <div style="opacity: 0.9;">${escapeHtml(text)}</div>
        `;
      } else {
        subtitleText.textContent = text;
      }
      subtitleText.style.display = 'block';
    } else {
      subtitleText.textContent = '';
      subtitleText.style.display = 'none';
    }
  }
}

// Helper function to escape HTML
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Track video time for subtitle sync
let currentSubtitles = [];
let subtitleInterval = null;
let syncedVideoId = null;

// Detect YouTube SPA navigation and stop subtitles on video change
function onVideoChange() {
  const newVideoId = new URLSearchParams(window.location.search).get('v');
  if (newVideoId !== syncedVideoId && syncedVideoId !== null) {
    stopSubtitleSync();
    const overlay = document.getElementById('ai-subtitle-overlay');
    if (overlay) overlay.remove();
    syncedVideoId = null;
  }
}

// Guard against re-injection: only patch History API and register navigation
// listeners once per isolated world, otherwise repeated injections would stack
// wrappers and double-fire onVideoChange.
if (!window.__subtitleAiNavPatched) {
  window.__subtitleAiNavPatched = true;

  // YouTube fires this custom event on SPA navigation
  window.addEventListener('yt-navigate-finish', onVideoChange);

  // Fallback: intercept History API
  const origPushState = history.pushState;
  history.pushState = function () {
    origPushState.apply(this, arguments);
    onVideoChange();
  };
  const origReplaceState = history.replaceState;
  history.replaceState = function () {
    origReplaceState.apply(this, arguments);
    onVideoChange();
  };
  window.addEventListener('popstate', onVideoChange);
}

function startSubtitleSync(subtitles) {
  currentSubtitles = subtitles;
  syncedVideoId = new URLSearchParams(window.location.search).get('v');

  if (subtitleInterval) {
    clearInterval(subtitleInterval);
  }
  
  const video = document.querySelector('video');
  if (!video) return;
  
  createSubtitleOverlay();
  
  subtitleInterval = setInterval(() => {
    const currentTime = video.currentTime;
    const currentSub = currentSubtitles.find(
      sub => currentTime >= sub.start && currentTime <= sub.end
    );

    updateSubtitle(
      currentSub ? currentSub.text : '',
      currentSub ? currentSub.original_text : null
    );
  }, 100);
}

function stopSubtitleSync() {
  if (subtitleInterval) {
    clearInterval(subtitleInterval);
    subtitleInterval = null;
  }
  updateSubtitle('');
}

// Clean up on page unload or visibility change
function cleanupSubtitles() {
  if (subtitleInterval) {
    console.log('Cleaning up subtitle interval');
    stopSubtitleSync();
  }
}

window.addEventListener('pagehide', cleanupSubtitles);

// Pause subtitle sync when tab is hidden, resume when visible
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    if (subtitleInterval) {
      clearInterval(subtitleInterval);
      subtitleInterval = null;
    }
  } else if (currentSubtitles.length > 0 && syncedVideoId && !subtitleInterval) {
    startSubtitleSync(currentSubtitles);
  }
});

// Clean up when video ends or is paused (optional)
function attachVideoListeners() {
  const video = document.querySelector('video');
  if (video) {
    video.addEventListener('ended', () => {
      console.log('Video ended, stopping subtitle sync');
      stopSubtitleSync();
    });
  }
}

// Try to attach video listeners when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', attachVideoListeners);
} else {
  attachVideoListeners();
}

console.log('SubtitleAI content script loaded');
