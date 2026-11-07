/* Date/time values stay local, as expected by the Flask study-plan APIs.
   Never serialize via toISOString(): UTC can shift a chosen Vietnam date. */
const pad = n => String(n).padStart(2, '0');

function parseLocalDateTime(value) {
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/);
  if (!match) return null;
  const [year, month, day, hour, minute] = match.slice(1).map(Number);
  const date = new Date(year, month - 1, day, hour, minute, 0, 0);
  if (year < 2000 || year > 2100 || date.getFullYear() !== year ||
      date.getMonth() !== month - 1 || date.getDate() !== day ||
      date.getHours() !== hour || date.getMinutes() !== minute) return null;
  return {year,month,day,hour,minute};
}

function dateTimeString({year,month,day,hour,minute}) {
  return `${year}-${pad(month)}-${pad(day)}T${pad(hour)}:${pad(minute)}`;
}

function localDateTimeLabel(value) {
  const date = parseLocalDateTime(value);
  return date ? `${pad(date.day)}/${pad(date.month)}/${date.year} · ${pad(date.hour)}:${pad(date.minute)}`
              : 'Chọn ngày và giờ';
}

function monthCells(year, month) {
  const first = new Date(year,month-1,1);
  const offset = (first.getDay()+6)%7;
  const last = new Date(year,month,0).getDate();
  return [...Array(offset).fill(null), ...Array.from({length:last},(_,i)=>i+1)];
}
module.exports={parseLocalDateTime,dateTimeString,localDateTimeLabel,monthCells};
