// Regression: never ship a project incompatible with iPhone Expo Go SDK 58.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const pkg = require(path.join(root, 'mobile/package.json'));
const config = require(path.join(root, 'mobile/app.json'));
const workflow = fs.readFileSync(path.join(root, '.github/workflows/ci.yml'), 'utf8');

assert.match(pkg.dependencies.expo, /^~58\./, 'Mobile Expo must match iPhone Expo Go SDK 58');
assert.match(pkg.dependencies['expo-document-picker'], /^~58\./, 'Document Picker must target SDK 58');
assert.match(pkg.dependencies['react-native'], /^0\.88\./, 'SDK 58 bundles React Native 0.88');
assert.match(pkg.dependencies.react, /^19\.3\./, 'SDK 58 requires React 19.3');
assert.ok(Number(pkg.engines.node.match(/\d+/)?.[0]) >= 22, 'Expo 58 needs Node 22.13+');
assert.ok(!config.expo.sdkVersion || String(config.expo.sdkVersion).startsWith('58.'), 'No stale app.json sdkVersion');
assert.match(workflow, /node-version: "22"/, 'CI must use Node 22');
assert.match(workflow, /npx expo install --check/, 'CI must validate Expo dependency versions');
assert.match(workflow, /npx expo export --platform ios/, 'CI must bundle the actual iOS app');
console.log('Expo Go SDK 58 compatibility manifest and CI checks passed');
