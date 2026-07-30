import { useEffect, useRef, useState } from 'react';
import { getChatStarters, sendChat } from '../lib/api.js';
import VoiceInput from './VoiceInput.jsx';

const FIELD_LABEL_KEYS = {
  age: 'age',
  gender: 'gender',
  annual_income: 'annualIncome',
  district: 'district',
  occupation: 'occupation',
  social_category: 'socialCategory',
};

export default function ChatPanel({ strings, language, capabilities, onMatch }) {
  const [messages, setMessages] = useState([]);
  const [starters, setStarters] = useState([]);
  const [draft, setDraft] = useState('');
  const [profile, setProfile] = useState({ language });
  const [missing, setMissing] = useState([]);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState('rules');
  const scrollRef = useRef(null);

  // Reload the greeting whenever the language flips, so the conversation
  // restarts in the language the user just chose.
  useEffect(() => {
    let cancelled = false;
    getChatStarters(language)
      .then((data) => {
        if (cancelled) return;
        setMessages([{ role: 'assistant', content: data.greeting }]);
        setStarters(data.suggestions || []);
        setProfile({ language });
        setMissing([]);
        setReady(false);
      })
      .catch(() => {
        if (!cancelled) setMessages([{ role: 'assistant', content: strings.errorBackend }]);
      });
    return () => { cancelled = true; };
  }, [language, strings.errorBackend]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, busy]);

  async function submit(text) {
    const message = (text ?? draft).trim();
    if (!message || busy) return;

    const history = messages.map(({ role, content }) => ({ role, content }));
    setMessages((prev) => [...prev, { role: 'user', content: message }]);
    setDraft('');
    setBusy(true);

    try {
      const response = await sendChat({
        message,
        history,
        profile: { ...profile, language },
        language,
      });
      setMessages((prev) => [...prev, { role: 'assistant', content: response.reply }]);
      setProfile(response.profile);
      setMissing(response.missing_fields || []);
      setReady(response.ready_to_match);
      setSource(response.source);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: err.status ? err.message : strings.errorBackend },
      ]);
    } finally {
      setBusy(false);
    }
  }

  const known = [
    profile.age && `${strings.age}: ${profile.age}`,
    profile.gender && `${strings.gender}: ${strings[`gender${profile.gender[0].toUpperCase()}${profile.gender.slice(1)}`] || profile.gender}`,
    profile.district && `${strings.district}: ${profile.district}`,
    profile.annual_income && `${strings.annualIncome}: ₹${Number(profile.annual_income).toLocaleString('en-IN')}`,
    profile.occupation && `${strings.occupation}: ${profile.occupation.replace(/_/g, ' ')}`,
    profile.social_category && `${strings.socialCategory}: ${profile.social_category}`,
  ].filter(Boolean);

  return (
    <div className="panel chat">
      <div className="panel-head panel-head--split">
        <div>
          <h2>{strings.chatTitle}</h2>
          <p className="chat-source">
            <span className={`dot ${source === 'ollama' ? 'dot--ai' : 'dot--rules'}`} />
            {source === 'ollama' ? strings.chatPoweredOllama : strings.chatPoweredRules}
          </p>
        </div>
      </div>

      <div className="chat-log" ref={scrollRef}>
        {messages.map((message, index) => (
          <div key={index} className={`bubble bubble--${message.role}`}>
            {message.content}
          </div>
        ))}
        {busy && (
          <div className="bubble bubble--assistant bubble--typing">
            <i /><i /><i />
          </div>
        )}
      </div>

      {starters.length > 0 && messages.length <= 1 && (
        <div className="starters">
          {starters.map((starter) => (
            <button key={starter} type="button" className="starter" onClick={() => submit(starter)}>
              {starter}
            </button>
          ))}
        </div>
      )}

      {known.length > 0 && (
        <div className="chat-profile">
          <span className="chat-profile-title">{strings.chatKnown}</span>
          <div className="chat-profile-chips">
            {known.map((item) => (
              <span key={item} className="tag tag--soft">{item}</span>
            ))}
          </div>
          {missing.length > 0 && (
            <p className="chat-missing">
              {strings.chatStillNeeds}:{' '}
              {missing.map((field) => strings[FIELD_LABEL_KEYS[field]] || field).join(', ')}
            </p>
          )}
        </div>
      )}

      <div className="chat-input">
        <textarea
          rows="2"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={strings.chatPlaceholder}
        />
        <div className="chat-input-actions">
          <VoiceInput
            strings={strings}
            available={capabilities.voice}
            onTranscript={(text) => setDraft((prev) => (prev ? `${prev} ${text}` : text))}
            compact
          />
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => submit()}
            disabled={busy || !draft.trim()}
          >
            {strings.chatSend}
          </button>
        </div>
      </div>

      {ready && (
        <button
          type="button"
          className="btn btn-accent btn-wide"
          onClick={() => onMatch({ ...profile, language })}
        >
          {strings.chatShowSchemes} →
        </button>
      )}
    </div>
  );
}
