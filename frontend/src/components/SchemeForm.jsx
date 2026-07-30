import { useState } from 'react';
import { TN_DISTRICTS } from '../i18n.js';
import { readDocument } from '../lib/api.js';
import VoiceInput from './VoiceInput.jsx';

const EXAMPLE = {
  name: 'Lakshmi',
  district: 'Madurai',
  age: '62',
  gender: 'female',
  marital_status: 'widowed',
  annual_income: '48000',
  family_size: '3',
  occupation: 'agricultural_labourer',
  social_category: 'MBC',
  disability_percent: '',
  flags: ['is_widow', 'is_rural', 'is_low_income'],
  issue_text:
    'My husband passed away two years ago. I need help with my heart treatment and I have no regular income. I live in a village near Madurai.',
};

export default function SchemeForm({
  strings,
  language,
  options,
  capabilities,
  onSubmit,
  loading,
}) {
  const [form, setForm] = useState({
    name: '', district: '', age: '', gender: '', marital_status: '',
    annual_income: '', family_size: '', occupation: '', social_category: '',
    disability_percent: '', flags: [], issue_text: '',
  });
  const [ocrState, setOcrState] = useState({ status: 'idle', filled: [], detected: '', error: '' });

  const set = (key, value) => setForm((prev) => ({ ...prev, [key]: value }));

  const toggleFlag = (flag) =>
    setForm((prev) => ({
      ...prev,
      flags: prev.flags.includes(flag)
        ? prev.flags.filter((f) => f !== flag)
        : [...prev.flags, flag],
    }));

  // Form inputs always hold strings; the API expects nullable integers. Every
  // submission path goes through here so an empty field becomes null rather
  // than an empty string the backend would reject.
  function toProfile(state) {
    const toInt = (value) => {
      const parsed = parseInt(value, 10);
      return Number.isNaN(parsed) ? null : parsed;
    };
    return {
      name: (state.name || '').trim(),
      district: state.district || '',
      age: toInt(state.age),
      gender: state.gender || null,
      marital_status: state.marital_status || null,
      annual_income: toInt(state.annual_income),
      family_size: toInt(state.family_size),
      occupation: state.occupation || null,
      social_category: state.social_category || null,
      disability_percent: toInt(state.disability_percent),
      flags: state.flags || [],
      issue_text: (state.issue_text || '').trim(),
      language,
    };
  }

  function handleSubmit(event) {
    event.preventDefault();
    onSubmit(toProfile(form));
  }

  async function handleDocument(event) {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;

    setOcrState({ status: 'reading', filled: [], detected: '', error: '' });
    try {
      const result = await readDocument(file);
      const filled = [];
      const next = {};
      result.fields.forEach(({ field, value }) => {
        // Never overwrite something the user already typed.
        if (field === 'name' && !form.name) { next.name = value; filled.push(strings.name); }
        if (field === 'age' && !form.age) { next.age = value; filled.push(strings.age); }
        if (field === 'annual_income' && !form.annual_income) {
          next.annual_income = value; filled.push(strings.annualIncome);
        }
        if (field === 'district' && !form.district) { next.district = value; filled.push(strings.district); }
        if (field === 'disability_percent' && !form.disability_percent) {
          next.disability_percent = value; filled.push(strings.disabilityPercent);
        }
      });
      setForm((prev) => ({ ...prev, ...next }));
      setOcrState({
        status: 'done',
        filled,
        detected: result.detected_document || '',
        error: filled.length ? '' : strings.uploadNothing,
      });
    } catch (err) {
      setOcrState({
        status: 'error',
        filled: [],
        detected: '',
        error: err.status === 503 ? strings.uploadUnavailable : err.message,
      });
    }
  }

  const appendTranscript = (text) =>
    set('issue_text', form.issue_text ? `${form.issue_text} ${text}` : text);

  return (
    <form className="panel form" onSubmit={handleSubmit}>
      <div className="panel-head">
        <h2>{strings.formTitle}</h2>
        <p>{strings.formSubtitle}</p>
      </div>

      {/* Document auto-fill */}
      <div className="ocr-box">
        <div className="ocr-copy">
          <strong>{strings.uploadTitle}</strong>
          <span>{strings.uploadBody}</span>
        </div>
        <label className={`btn btn-ghost ${!capabilities.ocr ? 'is-disabled' : ''}`}>
          {ocrState.status === 'reading' ? strings.uploadReading : strings.uploadButton}
          <input
            type="file"
            accept="image/png,image/jpeg,image/jpg,image/webp"
            onChange={handleDocument}
            disabled={!capabilities.ocr || ocrState.status === 'reading'}
            hidden
          />
        </label>
      </div>
      {!capabilities.ocr && <p className="inline-note">{strings.uploadUnavailable}</p>}
      {ocrState.filled.length > 0 && (
        <p className="inline-ok">
          ✓ {strings.uploadFound}: {ocrState.filled.join(', ')}
          {ocrState.detected && ocrState.detected !== 'unknown' && (
            <> · {strings.uploadDetected}: {ocrState.detected.replace(/_/g, ' ')}</>
          )}
        </p>
      )}
      {ocrState.error && <p className="inline-warn">{ocrState.error}</p>}

      <div className="grid-2">
        <label className="field">
          <span>{strings.name}</span>
          <input
            type="text"
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder={strings.namePlaceholder}
          />
        </label>
        <label className="field">
          <span>{strings.district}</span>
          <select value={form.district} onChange={(e) => set('district', e.target.value)}>
            <option value="">{strings.districtPlaceholder}</option>
            {TN_DISTRICTS.map((district) => (
              <option key={district} value={district}>{district}</option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid-3">
        <label className="field">
          <span>{strings.age}</span>
          <input
            type="number" min="1" max="120" value={form.age}
            onChange={(e) => set('age', e.target.value)} placeholder="—"
          />
        </label>
        <label className="field">
          <span>{strings.gender}</span>
          <select value={form.gender} onChange={(e) => set('gender', e.target.value)}>
            <option value="">{strings.selectPlaceholder}</option>
            <option value="female">{strings.genderFemale}</option>
            <option value="male">{strings.genderMale}</option>
            <option value="other">{strings.genderOther}</option>
          </select>
        </label>
        <label className="field">
          <span>{strings.maritalStatus}</span>
          <select
            value={form.marital_status}
            onChange={(e) => set('marital_status', e.target.value)}
          >
            <option value="">{strings.selectPlaceholder}</option>
            <option value="single">{strings.maritalSingle}</option>
            <option value="married">{strings.maritalMarried}</option>
            <option value="widowed">{strings.maritalWidowed}</option>
            <option value="separated">{strings.maritalSeparated}</option>
          </select>
        </label>
      </div>

      <div className="grid-3">
        <label className="field">
          <span>{strings.annualIncome}</span>
          <input
            type="number" min="0" value={form.annual_income}
            onChange={(e) => set('annual_income', e.target.value)} placeholder="—"
          />
          <small>{strings.incomeHint}</small>
        </label>
        <label className="field">
          <span>{strings.familySize}</span>
          <input
            type="number" min="1" max="25" value={form.family_size}
            onChange={(e) => set('family_size', e.target.value)} placeholder="—"
          />
        </label>
        <label className="field">
          <span>{strings.disabilityPercent}</span>
          <input
            type="number" min="0" max="100" value={form.disability_percent}
            onChange={(e) => set('disability_percent', e.target.value)} placeholder="—"
          />
        </label>
      </div>

      <div className="grid-2">
        <label className="field">
          <span>{strings.occupation}</span>
          <select value={form.occupation} onChange={(e) => set('occupation', e.target.value)}>
            <option value="">{strings.selectPlaceholder}</option>
            {options.occupations.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{strings.socialCategory}</span>
          <select
            value={form.social_category}
            onChange={(e) => set('social_category', e.target.value)}
          >
            <option value="">{strings.selectPlaceholder}</option>
            {options.social_categories.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </label>
      </div>

      <fieldset className="chips-field">
        <legend>
          {strings.situationTitle}
          <small>{strings.situationHint}</small>
        </legend>
        <div className="chips">
          {options.situation_flags.map((option) => (
            <label
              key={option.value}
              className={`chip ${form.flags.includes(option.value) ? 'is-on' : ''}`}
            >
              <input
                type="checkbox"
                checked={form.flags.includes(option.value)}
                onChange={() => toggleFlag(option.value)}
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>

      <label className="field">
        <span>{strings.issueTitle}</span>
        <textarea
          rows="4"
          value={form.issue_text}
          onChange={(e) => set('issue_text', e.target.value)}
          placeholder={strings.issuePlaceholder}
        />
        <small>{strings.issueHint}</small>
      </label>

      <VoiceInput
        strings={strings}
        available={capabilities.voice}
        onTranscript={appendTranscript}
      />

      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? strings.submitting : strings.submit}
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => { setForm(EXAMPLE); onSubmit(toProfile(EXAMPLE)); }}
        >
          {strings.tryExample}
        </button>
        <button
          type="button"
          className="btn btn-quiet"
          onClick={() =>
            setForm({
              name: '', district: '', age: '', gender: '', marital_status: '',
              annual_income: '', family_size: '', occupation: '', social_category: '',
              disability_percent: '', flags: [], issue_text: '',
            })
          }
        >
          {strings.reset}
        </button>
      </div>
    </form>
  );
}
