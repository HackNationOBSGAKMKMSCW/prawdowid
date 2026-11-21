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
  | { type: 'buttons'; text: string; buttons: ReplyButton[] };

interface CloudApiTextMessage {
  type: 'text';
  text: { body: string };
}

interface CloudApiInteractiveMessage {
  type: 'interactive';
  interactive: {
    type: string;
    body?: { text?: string };
    action?: { buttons?: { reply?: { id?: string; title?: string } }[] };
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

export async function postWebhook(
  payload: unknown,
  signal?: AbortSignal,
): Promise<WebhookResponse> {
  const res = await fetch('/api/whatsapp/webhook', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as WebhookResponse;
}

export async function fetchHealth(): Promise<Health> {
  const res = await fetch('/api/whatsapp/health');
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as Health;
}

export function toBotMessages(messages: CloudApiMessage[]): BotMessage[] {
  const result: BotMessage[] = [];
  for (const message of messages) {
    if (message.type === 'text' && 'text' in message) {
      result.push({ type: 'text', text: message.text.body });
    } else if (message.type === 'interactive' && 'interactive' in message) {
      const buttons = (message.interactive.action?.buttons ?? [])
        .map((button) => button.reply)
        .filter((reply): reply is ReplyButton => Boolean(reply?.id && reply.title));
      result.push({ type: 'buttons', text: message.interactive.body?.text ?? '', buttons });
    }
  }
  return result;
}
