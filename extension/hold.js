if (location.hash === '#held') {
  document.getElementById('t').textContent = 'Search held';
  document.getElementById('d').textContent = 'HonestHands stopped this search. Change it, or go back.';
  const b = document.getElementById('b'); b.hidden = false; b.onclick = () => history.back();
}
