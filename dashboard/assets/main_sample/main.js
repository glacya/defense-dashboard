export default function ({ parentElement }) {
  const clock = parentElement.querySelector('#sample-clock');
  const update = () => {
    clock.textContent = new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul', dateStyle: 'medium', timeStyle: 'medium'
    }).format(new Date());
  };
  update();
  const timer = setInterval(update, 1000);
  const button = parentElement.querySelector('#sample-help');
  const note = parentElement.querySelector('#sample-note');
  const toggle = () => {
    note.hidden = !note.hidden;
    button.setAttribute('aria-expanded', String(!note.hidden));
  };
  button.addEventListener('click', toggle);
  return () => {
    clearInterval(timer);
    button.removeEventListener('click', toggle);
  };
}
