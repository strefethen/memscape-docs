import init from './pkg/memscape_web.js';

try {
  await init();
} catch (error) {
  console.error(error);
  const notice = document.getElementById('error');
  notice.hidden = false;
  notice.textContent = `MemScape could not start: ${String(error)}`;
}
