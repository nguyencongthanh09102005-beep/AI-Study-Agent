/* Shared by React Native and a zero-dependency Node regression test.
   Use local calendar dates, not toISOString() (UTC can shift dates in Vietnam).
 */
const pad2 = value => String(value).padStart(2, '0');

function localDateKey(date) {
  const d = date instanceof Date ? date : new Date(String(date).slice(0, 10) + 'T12:00:00');
  if (Number.isNaN(d.getTime())) return '';
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function addDays(dateKey, delta) {
  const d = new Date(String(dateKey).slice(0, 10) + 'T12:00:00');
  if (Number.isNaN(d.getTime())) return dateKey;
  d.setDate(d.getDate() + delta);
  return localDateKey(d);
}

function getWeekDates(dateKey) {
  const d = new Date(String(dateKey).slice(0, 10) + 'T12:00:00');
  if (Number.isNaN(d.getTime())) return [];
  const mondayShift = (d.getDay() + 6) % 7;
  const monday = addDays(localDateKey(d), -mondayShift);
  return Array.from({ length: 7 }, (_, i) => addDays(monday, i));
}

function getPlanOverview(tasks = [], dateKey = localDateKey(new Date())) {
  const week = new Set(getWeekDates(dateKey));
  const weekTasks = (Array.isArray(tasks) ? tasks : []).filter(
    task => week.has(String(task.study_at || '').slice(0, 10))
  );
  const completed = weekTasks.filter(task => !!task.done).length;
  const minutes = weekTasks.reduce((sum, task) => sum + Math.max(0, Number(task.duration) || 0), 0);
  const completedMinutes = weekTasks.reduce(
    (sum, task) => sum + (task.done ? Math.max(0, Number(task.duration) || 0) : 0), 0
  );
  return {
    total: weekTasks.length,
    completed,
    percentage: weekTasks.length ? Math.round(completed / weekTasks.length * 100) : 0,
    minutes,
    completedMinutes,
  };
}

function getVisiblePlanTasks(tasks = [], dateKey, showAll = false) {
  return (Array.isArray(tasks) ? tasks : [])
    .filter(task => showAll || String(task.study_at || '').slice(0, 10) === dateKey)
    .slice()
    .sort((left, right) => String(left.study_at || '').localeCompare(String(right.study_at || '')));
}

function splitReminders(reminders = []) {
  const rows = Array.isArray(reminders) ? reminders : [];
  return {
    pending: rows.filter(item => !item.done).slice().sort(
      (a, b) => String(a.due_at || '').localeCompare(String(b.due_at || ''))
    ),
    completed: rows.filter(item => !!item.done).slice().sort(
      (a, b) => String(b.due_at || '').localeCompare(String(a.due_at || ''))
    )
  };
}

module.exports = {
  localDateKey, addDays, getWeekDates,
  getPlanOverview, getVisiblePlanTasks, splitReminders,
};
