// background.js - Minimal Service Worker (Server-Centric Architecture)
// Job management is handled entirely by the backend server.
// This Service Worker only provides extension lifecycle support.

console.log('SubtitleAI service worker started (server-centric mode)');

// Optional: Handle extension install/update events
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    console.log('Extension installed');
  } else if (details.reason === 'update') {
    console.log('Extension updated to version', chrome.runtime.getManifest().version);
  }
});

// Keep service worker alive during active jobs (optional)
// The popup now communicates directly with the server,
// so this is mainly for future extensibility.
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  // Reserved for future use (e.g., notifications, badge updates)
  if (request.action === 'ping') {
    sendResponse({ status: 'alive' });
    return true;
  }

  return false;
});
