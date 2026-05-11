// popup.js - Chrome Extension Popup Logic (Server-Centric)

const API_BASE = 'http://localhost:8000';

// State
let currentVideoId = null;
let currentVideoTitle = null;
let currentJobId = null;
let subtitles = [];
let statusPollInterval = null;
let serverOnline = false;

// DOM Elements
const serverStatus = document.getElementById('serverStatus');
const serverStatusText = document.getElementById('serverStatusText');
const videoInfo = document.getElementById('videoInfo');
const sourceLanguage = document.getElementById('sourceLanguage');
const targetLanguage = document.getElementById('targetLanguage');
const generateBtn = document.getElementById('generateBtn');
const progressSection = document.getElementById('progressSection');
const progressStatus = document.getElementById('progressStatus');
const progressPercent = document.getElementById('progressPercent');
const progressBar = document.getElementById('progressBar');
const resultsSection = document.getElementById('resultsSection');
const resultContent = document.getElementById('resultContent');
const showOnVideoBtn = document.getElementById('showOnVideoBtn');
const forceRegenerate = document.getElementById('forceRegenerate');
const savePath = document.getElementById('savePath');
const toast = document.getElementById('toast');
const loadFileBtn = document.getElementById('loadFileBtn');
const loadFileInput = document.getElementById('loadFileInput');

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
  await checkServerStatus();
  await getCurrentVideo();
  loadSettings();
  await checkOngoingJob();
});

// Cleanup on popup close
window.addEventListener('unload', () => {
  if (statusPollInterval) {
    clearInterval(statusPollInterval);
  }
});

// Check server status
async function checkServerStatus() {
  try {
    const response = await fetch(`${API_BASE}/health`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' }
    });

    if (response.ok) {
      serverOnline = true;
      serverStatus.classList.add('connected');
      serverStatus.classList.remove('error');
      serverStatusText.textContent = 'Server Connected';
    } else {
      throw new Error('Server not responding');
    }
  } catch (error) {
    serverOnline = false;
    serverStatus.classList.add('error');
    serverStatus.classList.remove('connected');
    serverStatusText.textContent = 'Server Offline';
  }
}

// Inject content script into tab if not already present
async function injectContentScript(tabId) {
  await chrome.scripting.executeScript({ target: { tabId }, files: ['content.js'] });
  await chrome.scripting.insertCSS({ target: { tabId }, files: ['content.css'] });
}

// Send message to content script, injecting it first if not loaded
function sendToContentScript(tabId, message, callback) {
  chrome.tabs.sendMessage(tabId, message, (response) => {
    if (chrome.runtime.lastError) {
      injectContentScript(tabId).then(() => {
        chrome.tabs.sendMessage(tabId, message, (retryResponse) => {
          if (chrome.runtime.lastError) {
            callback(null);
          } else {
            callback(retryResponse);
          }
        });
      }).catch(() => callback(null));
    } else {
      callback(response);
    }
  });
}

// Get current YouTube video from active tab
async function getCurrentVideo() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (tab && tab.url && tab.url.includes('youtube.com/watch')) {
      const url = new URL(tab.url);
      const videoId = url.searchParams.get('v');

      if (videoId) {
        currentVideoId = videoId;

        sendToContentScript(tab.id, { action: 'getVideoInfo' }, (response) => {
          if (response && response.title) {
            currentVideoTitle = response.title;
            updateVideoInfo(response);
          } else {
            currentVideoTitle = tab.title.replace(' - YouTube', '');
            updateVideoInfo({
              title: currentVideoTitle,
              channel: '',
              thumbnail: `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`
            });
          }

          generateBtn.disabled = false;
        });
      }
    } else {
      updateVideoInfo(null);
    }
  } catch (error) {
    console.error('Error getting current video:', error);
    updateVideoInfo(null);
  }
}

// Check for ongoing job on popup open
async function checkOngoingJob() {
  if (!currentVideoId) return;

  try {
    // Check if we have a stored job_id for this video
    const stored = await chrome.storage.local.get([`currentJob_${currentVideoId}`]);
    const storedJobId = stored[`currentJob_${currentVideoId}`];

    if (storedJobId) {
      // Check job status on server
      const state = await getServerJobStatus(storedJobId);

      if (state && isJobRunning(state.status)) {
        // Job is still running on server - resume UI
        currentJobId = storedJobId;
        showProgressUI(state);
        startStatusPolling();
        return;
      }

      // Job completed or not found - clean up stored ID
      await chrome.storage.local.remove([`currentJob_${currentVideoId}`]);

      // If job completed, show results
      if (state && state.status === 'complete' && state.subtitles) {
        subtitles = state.subtitles;
        displaySubtitles(subtitles);
        resultsSection.classList.add('visible');
        showToast('Subtitles ready!');
        return;
      }
    }

    // No active job - check server cache for completed results (only if server is online)
    const targetLang = targetLanguage.value;
    if (serverOnline) {
      const cacheResult = await checkServerCache(currentVideoId, targetLang);
      if (cacheResult) {
        subtitles = cacheResult.subtitles;
        displaySubtitles(subtitles);
        resultsSection.classList.add('visible');
        showToast(`Loaded subtitles from server (${cacheResult.source})`);
      }
    }
  } catch (error) {
    console.error('Error checking ongoing job:', error);
  }
}

// Check if job status indicates running
function isJobRunning(status) {
  return ['pending', 'extracting', 'transcribing', 'translating'].includes(status);
}

// Server API: Start a new job
async function startServerJob(videoId, source, target, forceRegen = false) {
  try {
    const response = await fetch(`${API_BASE}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_id: videoId,
        source_language: source === 'auto' ? null : source,
        target_language: target,
        force_regenerate: forceRegen,
        save_path: savePath.value || null
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to start job');
    }

    const data = await response.json();
    currentJobId = data.job_id;

    // Store job_id for popup resume
    await chrome.storage.local.set({ [`currentJob_${videoId}`]: data.job_id });

    return { started: true, job_id: data.job_id };
  } catch (error) {
    console.error('Error starting server job:', error);
    return { started: false, error: error.message };
  }
}

// Server API: Get job status
async function getServerJobStatus(jobId) {
  try {
    const response = await fetch(`${API_BASE}/jobs/${jobId}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' }
    });

    if (response.status === 404) {
      return null;
    }

    if (!response.ok) {
      throw new Error('Failed to get job status');
    }

    return await response.json();
  } catch (error) {
    console.warn('Error getting server job status:', error);
    return null;
  }
}

// Server API: Check cached subtitles
async function checkServerCache(videoId, language) {
  try {
    const sp = savePath.value ? `&save_path=${encodeURIComponent(savePath.value)}` : '';
    const response = await fetch(`${API_BASE}/subtitles/${videoId}?language=${language}${sp}`, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' }
    });

    if (response.ok) {
      const data = await response.json();
      if (data.success && data.subtitles && data.subtitles.length > 0) {
        return {
          subtitles: data.subtitles,
          source: data.source,
          language: data.language
        };
      }
    }
  } catch (error) {
    console.warn('Failed to check server cache:', error);
  }
  return null;
}

// Show progress UI from job state
function showProgressUI(state) {
  generateBtn.disabled = true;
  generateBtn.classList.add('loading');
  generateBtn.innerHTML = '<div class="spinner"></div> Processing...';
  progressSection.classList.add('visible');
  resultsSection.classList.remove('visible');

  updateProgress(state.progress, state.message);
  updateStepFromState(state.step);
}

// Start polling for job status (server-direct)
function startStatusPolling() {
  if (statusPollInterval) {
    clearInterval(statusPollInterval);
  }

  statusPollInterval = setInterval(async () => {
    if (!currentJobId) return;

    const state = await getServerJobStatus(currentJobId);

    if (!state) {
      // Job not found on server - check cache
      stopStatusPolling();
      const targetLang = targetLanguage.value;
      const cacheResult = await checkServerCache(currentVideoId, targetLang);

      if (cacheResult && cacheResult.source === 'translation') {
        subtitles = cacheResult.subtitles;
        displaySubtitles(subtitles);
        updateProgress(100, 'Complete!');
        updateStepFromState(4);

        setTimeout(() => {
          progressSection.classList.remove('visible');
          resultsSection.classList.add('visible');
          resetGenerateButton();
        }, 500);

        showToast('Subtitles ready!');
      } else {
        resetGenerateButton();
        progressSection.classList.remove('visible');
        if (cacheResult) {
          subtitles = cacheResult.subtitles;
          displaySubtitles(subtitles);
          resultsSection.classList.add('visible');
          showToast('Showing transcript (translation not found)');
        }
      }

      await chrome.storage.local.remove([`currentJob_${currentVideoId}`]);
      return;
    }

    // Update progress UI
    updateProgress(state.progress, state.message);
    updateStepFromState(state.step);

    // Show batch progress if translating
    if (state.batch_current && state.batch_total) {
      updateProgress(state.progress, `Translating batch ${state.batch_current}/${state.batch_total}...`);
    }

    if (state.status === 'complete') {
      stopStatusPolling();

      if (state.subtitles && state.subtitles.length > 0) {
        subtitles = state.subtitles;
        displaySubtitles(subtitles);
      }

      updateProgress(100, 'Complete!');
      updateStepFromState(4);

      setTimeout(() => {
        progressSection.classList.remove('visible');
        resultsSection.classList.add('visible');
        resetGenerateButton();
      }, 500);

      showToast('Subtitles generated successfully!');
      await chrome.storage.local.remove([`currentJob_${currentVideoId}`]);

    } else if (state.status === 'error') {
      stopStatusPolling();
      showToast(state.error || 'Failed to generate subtitles');
      progressSection.classList.remove('visible');
      resetGenerateButton();
      await chrome.storage.local.remove([`currentJob_${currentVideoId}`]);
    }
  }, 1000); // Poll every 1 second (server handles timing)
}

// Stop polling
function stopStatusPolling() {
  if (statusPollInterval) {
    clearInterval(statusPollInterval);
    statusPollInterval = null;
  }
}

// Update step indicators from state
function updateStepFromState(currentStep) {
  for (let i = 1; i <= 4; i++) {
    const step = document.getElementById(`step${i}`);
    step.classList.remove('active', 'completed');

    if (i < currentStep) {
      step.classList.add('completed');
      const icon = step.querySelector('.step-icon');
      icon.innerHTML = '<svg viewBox="0 0 24 24"><path d="M9 16.2L4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4L9 16.2z"/></svg>';
    } else if (i === currentStep) {
      step.classList.add('active');
      const icon = step.querySelector('.step-icon');
      icon.innerHTML = '<div class="spinner" style="width: 14px; height: 14px; border-width: 2px;"></div>';
    }
  }
}

// Reset generate button to default state
function resetGenerateButton() {
  generateBtn.disabled = false;
  generateBtn.classList.remove('loading');
  generateBtn.innerHTML = `
    <svg viewBox="0 0 24 24">
      <path d="M9 16.2L4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4L9 16.2z"/>
    </svg>
    Generate Subtitles
  `;
}

// Update video info display
function updateVideoInfo(info) {
  if (!info) {
    videoInfo.innerHTML = `
      <div class="no-video">
        <p>Navigate to a YouTube video to get started</p>
      </div>
    `;
    generateBtn.disabled = true;
    return;
  }

  videoInfo.innerHTML = `
    <div class="video-info">
      <div class="video-thumbnail">
        <img src="${info.thumbnail}" alt="Thumbnail" onerror="this.parentElement.classList.add('placeholder'); this.style.display='none';">
      </div>
      <div class="video-details">
        <div class="video-title">${escapeHtml(info.title)}</div>
        ${info.channel ? `<div class="video-channel">${escapeHtml(info.channel)}</div>` : ''}
      </div>
    </div>
  `;
}

// Load saved settings
function loadSettings() {
  chrome.storage.local.get(['sourceLanguage', 'targetLanguage', 'savePath'], (result) => {
    if (result.sourceLanguage) {
      sourceLanguage.value = result.sourceLanguage;
    }
    if (result.targetLanguage) {
      targetLanguage.value = result.targetLanguage;
    }
    if (result.savePath) {
      savePath.value = result.savePath;
    }
  });
}

// Save settings
function saveSettings() {
  chrome.storage.local.set({
    sourceLanguage: sourceLanguage.value,
    targetLanguage: targetLanguage.value,
    savePath: savePath.value
  });
}

// Event Listeners
sourceLanguage.addEventListener('change', saveSettings);
targetLanguage.addEventListener('change', saveSettings);
savePath.addEventListener('change', saveSettings);

generateBtn.addEventListener('click', async () => {
  if (!currentVideoId) {
    showToast('No YouTube video detected');
    return;
  }

  if (!serverOnline) {
    showToast('Server is offline. Start it with: python server.py');
    return;
  }

  await generateSubtitles();
});

showOnVideoBtn.addEventListener('click', async () => {
  if (!currentVideoId || subtitles.length === 0) {
    showToast('No subtitles to display');
    return;
  }

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    if (!tab || !tab.url || !tab.url.includes('youtube.com/watch')) {
      showToast('Please navigate to the YouTube video page');
      return;
    }

    sendToContentScript(tab.id, { action: 'startSubtitleSync', subtitles }, (response) => {
      if (response && response.success) {
        showToast('Subtitles now showing on video!');
      } else {
        showToast('Failed to show subtitles on video. Refresh the page and try again.');
      }
    });
  } catch (error) {
    console.error('Error showing subtitles on video:', error);
    showToast('Failed to show subtitles on video');
  }
});

// Generate subtitles - direct server communication
async function generateSubtitles() {
  const source = sourceLanguage.value;
  const target = targetLanguage.value;
  const forceRegen = forceRegenerate.checked;

  // Show progress
  generateBtn.disabled = true;
  generateBtn.classList.add('loading');
  generateBtn.innerHTML = '<div class="spinner"></div> Processing...';
  progressSection.classList.add('visible');
  resultsSection.classList.remove('visible');

  resetProgress();

  // Start job on server
  const result = await startServerJob(currentVideoId, source, target, forceRegen);

  if (result.started) {
    startStatusPolling();
  } else {
    showToast(result.error || 'Failed to start job');
    resetGenerateButton();
    progressSection.classList.remove('visible');
  }
}

// Progress helpers
function resetProgress() {
  progressBar.style.width = '0%';
  progressPercent.textContent = '0%';
  progressStatus.textContent = 'Starting...';

  for (let i = 1; i <= 4; i++) {
    const step = document.getElementById(`step${i}`);
    step.classList.remove('active', 'completed');
  }
}

function updateProgress(percent, status) {
  progressBar.style.width = `${percent}%`;
  progressPercent.textContent = `${percent}%`;
  progressStatus.textContent = status;
}

// Display subtitles
function displaySubtitles(subs) {
  resultContent.innerHTML = subs.map(sub => {
    let textDisplay = escapeHtml(sub.text);
    if (sub.original_text && sub.original_text !== sub.text) {
      textDisplay = `${escapeHtml(sub.original_text)}<br><span style="opacity: 0.8;">${escapeHtml(sub.text)}</span>`;
    }

    return `
      <div class="subtitle-line">
        <span class="subtitle-time">${formatTime(sub.start)}</span>
        <span class="subtitle-text">${textDisplay}</span>
      </div>
    `;
  }).join('');
}

// Time formatting helpers
function formatTime(seconds) {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

// Toast notification
function showToast(message) {
  toast.textContent = message;
  toast.classList.add('visible');

  setTimeout(() => {
    toast.classList.remove('visible');
  }, 3000);
}

// Load subtitle JSON file from local filesystem
loadFileBtn.addEventListener('click', () => loadFileInput.click());

loadFileInput.addEventListener('change', (event) => {
  const file = event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (e) => {
    try {
      const data = JSON.parse(e.target.result);

      // Support both {segments: [...]} and raw array formats
      const segments = Array.isArray(data) ? data : data.segments;

      if (!segments || segments.length === 0) {
        showToast('No subtitle segments found in file');
        return;
      }

      subtitles = segments.map(s => ({
        start: s.start,
        end: s.end,
        text: s.text,
        original_text: s.original_text || null,
        speaker_id: s.speaker_id || null
      }));

      displaySubtitles(subtitles);
      resultsSection.classList.add('visible');
      showToast(`Loaded ${subtitles.length} subtitles from file`);
    } catch {
      showToast('Failed to parse subtitle file. Make sure it is a valid JSON file.');
    }
  };
  reader.readAsText(file);
  // Reset input so the same file can be selected again
  loadFileInput.value = '';
});

// Utility
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}
