import { useCallback, useEffect, useState } from 'react';

/** Czytanie tekstu na głos przez syntezator mowy przeglądarki. */
export function useSpeech(onUnsupported: () => void) {
  const [speaking, setSpeaking] = useState(false);

  const stop = useCallback(() => {
    if (typeof window !== 'undefined' && window.speechSynthesis) window.speechSynthesis.cancel();
    setSpeaking(false);
  }, []);

  const toggle = useCallback(
    (text: string) => {
      const synth = typeof window !== 'undefined' ? window.speechSynthesis : undefined;
      if (!synth) {
        onUnsupported();
        return;
      }
      if (speaking) {
        stop();
        return;
      }
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = 'pl-PL';
      utterance.rate = 0.95;
      utterance.onend = () => setSpeaking(false);
      utterance.onerror = () => setSpeaking(false);
      synth.cancel();
      synth.speak(utterance);
      setSpeaking(true);
    },
    [speaking, stop, onUnsupported],
  );

  useEffect(() => stop, [stop]);

  return { speaking, toggle, stop };
}
