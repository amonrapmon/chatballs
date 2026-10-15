import { useEffect, useState } from "react";
import { useEmailContinuation } from "./EmailContinuationContext";

/** Почтовый черновик сохраняется отдельно от ответа и внутреннего комментария. */
export function useEmailComposerDraft(conversationId: number | null) {
  const mail = useEmailContinuation();
  const [text, setText] = useState("");
  const [attachment, setAttachment] = useState<File | null>(null);
  const [recipient, setRecipient] = useState("");
  const [connectionId, setConnectionId] = useState(0);
  const [subject, setSubject] = useState("");
  const [waiting, setWaiting] = useState(false);
  const options = mail?.options;
  const chosenRecipient = options?.addresses.includes(recipient) ? recipient : options?.addresses[0] ?? "";
  // Исчезнувший выбранный ящик блокирует отправку, а не меняет её транспорт.
  const mailbox = connectionId
    ? options?.mailboxes.find((box) => box.id === connectionId)
    : options?.mailboxes[0];
  useEffect(() => {
    setText(""); setAttachment(null); setRecipient(""); setConnectionId(0); setSubject(""); setWaiting(false);
  }, [conversationId]);
  useEffect(() => {
    // Первый доступный ящик — тоже выбор: обновление списка не должно его менять.
    if (!connectionId && options?.mailboxes[0]) setConnectionId(options.mailboxes[0].id);
  }, [connectionId, options]);
  useEffect(() => {
    if (waiting && !mail?.busy) { setText(""); setAttachment(null); setWaiting(false); }
  }, [waiting, mail?.busy]);
  async function send() {
    if (!mail || mail.busy || !chosenRecipient || !mailbox) return false;
    const accepted = await mail.send({ recipient: chosenRecipient, connectionId: mailbox.id, subject, text: text.trim(), file: attachment });
    if (accepted) setWaiting(true);
    return accepted;
  }
  return { mail, options, text, setText, attachment, setAttachment, recipient: chosenRecipient, setRecipient,
    mailbox, setConnectionId, subject, setSubject, send, blocked: !chosenRecipient || !mailbox };
}
