/* Run: node tests/test_mobile_plan_ui.js */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {
  localDateKey, addDays, getWeekDates, getPlanOverview,
  getVisiblePlanTasks, splitReminders,
} = require('../mobile/src/plan-utils');

assert.equal(localDateKey(new Date(2026, 9, 25, 23, 55)), '2026-10-25');
assert.equal(addDays('2026-10-25', 7), '2026-11-01');
assert.equal(addDays('2026-11-01', -7), '2026-10-25');
assert.deepEqual(getWeekDates('2026-10-25'), [
  '2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22',
  '2026-10-23', '2026-10-24', '2026-10-25'
]);
assert.deepEqual(getWeekDates('2026-10-26'), [
  '2026-10-26', '2026-10-27', '2026-10-28', '2026-10-29',
  '2026-10-30', '2026-10-31', '2026-11-01'
]);

const tasks = [
  { id: 3, study_at: '2026-10-25T20:00', duration: 45, done: 1 },
  { id: 4, study_at: '2026-10-26T20:00', duration: 30, done: 0 },
  { id: 2, study_at: '2026-10-25T09:00', duration: 30, done: 0 },
  { id: 1, study_at: '2026-10-23T08:00', duration: 45, done: 1 }
];
assert.deepEqual(getVisiblePlanTasks(tasks, '2026-10-25', false).map(t => t.id), [2,3]);
assert.deepEqual(getVisiblePlanTasks(tasks, '2026-10-25', true).map(t => t.id), [1,2,3,4]);
assert.equal(tasks[0].id, 3, 'Filter must not mutate original API results');
const stats = getPlanOverview(tasks, '2026-10-25');
assert.deepEqual(stats, { total: 3, completed: 2, percentage: 67, minutes: 120, completedMinutes: 90 });
assert.deepEqual(getPlanOverview([], '2026-10-25'), {
  total: 0, completed: 0, percentage: 0, minutes: 0, completedMinutes: 0
});

const reminders = [
  { id: 1, due_at: '2026-10-25T22:00', done: 1 },
  { id: 2, due_at: '2026-10-26T20:00', done: 0 },
  { id: 3, due_at: '2026-10-25T19:00', done: 0 },
  { id: 4, due_at: '2026-10-24T12:00', done: 1 },
];
const sorted = splitReminders(reminders);
assert.deepEqual(sorted.pending.map(r => r.id), [3,2]);
assert.deepEqual(sorted.completed.map(r => r.id), [1,4]);
assert.equal(reminders[0].id, 1, 'Sorting must not alter API source array');

// Static presentation contract: Mobile is for students; Admin remains Web-only.
// The Expo iOS export in CI validates all JSX syntax and React Native bundling.
const app = fs.readFileSync(path.join(__dirname, '../mobile/App.js'), 'utf8');
assert.ok(app.includes('getWeekDates(selectedDate)'), 'Week calendar must render');
assert.ok(app.includes("planView === 'list'"), 'List view must remain available');
assert.ok(app.includes('getPlanOverview(tasks, selectedDate)'), 'Progress based on selected week');
assert.ok(app.includes('splitReminders(reminders)'), 'Completed deadlines must be grouped');
assert.ok(app.includes('accessibilityState={{ expanded: showCompletedReminders }}'));
assert.ok(app.includes("Quản trị viên chỉ đăng nhập trên Web."));
assert.ok(app.includes('secureTextEntry={!showPassword}'));
assert.ok(app.includes('secureTextEntry={!showConfirm}'));
assert.ok(!app.includes('onAdminRegister'), 'No self-service mobile Admin registration');
assert.ok(!app.includes('api.adminLogin'), 'Admin login stays exclusively in Web interface');
assert.ok(app.includes("muted: { color: '#53678B'"), 'Improve helper-text contrast');
assert.ok(app.includes("navLabel: { fontSize: 10, color: '#637493'"), 'Readable bottom navigation');
console.log('Mobile readability, planner week and deadline grouping QA passed');
