import {
  Fragment,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react';
import {
  AttachIcon,
  BackIcon,
  CameraIcon,
  ChainIcon,
  CloseIcon,
  ClockIcon,
  DoubleTickIcon,
  EmojiIcon,
  ExternalLinkIcon,
  FailedIcon,
  ForwardIcon,
  LockIcon,
  MenuIcon,
  MicIcon,
  PhoneIcon,
  ReplyIcon,
  SendIcon,
  SprawdzToAvatar,
  TickIcon,
  VideoIcon,
} from './icons.tsx';
import {
  buildWebhook,
  fetchHealth,
  newMessageId,
  postWebhookStream,
  toBotMessages,
  type Health,
  type IncomingPart,
  type LinkButton,
  type ReplyButton,
} from './webhook.ts';
import WhatsAppText from './WhatsAppText.tsx';
import './whatsapp.css';

type Status = 'pending' | 'sent' | 'delivered' | 'read' | 'failed';

type ChatItem =
  | {
      kind: 'user';
      id: string;
      text: string;
      time: number;
      status: Status;
      forwarded?: boolean;
    }
  | {
      kind: 'bot';
      id: string;
      text: string;
      time: number;
      buttons?: ReplyButton[];
      card?: { header: string; footer: string; link: LinkButton };
    }
  | { kind: 'notice'; id: string; text: string; time: number };

// A pending check: hidden until the bot "reads" the message, then shown as
// typing dots or as the list of progress steps streamed by the adapter.
interface Activity {
  id: string;
  visible: boolean;
  steps: string[];
}

const STORAGE_KEY = 'sprawdzto-whatsapp-chat-v1';
const START_COMMAND = 'cd whatsapp_sim/backend && ../../.venv/bin/python -m whatsappAdapter --demo';

// A typical chain message, used by the attach menu to demo forwarded content.
const SAMPLE_CHAIN =
  'UWAGA!!! Od poniedziałku maszty 5G w całej Polsce będą roznosić koronawirusa. ' +
  'Lekarze to ukrywają! Przekaż dalej wszystkim znajomym, zanim to usuną!!!';

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

function loadItems(): ChatItem[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '[]');
    if (!Array.isArray(parsed)) return [];
    return (parsed as ChatItem[]).map((item) =>
      item.kind === 'user' && item.status === 'pending' ? { ...item, status: 'failed' } : item,
    );
  } catch {
    return [];
  }
}

function saveItems(items: ChatItem[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(-200)));
  } catch {
    // Storage can be unavailable (private mode); the chat still works in memory.
  }
}

const formatTime = (time: number) =>
  new Date(time).toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' });

function dayLabel(time: number): string {
  const date = new Date(time);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return 'Dzisiaj';
  if (date.toDateString() === yesterday.toDateString()) return 'Wczoraj';
  return date.toLocaleDateString('pl-PL', { day: 'numeric', month: 'long', year: 'numeric' });
}

// Card colour follows the verdict wording the adapter puts in the header.
function cardTone(header: string): string {
  const text = header.toLocaleLowerCase('pl-PL');
  if (text.includes('fałsz')) return 'false';
  if (text.includes('wprowadza w błąd')) return 'misleading';
  if (text.includes('prawda')) return 'true';
  if (text.includes('rozbieżne')) return 'conflicting';
  return 'neutral';
}

function StatusIcon({ status }: { status: Status }) {
  switch (status) {
    case 'pending':
      return <ClockIcon className="wa-tick" aria-label="Wysyłanie" />;
    case 'sent':
      return <TickIcon className="wa-tick" aria-label="Wysłano" />;
    case 'delivered':
      return <DoubleTickIcon className="wa-tick" aria-label="Dostarczono" />;
    case 'read':
      return <DoubleTickIcon className="wa-tick wa-tick--read" aria-label="Odczytano" />;
    case 'failed':
      return <FailedIcon className="wa-tick wa-tick--failed" aria-label="Nie wysłano" />;
  }
}

function StatusBar() {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 15_000);
    return () => clearInterval(timer);
  }, []);
  return (
    <div className="wa-statusbar" aria-hidden="true">
      <span>{formatTime(now)}</span>
      <span className="wa-statusbar-icons">
        <svg viewBox="0 0 18 12" width="18" height="12">
          <rect x="0" y="8" width="3" height="4" rx="1" fill="currentColor" />
          <rect x="5" y="5.5" width="3" height="6.5" rx="1" fill="currentColor" />
          <rect x="10" y="3" width="3" height="9" rx="1" fill="currentColor" />
          <rect x="15" y="0" width="3" height="12" rx="1" fill="currentColor" />
        </svg>
        <svg viewBox="0 0 26 12" width="26" height="12">
          <rect x="0.5" y="0.5" width="22" height="11" rx="3" fill="none" stroke="currentColor" />
          <rect x="2" y="2" width="16" height="8" rx="1.5" fill="currentColor" />
          <rect x="23.5" y="4" width="2" height="4" rx="1" fill="currentColor" />
        </svg>
      </span>
    </div>
  );
}

export default function WhatsAppSimulator() {
  const [items, setItems] = useState<ChatItem[]>(loadItems);
  const [draft, setDraft] = useState('');
  const [forwardDraft, setForwardDraft] = useState(false);
  const [attachOpen, setAttachOpen] = useState(false);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [health, setHealth] = useState<Health | 'offline' | null>(null);
  const initialItemCount = useRef(items.length);
  const welcomed = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => saveItems(items), [items]);

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [items, activity]);

  useLayoutEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [draft]);

  const checkHealth = useCallback(() => {
    fetchHealth().then(setHealth, () => setHealth('offline'));
  }, []);

  useEffect(checkHealth, [checkHealth]);

  const append = useCallback((item: ChatItem) => setItems((prev) => [...prev, item]), []);

  const setStatus = useCallback((id: string, status: Status) => {
    setItems((prev) =>
      prev.map((item) => (item.kind === 'user' && item.id === id ? { ...item, status } : item)),
    );
  }, []);

  // Plays WhatsApp's part: send the webhook, animate ticks and typing, show replies.
  const deliver = useCallback(
    async (part: IncomingPart, display: string | null) => {
      const id = newMessageId();
      const sentAt = Date.now();
      const payload = buildWebhook(part, id, sentAt);
      const fromUser = display !== null;
      if (fromUser) {
        append({
          kind: 'user',
          id,
          text: display,
          time: sentAt,
          status: 'pending',
          forwarded: part.type === 'text' && part.forwarded,
        });
      }

      const updateActivity = (change: (current: Activity) => Activity) =>
        setActivity((prev) => prev.map((entry) => (entry.id === id ? change(entry) : entry)));
      setActivity((prev) => [...prev, { id, visible: false, steps: [] }]);

      const outcome = postWebhookStream(payload, (text) =>
        updateActivity((current) => ({ ...current, steps: [...current.steps, text] })),
      ).then(
        (response) => ({ response }) as const,
        (error: unknown) => ({ error }) as const,
      );
      try {
        if (fromUser) {
          await sleep(150);
          setStatus(id, 'sent');
        }
        const early = await Promise.race([outcome, sleep(450).then(() => null)]);
        if (early && 'error' in early) throw early.error;
        if (fromUser) setStatus(id, 'delivered');
        await sleep(fromUser ? 500 : 200);
        if (fromUser) setStatus(id, 'read');
        updateActivity((current) => ({ ...current, visible: true }));

        const [result] = await Promise.all([outcome, sleep(700)]);
        if ('error' in result) throw result.error;
        setHealth((current) => (current === 'offline' ? null : current));

        const messages = toBotMessages(result.response.messages);
        for (const [index, message] of messages.entries()) {
          if (index > 0) await sleep(650);
          if (index === 0) setActivity((prev) => prev.filter((entry) => entry.id !== id));
          append({
            kind: 'bot',
            id: newMessageId(),
            text: message.text,
            time: Date.now(),
            buttons: message.type === 'buttons' ? message.buttons : undefined,
            card:
              message.type === 'card'
                ? { header: message.header, footer: message.footer, link: message.link }
                : undefined,
          });
        }
      } catch (error) {
        if (fromUser) setStatus(id, 'failed');
        const detail = error instanceof Error ? error.message : String(error);
        setHealth('offline');
        append({
          kind: 'notice',
          id: newMessageId(),
          time: Date.now(),
          text: `Brak odpowiedzi od adaptera SprawdzTo (${detail}). Uruchom backend: ${START_COMMAND}`,
        });
      } finally {
        setActivity((prev) => prev.filter((entry) => entry.id !== id));
      }
    },
    [append, setStatus],
  );

  useEffect(() => {
    if (welcomed.current) return;
    welcomed.current = true;
    if (initialItemCount.current === 0) void deliver({ type: 'request_welcome' }, null);
  }, [deliver]);

  const sendDraft = () => {
    const body = draft.trim();
    if (body) void deliver({ type: 'text', body, forwarded: forwardDraft }, body);
    setForwardDraft(false);
    setAttachOpen(false);
    setDraft('');
    inputRef.current?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape') setAttachOpen(false);
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      sendDraft();
    }
  };

  const online = health !== null && health !== 'offline';
  const visibleActivity = activity.filter((entry) => entry.visible);
  const typing = visibleActivity.length;
  const checking = visibleActivity.some((entry) => entry.steps.length > 0);
  const headerStatus = checking
    ? 'sprawdza…'
    : typing > 0
      ? 'pisze…'
      : online
        ? 'online'
        : 'konto firmowe';

  return (
    <div className="wa-app">
      <div className="wa-page">
        <section className="wa-phone" aria-label="Symulator WhatsApp: czat ze SprawdzTo">
          <StatusBar />
          <header className="wa-header">
            <span className="wa-icon-button" title="Niedostępne w symulatorze">
              <BackIcon />
            </span>
            <SprawdzToAvatar size={40} />
            <div className="wa-contact">
              <span className="wa-contact-name">SprawdzTo</span>
              <span className={`wa-contact-status${typing > 0 ? ' is-typing' : ''}`}>
                {headerStatus}
              </span>
            </div>
            <span className="wa-icon-button" title="Niedostępne w symulatorze">
              <VideoIcon />
            </span>
            <span className="wa-icon-button" title="Niedostępne w symulatorze">
              <PhoneIcon />
            </span>
            <span className="wa-icon-button" title="Niedostępne w symulatorze">
              <MenuIcon />
            </span>
          </header>

          <div className="wa-chat" ref={scrollRef} role="log" aria-live="polite">
            <div className="wa-chip wa-chip--notice">
              <LockIcon width={12} height={12} />
              To symulator WhatsApp. Wiadomości trafiają do lokalnego adaptera SprawdzTo, nie do
              serwerów WhatsApp.
            </div>

            {items.map((item, index) => {
              const previous = items[index - 1];
              const newDay =
                !previous ||
                new Date(previous.time).toDateString() !== new Date(item.time).toDateString();
              const first = newDay || !previous || previous.kind !== item.kind;
              return (
                <Fragment key={item.id}>
                  {newDay && <div className="wa-chip wa-chip--date">{dayLabel(item.time)}</div>}
                  {item.kind === 'notice' ? (
                    <div className="wa-chip wa-chip--error" role="status">
                      {item.text}
                    </div>
                  ) : (
                    <div
                      className={`wa-row wa-row--${item.kind === 'user' ? 'out' : 'in'}${
                        first ? ' wa-row--first' : ''
                      }`}
                    >
                      <div
                        className={`wa-bubble${item.kind === 'bot' && item.card ? ' wa-card' : ''}`}
                        data-tone={
                          item.kind === 'bot' && item.card ? cardTone(item.card.header) : undefined
                        }
                      >
                        {item.kind === 'bot' && item.card?.header && (
                          <div className="wa-card-header">{item.card.header}</div>
                        )}
                        <div className="wa-bubble-body">
                          {item.kind === 'user' && item.forwarded && (
                            <span className="wa-forwarded">
                              <ForwardIcon width={14} height={14} />
                              Przekazano dalej
                            </span>
                          )}
                          <WhatsAppText text={item.text} />
                          {item.kind === 'bot' && item.card?.footer && (
                            <span className="wa-card-footer">{item.card.footer}</span>
                          )}
                          <span className="wa-meta-spacer" aria-hidden="true" />
                          <span className="wa-meta">
                            {formatTime(item.time)}
                            {item.kind === 'user' && <StatusIcon status={item.status} />}
                          </span>
                        </div>
                        {item.kind === 'bot' && item.card && (
                          <div className="wa-buttons">
                            <a
                              className="wa-reply-button"
                              href={item.card.link.url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              <ExternalLinkIcon width={16} height={16} />
                              {item.card.link.label}
                            </a>
                          </div>
                        )}
                        {item.kind === 'bot' && item.buttons && item.buttons.length > 0 && (
                          <div className="wa-buttons">
                            {item.buttons.map((button) => (
                              <button
                                key={button.id}
                                type="button"
                                className="wa-reply-button"
                                onClick={() =>
                                  void deliver(
                                    { type: 'button_reply', id: button.id, title: button.title },
                                    button.title,
                                  )
                                }
                              >
                                <ReplyIcon width={16} height={16} />
                                {button.title}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </Fragment>
              );
            })}

            {visibleActivity.map((entry) => (
              <div key={entry.id} className="wa-row wa-row--in wa-row--first">
                {entry.steps.length === 0 ? (
                  <div className="wa-bubble wa-typing" aria-label="SprawdzTo pisze">
                    <span />
                    <span />
                    <span />
                  </div>
                ) : (
                  <div className="wa-bubble wa-progress" role="status">
                    {entry.steps.map((step, index) => {
                      const done = index < entry.steps.length - 1;
                      return (
                        <div key={index} className={`wa-progress-step${done ? ' is-done' : ''}`}>
                          <span>{step}</span>
                          {done ? (
                            <TickIcon className="wa-progress-mark" aria-label="gotowe" />
                          ) : (
                            <span className="wa-spinner" aria-label="w toku" />
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="wa-composer">
            {attachOpen && (
              <div className="wa-attach-menu" role="menu">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setDraft(SAMPLE_CHAIN);
                    setForwardDraft(true);
                    setAttachOpen(false);
                    inputRef.current?.focus();
                  }}
                >
                  <span className="wa-attach-icon wa-attach-icon--chain">
                    <ChainIcon width={20} height={20} />
                  </span>
                  Przykładowy łańcuszek
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setForwardDraft((value) => !value);
                    setAttachOpen(false);
                    inputRef.current?.focus();
                  }}
                >
                  <span className="wa-attach-icon wa-attach-icon--forward">
                    <ForwardIcon width={20} height={20} />
                  </span>
                  {forwardDraft ? 'Wyślij jako zwykłą wiadomość' : 'Wyślij jako przekazaną dalej'}
                </button>
              </div>
            )}
            {forwardDraft && (
              <div className="wa-forward-banner">
                <ForwardIcon width={16} height={16} />
                <span>Wiadomość zostanie wysłana jako przekazana dalej</span>
                <button
                  type="button"
                  aria-label="Wyślij jako zwykłą wiadomość"
                  onClick={() => setForwardDraft(false)}
                >
                  <CloseIcon width={18} height={18} />
                </button>
              </div>
            )}
            <div className="wa-input">
              <span className="wa-input-icon" title="Niedostępne w symulatorze">
                <EmojiIcon />
              </span>
              <textarea
                ref={inputRef}
                rows={1}
                value={draft}
                maxLength={16_000}
                placeholder="Wiadomość"
                aria-label="Wiadomość do SprawdzTo"
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={onKeyDown}
              />
              <button
                type="button"
                className="wa-input-icon wa-input-button"
                aria-label="Załącz"
                aria-expanded={attachOpen}
                onClick={() => setAttachOpen((open) => !open)}
              >
                <AttachIcon />
              </button>
              {!draft.trim() && (
                <span className="wa-input-icon" title="Niedostępne w symulatorze">
                  <CameraIcon />
                </span>
              )}
            </div>
            <button
              type="button"
              className="wa-send"
              onClick={sendDraft}
              disabled={!draft.trim()}
              aria-label={draft.trim() ? 'Wyślij' : 'Wiadomość głosowa (niedostępna)'}
            >
              {draft.trim() ? <SendIcon /> : <MicIcon />}
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
