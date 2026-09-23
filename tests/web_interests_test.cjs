const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({ document: { addEventListener() {} } });
vm.runInContext(fs.readFileSync('src/web/static/app.js', 'utf8'), context);
for (const completed of [true, false]) {
  vm.runInContext(`state.settings = {onboarding_completed: ${completed}}; state.profile = null; state.interests = []; state.signals = []; detectFirstRun();`, context);
  assert.equal(vm.runInContext('state.firstRun', context), !completed);
}
vm.runInContext('state.settings = null; detectFirstRun();', context);
assert.equal(vm.runInContext('state.firstRun', context), false);
console.log('Onboarding visibility checks passed');
