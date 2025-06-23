document.querySelectorAll(".joined-time").forEach(span => {
  const utcTime = span.dataset.utc;
  if (!utcTime) return;

  const utcDate = new Date(utcTime);
  const localDate = new Date(utcDate.getTime() + (utcDate.getTimezoneOffset() * -60000));
  const formatted = localDate.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    timeZoneName: "short"
  });
  span.innerText = formatted;
});
const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
tooltipTriggerList.map(el => new bootstrap.Tooltip(el));
