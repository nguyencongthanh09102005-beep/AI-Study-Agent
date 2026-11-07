"use strict";
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const app=fs.readFileSync('mobile/App.js','utf8');
const connection=fs.readFileSync('mobile/src/ConnectionSettings.js','utf8');
const storage=fs.readFileSync('mobile/src/serverAddressStorage.js','utf8');
const room=fs.readFileSync('mobile/src/ManualStudyRoom.js','utf8');
const api=fs.readFileSync('mobile/src/api.js','utf8');
const backend=fs.readFileSync('manual_lesson_routes.py','utf8');
const pkg=require('../mobile/package.json');

assert.equal(pkg.dependencies['@react-native-async-storage/async-storage'],'2.2.0');
assert(pkg.dependencies['expo-file-system']&&pkg.dependencies['expo-sharing']);
assert(app.indexOf('restoreServerAddress()') < app.indexOf('.then(() => api.session())'),
  'Saved IP must be restored BEFORE session check');
assert(connection.includes('testApiConnection(address)') &&
       connection.includes('persistServerAddress(address)'),
       'Save address only after confirming connection');
assert(!connection.includes('Địa chỉ đổi tại đây chỉ có hiệu lực'),
  'Mobile help should no longer claim the saved address is temporary');
assert(app.includes('<ManualStudyRoom key={activeManualTask}'));
assert(app.includes('onOpenManualStudy(task.id)') &&
       app.includes('task.source === \'manual\' && task.document_id'));
assert(app.includes('!activeManualTask && <FloatingStudyChat'),
  'Course chat bubble must not mix with private document room');
for(const method of ['manualRoom','manualTimer','manualAsk','manualPrepareQuiz','manualFile']) {
  assert(api.includes(method+':'),method+' API missing');
}
assert(room.includes('file.write(payload.base64') && room.includes('file.preview('),
  'Source PDF/Word must open using private cached file');
assert(room.includes('api.manualTimer(taskId,action,csrf.current)'));
assert(room.includes('api.manualAsk(taskId,question.trim(),csrf.current)'));
assert(room.includes('api.manualPrepareQuiz(taskId,csrf.current)'));
assert(room.includes("if (await sendTimerAction('pause')) onBack()"));
assert(backend.includes('def mobile_manual_timer(') &&
       backend.includes('def mobile_manual_ask('));
assert(backend.includes('context(project, conn, uid, task_id)'),
  'Private file must be owner-verified');

async function testSavedAddress(){
  let active='http://10.0.2.2:5000', saved=null, writes=0, failWrite=false;
  const AsyncStorage={
    getItem:async key=>{assert(key.includes('flask-api-origin'));return saved;},
    setItem:async(_key,value)=>{writes++;if(failWrite)throw Error('disk full');saved=value;},
    removeItem:async()=>{saved=null;},
  };
  const getApiBaseUrl=()=>active;
  const setApiBaseUrl=value=>{
    if(!/^https?:\/\/[a-z0-9.-]+(?::\d{1,5})?$/i.test(value))throw Error('bad URL');
    active=value;return active;
  };
  const source=storage
    .replace(/^import .*;\s*$/gm,'')
    .replace(/export async function /g,'async function ')+
    '\nmodule.exports={restoreServerAddress,persistServerAddress};';
  const sandbox={AsyncStorage,getApiBaseUrl,setApiBaseUrl,module:{exports:{}}};
  vm.runInNewContext(source,sandbox);
  const {restoreServerAddress,persistServerAddress}=sandbox.module.exports;
  assert.equal(await restoreServerAddress(),'http://10.0.2.2:5000');
  assert.equal(await persistServerAddress('http://192.168.1.27:5000'),'http://192.168.1.27:5000');
  assert.equal(writes,1);
  active='http://10.0.2.2:5000';
  assert.equal(await restoreServerAddress(),'http://192.168.1.27:5000');
  failWrite=true;
  await assert.rejects(()=>persistServerAddress('http://192.168.1.28:5000'));
  assert.equal(active,'http://192.168.1.27:5000','Failed persistence must rollback live host');
  failWrite=false;
  saved='invalid://server';
  assert.equal(await restoreServerAddress(),'http://192.168.1.27:5000');
  assert.equal(saved,null,'Corrupt origin must not become active');
}
testSavedAddress().then(()=>console.log('Mobile persisted server + manual study UI PASS'))
  .catch(err=>{console.error(err);process.exitCode=1;});
