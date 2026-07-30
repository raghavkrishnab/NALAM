import { useRef, useState } from 'react';
import { transcribeAudio } from '../lib/api.js';

/**
 * Records from the microphone and sends the audio to Whisper on the backend.
 *
 * Language is deliberately sent as "auto" rather than the UI language: Tamil
 * Nadu speech is very often code-mixed ("enakku hospital la treatment venum"),
 * and forcing a language makes Whisper noticeably worse on those sentences.
 */
export default function VoiceInput({ onTranscript, strings, available, compact = false }) {
  const [state, setState] = useState('idle'); // idle | recording | transcribing
  const [error, setError] = useState('');
  const [detected, setDetected] = useState('');
  const recorderRef = useRef(null);
  const chunksRef = useRef([]);
  const streamRef = useRef(null);

  const stopTracks = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  };

  async function start() {
    setError('');
    setDetected('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const recorder = new MediaRecorder(stream);
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        stopTracks();
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        if (blob.size < 1200) {
          setState('idle');
          return;
        }
        setState('transcribing');
        try {
          const result = await transcribeAudio(blob, 'auto');
          if (result.text?.trim()) {
            onTranscript(result.text.trim());
            setDetected(result.detected_language || '');
          }
        } catch (err) {
          setError(err.status === 503 ? strings.voiceUnavailable : strings.voiceError);
        } finally {
          setState('idle');
        }
      };

      recorder.start();
      recorderRef.current = recorder;
      setState('recording');
    } catch {
      setError(strings.voiceError);
      stopTracks();
      setState('idle');
    }
  }

  function stop() {
    recorderRef.current?.stop();
    recorderRef.current = null;
  }

  const busy = state === 'transcribing';
  const recording = state === 'recording';

  const label = busy
    ? strings.voiceTranscribing
    : recording
    ? strings.voiceStop
    : strings.voiceStart;

  return (
    <div className={`voice ${compact ? 'voice--compact' : ''}`}>
      <button
        type="button"
        className={`voice-btn ${recording ? 'is-recording' : ''}`}
        onClick={recording ? stop : start}
        disabled={busy || !available}
        title={available ? label : strings.voiceUnavailable}
        aria-label={label}
      >
        <span className="voice-icon" aria-hidden="true">
          {busy ? '⏳' : recording ? '⏹' : '🎙'}
        </span>
        {!compact && <span>{label}</span>}
      </button>

      {recording && (
        <span className="voice-pulse" aria-live="polite">
          <i /><i /><i />
          {strings.voiceRecording}
        </span>
      )}
      {detected && !recording && !busy && (
        <span className="voice-detected">
          {strings.voiceDetected}: <strong>{detected}</strong>
        </span>
      )}
      {error && <span className="voice-error">{error}</span>}
      {!available && !error && (
        <span className="voice-hint">{strings.voiceUnavailable}</span>
      )}
    </div>
  );
}
