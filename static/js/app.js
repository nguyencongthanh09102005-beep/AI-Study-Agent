document.querySelectorAll('input[type="range"]').forEach(el => {
  el.addEventListener('input', () => {
    const out = document.querySelector(`[data-output="${el.id}"]`);
    if(out) out.textContent = el.value + '%';
  });
});
