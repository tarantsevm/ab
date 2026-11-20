import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../extensions/ab_proofread@ab.local/extension.js', import.meta.url), 'utf8');

test('drag selection waits for mouse release before exposing the button', () => {
  const callbacks = new Map(); let next = 0;
  let pointer = [100, 100, 256];
  const win = {};
  const context = {
    Extension: class {}, global: {display: {focus_window: win}, get_pointer: () => pointer},
    GLib: {timeout_add: (_priority, _delay, fn) => { callbacks.set(++next, fn); return next; },
      Source: {remove: id => callbacks.delete(id)}, SOURCE_CONTINUE: true, SOURCE_REMOVE: false},
    Clutter: {ModifierType: {BUTTON1_MASK: 256}},
    Main: {layoutManager: {monitors: [{x:0,y:0,width:1000,height:600}]}, sessionMode: {}, overview: {}},
  };
  const Ext = vm.runInNewContext(source.replace(/^import .*;$/gm, '').replace('export default class', '(class') + ')', context);
  const e = new Ext(); let position; let shown = false;
  Object.assign(e, {_enabled:true, _ready:true, _selection:true, _focusedWindow:win, _button:{
    get_preferred_width:()=>[26,26], get_preferred_height:()=>[26,26], show:()=>{shown=true;}, hide:()=>{shown=false;}, set_position:(...p)=>{position=p;},
  }});
  e._showButton();
  assert.equal(shown, false);
  const step = [...callbacks.values()][0];
  assert.equal(step(), true);
  pointer = [300, 150, 0];
  assert.equal(step(), false);
  assert.equal(shown, true);
  assert.deepEqual(position, [314, 168]);
});

test('pure Shell extension implements the watcher JSONL contract', () => {
  assert.match(source, /ab_proofread\.integration\.watch/);
  assert.match(source, /JSON\.parse/);
  assert.match(source, /JSON\.stringify\(message\)/);
  assert.match(source, /message\.ready === true/);
  assert.match(source, /typeof message\.selection === 'boolean'/);
  assert.match(source, /this\._send\(\{check: true\}\)/);
});

test('selection affordance is pointer anchored and click hides before request', () => {
  assert.match(source, /global\.get_pointer\(\)/);
  assert.match(source, /child: new St.Icon\(/);
  assert.match(source, /accessible_name: 'Проверить выделенный текст в ab'/);
  assert.doesNotMatch(source, /label: 'Проверить'/);
  assert.match(source, /this\._hideButton\(\);[\s\S]*?this\._showReviewCard\('loading'\);\s*this\._send\(\{check: true\}\)/);
});

test('review response stays in compact Shell card with safe inline change markup', () => {
  assert.match(source, /message\.review === 'loading'/);
  assert.match(source, /message\.review === 'result'/);
  assert.match(source, /message\.review === 'error'/);
  assert.match(source, /message\.review === 'stale'/);
  assert.match(source, /changed/);
  assert.match(source, /_makeReviewCard/);
  assert.doesNotMatch(source, /Копировать|_dismissButton|set_text\(St\.ClipboardType/);
  assert.match(source, /Замена в этом приложении недоступна/);
  assert.doesNotMatch(source, /Gtk/);
});

test('review popup is invalidated on focus changes and dismissals', () => {
  assert.match(source, /_reviewGeneration/);
  assert.match(source, /_hideReviewCard/);
  assert.match(source, /notify::focus-window/);
});

test('press outside dismisses the preview but passes through to its destination', () => {
  const Clutter = {EventType: {BUTTON_PRESS: 1, TOUCH_BEGIN: 2}, EVENT_PROPAGATE: false};
  const context = {Extension: class {}, Clutter};
  const Ext = vm.runInNewContext(source.replace(/^import .*;$/gm, '').replace('export default class', '(class') + ')', context);
  const e = new Ext();
  e._reviewGeneration = 1;
  e._reviewCard = {visible: true, get_transformed_position: () => [100, 100], get_transformed_size: () => [120, 50], hide() { this.visible = false; }};
  const event = (x, y) => ({type: () => Clutter.EventType.BUTTON_PRESS, get_coords: () => [x, y]});
  assert.equal(e._onCapturedEvent(event(110, 110)), false);
  assert.equal(e._reviewCard.visible, true);
  assert.equal(e._onCapturedEvent(event(110, 160)), false);
  assert.equal(e._reviewCard.visible, false);
  assert.equal(e._reviewGeneration, 2);
});

test('only an offered correction gets a one-shot Replace button', () => {
  const children = [];
  const sent = [];
  const win = {};
  let dismissPraise;
  class Button { constructor(props) { Object.assign(this, props); } connect(_, fn) { this.click = fn; } }
  const context = {
    Extension: class {}, St: {Button, Label: Button}, global: {display: {focus_window: win}, stage: {disconnect() {}}},
    GLib: {timeout_add: (_priority, ms, fn) => { assert.equal(ms, 2200); dismissPraise = fn; return 1; }, SOURCE_REMOVE: false},
    Main: {layoutManager: {monitors: [{x:0,y:0,width:1000,height:600}]}, sessionMode: {}, overview: {}},
  };
  const Ext = vm.runInNewContext(source.replace(/^import .*;$/gm, '').replace('export default class', '(class') + ')', context);
  const e = new Ext();
  Object.assign(e, {_enabled: true, _reviewGeneration: 1, _activeReview: 1, _focusedWindow: win, _anchor: [100,100],
    _outsideId: 1, _renderParts() {}, _send: value => sent.push(JSON.stringify(value)),
    _reviewBody: {destroy_all_children() {children.length = 0;}, add_child: child => children.push(child)},
    _reviewCard: {set_width() {}, get_preferred_height: () => [0,50], set_position() {}, show() {this.visible = true;}, hide() {this.visible = false;}},
  });
  const preview = {review: 'result', changes: 1, parts: [{text:'spelling', changed:true}]};
  e._handleReviewMessage({review: 'result', changes: 0, findings: true, parts: []});
  assert.equal(children[0].text, 'Нет однозначного исправления.');
  e._handleReviewMessage({review: 'unsupported'});
  assert.equal(children[0].text, 'ab проверяет только русский текст.');
  e._handleReviewMessage({review: 'result', changes: 0, findings: false, parts: []});
  assert.equal(children[0].text, 'Отлично! Ошибок не найдено.');
  assert.equal(dismissPraise(), false);
  assert.equal(e._reviewCard.visible, false);
  e._activeReview = e._reviewGeneration;
  e._outsideId = 1;
  e._handleReviewMessage(preview);
  assert.equal(children.some(c => c.label === 'Заменить'), false);
  const id = '1'.repeat(32);
  e._handleReviewMessage({...preview, replace:id});
  const button = children.find(c => c.label === 'Заменить');
  assert.ok(button);
  button.click();
  button.click();
  assert.equal(e._reviewCard.visible, false);
  assert.deepEqual(sent, [JSON.stringify({replace:id})]);
});

test('suspend and disable stop watcher and release signals', () => {
  assert.match(source, /if \(!state\) \{\s*this\._reviewGeneration\+\+;\s*this\._hideButton\(\);\s*this\._hideReviewCard\(\);\s*this\._stopWatcher\(\);/);
  assert.match(source, /this\._signals\?\.cancel\(\)/);
  assert.match(source, /global\.display\.disconnect\(this\._focusId\)/);
});

test('lost reply warns once even after selection invalidation', () => {
  const notifications = [];
  const context = {Extension: class {}, Main: {sessionMode: {}, notify: (...args) => notifications.push(args)}};
  const Ext = vm.runInNewContext(source.replace(/^import .*;$/gm, '').replace('export default class', '(class') + ')', context);
  const e = new Ext();
  const id = '1'.repeat(32);
  Object.assign(e, {_enabled: true, _activeReview: 1, _reviewGeneration: 2, _pendingReplace: id});
  e._handleReviewMessage({replacement: 'unknown', id: '2'.repeat(32)});
  e._handleReviewMessage({replacement: 'unknown', id});
  e._handleReviewMessage({replacement: 'unknown', id});
  assert.equal(notifications.length, 1);
  assert.match(notifications[0][1], /Проверьте текст/);
});
