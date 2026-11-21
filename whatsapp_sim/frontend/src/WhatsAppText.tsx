import { Fragment, type ReactNode } from 'react';

// Renders WhatsApp markup: *bold*, _italic_, ~strike~, ```mono```, `code`,
// "> " quotes and bare http(s) links. Text is never injected as HTML.
const INLINE =
  /```([^`]+?)```|`([^`\n]+)`|(https?:\/\/[^\s<>"]*[^\s<>".,:;!?)\]'”])|(?<![\p{L}\p{N}])([*_~])(?!\s)((?:(?!\4).)+?)(?<!\s)\4(?![\p{L}\p{N}])/gu;

const STYLE_TAGS = { '*': 'strong', _: 'em', '~': 's' } as const;

function renderInline(text: string, depth = 0): ReactNode[] {
  const nodes: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE)) {
    const index = match.index ?? 0;
    if (index > last) nodes.push(text.slice(last, index));
    const [whole, mono, code, url, marker, inner] = match;
    const key = `${depth}-${index}`;
    if (mono !== undefined) {
      nodes.push(
        <code key={key} className="wa-mono">
          {mono}
        </code>,
      );
    } else if (code !== undefined) {
      nodes.push(
        <code key={key} className="wa-code">
          {code}
        </code>,
      );
    } else if (url !== undefined) {
      nodes.push(
        <a key={key} href={url} target="_blank" rel="noopener noreferrer">
          {url}
        </a>,
      );
    } else if (marker !== undefined && inner !== undefined) {
      const Tag = STYLE_TAGS[marker as keyof typeof STYLE_TAGS];
      nodes.push(<Tag key={key}>{depth < 3 ? renderInline(inner, depth + 1) : inner}</Tag>);
    } else {
      nodes.push(whole);
    }
    last = index + whole.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export default function WhatsAppText({ text }: { text: string }) {
  return (
    <>
      {text.split('\n').map((line, i) => (
        <Fragment key={i}>
          {i > 0 && <br />}
          {line.startsWith('> ') ? (
            <span className="wa-quote">{renderInline(line.slice(2))}</span>
          ) : (
            renderInline(line)
          )}
        </Fragment>
      ))}
    </>
  );
}
