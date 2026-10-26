// Switch between actual app screenshots; the timeline is visible before setup.
const controls = document.querySelector('.preview-controls');
const buttons = [...controls.querySelectorAll('button[data-view]')];

for (const button of buttons) {
  button.addEventListener('click', () => {
    for (const option of buttons) {
      const selected = option === button;
      option.setAttribute('aria-pressed', String(selected));
      document.getElementById(option.getAttribute('aria-controls')).hidden = !selected;
    }
  });
}
controls.hidden = false;
