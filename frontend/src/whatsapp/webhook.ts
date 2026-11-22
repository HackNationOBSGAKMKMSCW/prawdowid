// WhatsApp Cloud API shapes exchanged with the backend adapter.
// The simulator plays the part of WhatsApp: it POSTs webhook payloads and
// renders the message bodies the bot would send through the Graph API.

export const SIM_USER = { waId: '48500100200', name: 'Ty' } as const;

export type IncomingPart =
  | { type: 'text'; body: string; forwarded?: boolean }
  | { type: 'button_reply'; id: string; title: string }
  | { type: 'request_welcome' };

export interface ReplyButton {
  id: string;
  title: string;
}

export type BotMessage =
  | { type: 'text'; text: string }
  | { type: 'buttons'; text: string; buttons: ReplyButton[] }
  | { type: 'card'; header: string; text: string; footer: string; link: LinkButton };

export interface LinkButton {
  label: string;
  url: string;
}

interface CloudApiTextMessage {
  type: 'text';
  text: { body: string };
}

interface CloudApiInteractiveMessage {
  type: 'interactive';
  interactive: {
    type: string;
    header?: { type?: string; text?: string };
    body?: { text?: string };
    footer?: { text?: string };
    action?: {
      buttons?: { reply?: { id?: string; title?: string } }[];
      name?: string;
      parameters?: { display_text?: string; url?: string };
    };
  };
}

export type CloudApiMessage = CloudApiTextMessage | CloudApiInteractiveMessage | { type: string };

export interface WebhookResponse {
  messages: CloudApiMessage[];
}

export interface Health {
  status: string;
  mode: 'live' | 'demo' | string;
}

export function newMessageId(): string {
  const random = Math.random().toString(36).slice(2, 10).toUpperCase();
  return `wamid.SIM${Date.now().toString(36).toUpperCase()}${random}`;
}

export function buildWebhook(part: IncomingPart, id: string, sentAt: number) {
  const base = { from: SIM_USER.waId, id, timestamp: String(Math.floor(sentAt / 1000)) };
  const message =
    part.type === 'text'
      ? {
          ...base,
          type: 'text',
          text: { body: part.body },
          ...(part.forwarded ? { context: { forwarded: true } } : {}),
        }
      : part.type === 'button_reply'
        ? {
            ...base,
            type: 'interactive',
            interactive: { type: 'button_reply', button_reply: { id: part.id, title: part.title } },
          }
        : { ...base, type: 'request_welcome' };

  return {
    object: 'whatsapp_business_account',
    entry: [
      {
        id: 'SIMULATOR_WABA',
        changes: [
          {
            field: 'messages',
            value: {
              messaging_product: 'whatsapp',
              metadata: { display_phone_number: 'SprawdzTo', phone_number_id: 'SIMULATOR' },
              contacts: [{ profile: { name: SIM_USER.name }, wa_id: SIM_USER.waId }],
              messages: [message],
            },
          },
        ],
      },
    ],
  };
}

type StreamEvent =
  | { type: 'status'; to: string; text: string }
  | { type: 'messages'; messages: CloudApiMessage[] }
  | { type: 'error'; detail: string };

// Same API base as the website (`VITE_API_BASE_URL`, by default `/api`): in production
// the simulator talks to the backend directly, not through the host's proxy, whose
// time limit is shorter than a full check.
const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');

// Streaming variant: status lines arrive while the bot checks the message,
// followed by the final Cloud API messages (NDJSON, one event per line).
export async function postWebhookStream(
  payload: unknown,
  onStatus: (text: string) => void,
): Promise<WebhookResponse> {
  const res = await fetch(`${API_BASE}/whatsapp/webhook?stream=true`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok || !res.body) throw new Error(`${res.status} ${res.statusText}`);

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (value) buffer += value;
    const lines = buffer.split('\n');
    buffer = done ? '' : (lines.pop() ?? '');
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as StreamEvent;
      if (event.type === 'status') onStatus(event.text);
      else if (event.type === 'messages') return { messages: event.messages };
      else throw new Error(event.detail);
    }
    if (done) throw new Error('stream ended without messages');
  }
}

export async function fetchHealth(): Promise<Health> {
  const res = await fetch(`${API_BASE}/whatsapp/health`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as Health;
}

export function toBotMessages(messages: CloudApiMessage[]): BotMessage[] {
  const result: BotMessage[] = [];
  for (const message of messages) {
    if (message.type === 'text' && 'text' in message) {
      result.push({ type: 'text', text: message.text.body });
    } else if (message.type === 'interactive' && 'interactive' in message) {
      const { interactive } = message;
      const url = interactive.action?.parameters?.url ?? '';
      if (interactive.type === 'cta_url' && /^https?:\/\//.test(url)) {
        // "Call to action URL" message: rendered as a verdict card with a link button.
        result.push({
          type: 'card',
          header: interactive.header?.text ?? '',
          text: interactive.body?.text ?? '',
          footer: interactive.footer?.text ?? '',
          link: { label: interactive.action?.parameters?.display_text ?? 'Otwórz', url },
        });
        continue;
      }
      const buttons = (message.interactive.action?.buttons ?? [])
        .map((button) => button.reply)
        .filter((reply): reply is ReplyButton => Boolean(reply?.id && reply.title));
      result.push({ type: 'buttons', text: message.interactive.body?.text ?? '', buttons });
    }
  }
  return result;
}
