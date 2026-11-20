import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import Pango from 'gi://Pango';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const WATCHER = '/usr/bin/python3';
const WORKDIR = '/usr/share/ab-proofread';

export default class ProofreadExtension extends Extension {
    enable() {
        this._signals = new Gio.Cancellable();
        this._focusedWindow = global.display.focus_window;
        this._selection = false;
        this._ready = false;
        this._enabled = true;
        this._reviewGeneration = 0;
        this._makeButton();
        this._makeReviewCard();
        this._makeIndicator();
        this._focusId = global.display.connect('notify::focus-window', () => {
            this._focusedWindow = global.display.focus_window;
            this._reviewGeneration++;
            this._hideButton();
            this._hideReviewCard();
        });
        this._overviewShownId = Main.overview.connect('showing', () => {
            this._reviewGeneration++;
            this._hideButton();
            this._hideReviewCard();
        });
        this._lockId = Main.sessionMode.connect('updated', () => {
            if (Main.sessionMode.isLocked || Main.sessionMode.isGreeter) {
                this._reviewGeneration++;
                this._hideButton();
                this._hideReviewCard();
            }
        });
        this._spawnWatcher();
    }

    _makeButton() {
        this._button = new St.Button({
            style_class: 'ab-proofread-selection-button',
            child: new St.Icon({icon_name: 'tools-check-spelling-symbolic', icon_size: 14}),
            can_focus: false,
            reactive: true,
            track_hover: true,
            accessible_name: 'Проверить выделенный текст в ab',
        });
        this._button.connect('clicked', () => {
            if (!this._enabled || !this._ready || !this._selection ||
                !this._button.visible || global.display.focus_window !== this._focusedWindow)
                return;
            this._hideButton();
            this._reviewGeneration++;
            this._activeReview = this._reviewGeneration;
            this._anchor = global.get_pointer();
            this._showReviewCard('loading');
            this._send({check: true});
        });
        Main.layoutManager.addChrome(this._button);
        this._button.hide();
    }

    _makeReviewCard() {
        this._reviewCard = new St.BoxLayout({
            style_class: 'ab-proofread-review-card', vertical: true,
            reactive: true, can_focus: false, visible: false,
        });
        this._reviewBody = new St.BoxLayout({style_class: 'ab-proofread-review-body', vertical: true});
        this._reviewCard.add_child(this._reviewBody);
        Main.layoutManager.addChrome(this._reviewCard);
    }

    _onCapturedEvent(event) {
        const type = event.type();
        if (this._reviewCard?.visible &&
            (type === Clutter.EventType.BUTTON_PRESS || type === Clutter.EventType.TOUCH_BEGIN)) {
            const [x, y] = event.get_coords();
            const [left, top] = this._reviewCard.get_transformed_position();
            const [width, height] = this._reviewCard.get_transformed_size();
            if (x < left || y < top || x >= left + width || y >= top + height) {
                this._reviewGeneration++;
                this._hideReviewCard();
            }
        }
        return Clutter.EVENT_PROPAGATE;
    }

    _makeIndicator() {
        this._indicator = new PanelMenu.Button(0.0, 'ab', false);
        this._statusIcon = new St.Icon({icon_name: 'accessories-dictionary-symbolic', style_class: 'system-status-icon'});
        this._indicator.add_child(this._statusIcon);
        const item = new PopupMenu.PopupSwitchMenuItem('ab', true);
        this._statusItem = item;
        item.connect('toggled', (_item, state) => {
            this._enabled = state;
            if (!state) {
                this._reviewGeneration++;
                this._hideButton();
                this._hideReviewCard();
                this._stopWatcher();
            } else {
                this._signals = new Gio.Cancellable();
                this._spawnWatcher();
                if (this._selection && this._ready)
                    this._showButton();
            }
        });
        this._indicator.menu.addMenuItem(item);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    _spawnWatcher() {
        this._setStatus('ab: запуск…');
        const launcher = new Gio.SubprocessLauncher({
            flags: Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
        });
        launcher.set_cwd(WORKDIR);
        try {
            this._process = launcher.spawnv([WATCHER, '-B', '-m', 'ab_proofread.integration.watch']);
            this._stdin = this._process.get_stdin_pipe();
            this._stdout = new Gio.DataInputStream({base_stream: this._process.get_stdout_pipe()});
            this._readLine();
        } catch (error) {
            this._setStatus('ab: недоступно');
            console.error(`ab watcher failed to start: ${error.message}`);
        }
    }

    _setStatus(text) {
        this._statusItem.label.text = text;
        this._indicator.accessible_name = text;
        this._statusIcon.opacity = this._ready ? 255 : 128;
    }

    _readLine() {
        if (!this._process || !this._enabled)
            return;
        const generation = this._signals;
        this._stdout.read_line_async(GLib.PRIORITY_DEFAULT, this._signals, (stream, result) => {
            if (generation !== this._signals || generation.is_cancelled()) return;
            try {
                const [line] = stream.read_line_finish(result);
                if (!line) {
                    this._stopWatcher();
                    return;
                }
                const message = JSON.parse(new TextDecoder().decode(line));
                if (message.ready === true) {
                    this._ready = true;
                    this._setStatus('ab: включено');
                }
                if (typeof message.selection === 'boolean') {
                    if (!message.selection) {
                        this._reviewGeneration++;
                        this._hideReviewCard();
                    }
                    this._selection = message.selection;
                    if (this._selection && this._ready && this._enabled)
                        this._showButton();
                    else
                        this._hideButton();
                }
                this._handleReviewMessage(message);
                this._readLine();
            } catch (error) {
                if (!this._signals.is_cancelled()) {
                    console.error(`ab watcher stream error: ${error.message}`);
                    this._stopWatcher();
                }
            }
        });
    }

    _send(message) {
        try {
            this._stdin.write_all(new TextEncoder().encode(`${JSON.stringify(message)}\n`), null);
        } catch (_) {
            if (message.replace)
                this._handleReviewMessage({replacement: 'unknown', id: message.replace});
            else
                this._showReviewCard('error');
        }
    }

    _handleReviewMessage(message) {
        if (typeof message.replacement === 'string') {
            if (!this._pendingReplace || message.id !== this._pendingReplace)
                return;
            this._pendingReplace = null;
            if (this._enabled && !Main.sessionMode.isLocked) {
                if (message.replacement === 'unknown')
                    Main.notify('ab', 'Редактор не подтвердил результат замены. Проверьте текст перед повторной попыткой.');
                else if (message.replacement === 'refused')
                    Main.notify('ab', 'Замена не выполнена. Выделите текст и запустите проверку заново.');
            }
            return;
        }
        if (this._activeReview !== this._reviewGeneration ||
            global.display.focus_window !== this._focusedWindow || !this._enabled)
            return;
        if (message.review === 'loading') {
            this._showReviewCard('loading');
        } else if (message.review === 'result' && Array.isArray(message.parts)) {
            this._showReviewCard('result', message);
        } else if (message.review === 'error') {
            this._showReviewCard('error');
        } else if (message.review === 'unsupported') {
            this._showReviewCard('unsupported');
        } else if (message.review === 'stale') {
            this._hideReviewCard();
        }
    }

    _renderParts(parts, width) {
        const label = new St.Label({style_class: 'ab-proofread-review-text'});
        label.set_width(Math.max(1, width - 38));
        label.clutter_text.line_wrap = true;
        label.clutter_text.line_wrap_mode = Pango.WrapMode.WORD_CHAR;
        label.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
        const markup = (Array.isArray(parts) ? parts : []).map(part => {
            const text = GLib.markup_escape_text(part.text, -1);
            return part.changed ? `<span background="#255d51" foreground="#ffffff">${text}</span>` : text;
        }).join('');
        label.clutter_text.set_markup(markup);
        const scroll = new St.ScrollView({style_class: 'ab-proofread-review-scroll'});
        scroll.set_policy(St.PolicyType.NEVER, St.PolicyType.AUTOMATIC);
        const viewport = new St.Viewport();
        viewport.add_child(label);
        scroll.set_child(viewport);
        this._reviewBody.add_child(scroll);
    }

    _showReviewCard(state, message = {}) {
        if (!this._reviewCard || Main.sessionMode.isLocked || Main.sessionMode.isGreeter || Main.overview.visible)
            return;
        const [x, y] = this._anchor ?? global.get_pointer();
        const monitor = Main.layoutManager.monitors.find(m => x >= m.x && x < m.x + m.width && y >= m.y && y < m.y + m.height) ?? Main.layoutManager.primaryMonitor;
        if (!monitor) return;
        const width = Math.min(320, monitor.width - 24);
        this._cancelPraiseTimeout();
        this._reviewBody.destroy_all_children();
        if (state === 'loading') {
            this._reviewBody.add_child(new St.Label({text: 'Проверяю…', style_class: 'ab-proofread-review-status'}));
        } else if (state === 'error') {
            this._reviewBody.add_child(new St.Label({text: 'Не удалось проверить выделение.', style_class: 'ab-proofread-review-status'}));
        } else if (state === 'unsupported') {
            this._reviewBody.add_child(new St.Label({text: 'ab проверяет только русский текст.', style_class: 'ab-proofread-review-status'}));
        } else {
            if (message.changes > 0) {
                this._renderParts(message.parts, width);
                if (typeof message.replace === 'string' && /^[0-9a-f]{32}$/.test(message.replace)) {
                    const generation = this._activeReview;
                    const button = new St.Button({label: 'Заменить', style_class: 'button', can_focus: false});
                    button.connect('clicked', () => {
                        if (generation !== this._activeReview || generation !== this._reviewGeneration ||
                            global.display.focus_window !== this._focusedWindow || !this._enabled ||
                            !this._reviewCard?.visible || Main.sessionMode.isLocked || Main.overview.visible)
                            return;
                        this._reviewGeneration++;
                        this._pendingReplace = message.replace;
                        this._hideReviewCard();
                        this._send({replace: message.replace});
                    });
                    this._reviewBody.add_child(button);
                } else {
                    this._reviewBody.add_child(new St.Label({text: 'Замена в этом приложении недоступна', style_class: 'ab-proofread-review-note'}));
                }
            }
            else {
                const clean = message.changes === 0 && message.findings === false;
                const text = clean ? 'Отлично! Ошибок не найдено.' : 'Нет однозначного исправления.';
                this._reviewBody.add_child(new St.Label({text, style_class: 'ab-proofread-review-status'}));
                if (clean)
                    this._praiseTimeout = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 2200, () => {
                        this._praiseTimeout = 0;
                        this._hideReviewCard();
                        return GLib.SOURCE_REMOVE;
                    });
            }
        }
        this._reviewCard.set_width(width);
        const [, height] = this._reviewCard.get_preferred_height(width);
        this._reviewCard.set_position(
            Math.max(monitor.x + 12, Math.min(x + 14, monitor.x + monitor.width - width - 12)),
            Math.max(monitor.y + 12, Math.min(y + 18, monitor.y + monitor.height - height - 12)));
        this._reviewCard.show();
        if (!this._outsideId)
            this._outsideId = global.stage.connect('captured-event', (_stage, event) => this._onCapturedEvent(event));
    }

    _cancelPraiseTimeout() {
        if (this._praiseTimeout) {
            GLib.Source.remove(this._praiseTimeout);
            this._praiseTimeout = 0;
        }
    }

    _hideReviewCard() {
        this._cancelPraiseTimeout();
        this._reviewCard?.hide();
        this._reviewBody?.destroy_all_children();
        this._activeReview = null;
        if (this._outsideId) {
            global.stage.disconnect(this._outsideId);
            this._outsideId = 0;
        }
    }

    _showButton() {
        if (!this._enabled || !this._ready || !this._selection || !global.display.focus_window || Main.sessionMode.isLocked || Main.sessionMode.isGreeter || Main.overview.visible)
            return;
        if (global.get_pointer()[2] & Clutter.ModifierType.BUTTON1_MASK) {
            if (!this._releaseSource) {
                this._button.hide();
                let ticks = 0;
                this._releaseSource = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 35, () => {
                    if (global.get_pointer()[2] & Clutter.ModifierType.BUTTON1_MASK) {
                        if (++ticks < 300) return GLib.SOURCE_CONTINUE;
                        this._releaseSource = 0;
                        return GLib.SOURCE_REMOVE;
                    }
                    this._releaseSource = 0;
                    this._showButton();
                    return GLib.SOURCE_REMOVE;
                });
            }
            return;
        }
        const [x, y] = global.get_pointer();
        const monitor = Main.layoutManager.monitors.find(m => x >= m.x && x < m.x + m.width && y >= m.y && y < m.y + m.height) ?? Main.layoutManager.primaryMonitor;
        if (!monitor) return;
        const [, width] = this._button.get_preferred_width(-1);
        const [, height] = this._button.get_preferred_height(width);
        this._button.set_position(
            Math.max(monitor.x, Math.min(x + 14, monitor.x + monitor.width - width)),
            Math.max(monitor.y, Math.min(y + 18, monitor.y + monitor.height - height)));
        this._button.show();
    }

    _hideButton() {
        if (this._releaseSource) {
            GLib.Source.remove(this._releaseSource);
            this._releaseSource = 0;
        }
        this._button?.hide();
    }

    _stopWatcher() {
        this._hideButton();
        this._hideReviewCard();
        this._pendingReplace = null;
        this._signals?.cancel();
        if (this._process) {
            try { this._stdin?.close(null); } catch (_) {}
            // Closing stdin lets the watcher stop its own Java child.
        }
        this._process = null;
        this._stdin = null;
        this._stdout = null;
        this._ready = false;
        this._selection = false;
        this._setStatus(this._enabled ? 'ab: недоступно' : 'ab: выключено');
    }

    disable() {
        this._enabled = false;
        this._reviewGeneration++;
        this._hideButton();
        this._hideReviewCard();
        this._stopWatcher();
        if (this._focusId)
            global.display.disconnect(this._focusId);
        if (this._overviewShownId)
            Main.overview.disconnect(this._overviewShownId);
        if (this._lockId)
            Main.sessionMode.disconnect(this._lockId);
        this._indicator?.destroy();
        this._reviewCard?.destroy();
        this._button?.destroy();
        this._indicator = null;
        this._reviewCard = null;
        this._button = null;
    }
}
