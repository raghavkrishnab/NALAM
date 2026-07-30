import { useCallback, useEffect, useState } from 'react';
import BrowsePanel from './components/BrowsePanel.jsx';
import ChatPanel from './components/ChatPanel.jsx';
import ResultsPanel from './components/ResultsPanel.jsx';
import SchemeForm from './components/SchemeForm.jsx';
import { fill, useStrings } from './i18n.js';
import { getHealth, getOptions, getSchemes, matchProfile } from './lib/api.js';

const EMPTY_OPTIONS = { occupations: [], social_categories: [], situation_flags: [] };

export default function App() {
  const [language, setLanguage] = useState('en');
  const [tab, setTab] = useState('form');
  const [health, setHealth] = useState(null);
  const [options, setOptions] = useState(EMPTY_OPTIONS);
  const [schemes, setSchemes] = useState([]);
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const strings = useStrings(language);

  // The <html lang> attribute drives font selection in styles.css.
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setError(strings.errorBackend));
  }, [strings.errorBackend]);

  // Options and the browse list are localised server-side, so refetch on toggle.
  useEffect(() => {
    getOptions(language).then(setOptions).catch(() => {});
    getSchemes(language).then((data) => setSchemes(data.schemes)).catch(() => {});
  }, [language]);

  const runMatch = useCallback(
    async (profile) => {
      setLoading(true);
      setError('');
      setTab('form');
      try {
        const data = await matchProfile({ ...profile, language });
        setResults(data);
        // Give the results a moment to render before scrolling to them.
        requestAnimationFrame(() =>
          document.getElementById('results-anchor')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        );
      } catch (err) {
        setError(err.status ? err.message : strings.errorBackend);
        setResults(null);
      } finally {
        setLoading(false);
      }
    },
    [language, strings.errorBackend]
  );

  // Re-run the match when the language flips so results switch language too.
  const [lastProfile, setLastProfile] = useState(null);
  const handleSubmit = (profile) => {
    setLastProfile(profile);
    runMatch(profile);
  };
  useEffect(() => {
    if (lastProfile) runMatch(lastProfile);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [language]);

  const capabilities = {
    voice: Boolean(health?.capabilities?.voice_transcription?.installed),
    ocr: Boolean(health?.capabilities?.document_ocr?.installed),
    llm: Boolean(health?.capabilities?.llm?.available),
  };
  const schemeCount = health?.schemes_loaded ?? 94;

  return (
    <div className="app">
      <header className="topbar">
        <div className="shell topbar-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">◈</span>
            <div>
              <strong>{strings.brand}</strong>
              <small>{strings.tagline}</small>
            </div>
          </div>
          <button
            type="button"
            className="lang-toggle"
            onClick={() => setLanguage(language === 'en' ? 'ta' : 'en')}
            aria-label={strings.langToggleAria}
          >
            <span aria-hidden="true">⇄</span> {strings.langToggle}
          </button>
        </div>
      </header>

      <section className="hero">
        <div className="shell hero-inner">
          <div className="hero-copy">
            <h1>{strings.heroTitle}</h1>
            <p>{fill(strings.heroBody, { count: schemeCount })}</p>
            <div className="hero-stats">
              <div><strong>{schemeCount}</strong><span>{strings.heroStat1}</span></div>
              <div><strong>{schemes.length ? '100%' : '—'}</strong><span>{strings.heroStat2}</span></div>
              <div><strong>2</strong><span>{strings.heroStat3}</span></div>
            </div>
          </div>
          <ol className="hero-steps">
            <li><span>1</span><div><strong>{strings.trust1Title}</strong><p>{strings.trust1Body}</p></div></li>
            <li><span>2</span><div><strong>{strings.trust2Title}</strong><p>{strings.trust2Body}</p></div></li>
            <li><span>3</span><div><strong>{strings.trust3Title}</strong><p>{strings.trust3Body}</p></div></li>
          </ol>
        </div>
      </section>

      <nav className="tabs">
        <div className="shell tabs-inner">
          {[
            ['form', strings.tabForm],
            ['chat', strings.tabChat],
            ['browse', strings.tabBrowse],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`tab ${tab === key ? 'is-active' : ''}`}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
        </div>
      </nav>

      <main className="shell main">
        {error && !health && <div className="banner banner--error">{error}</div>}

        {tab === 'form' && (
          <div className="layout">
            <SchemeForm
              strings={strings}
              language={language}
              options={options}
              capabilities={capabilities}
              onSubmit={handleSubmit}
              loading={loading}
            />
            <div id="results-anchor">
              <ResultsPanel
                results={results}
                strings={strings}
                loading={loading}
                error={error && !results ? error : ''}
              />
            </div>
          </div>
        )}

        {tab === 'chat' && (
          <div className="layout">
            <ChatPanel
              strings={strings}
              language={language}
              capabilities={capabilities}
              onMatch={handleSubmit}
            />
            <div id="results-anchor">
              <ResultsPanel results={results} strings={strings} loading={loading} error="" />
            </div>
          </div>
        )}

        {tab === 'browse' && <BrowsePanel schemes={schemes} strings={strings} />}
      </main>

      <footer className="footer">
        <div className="shell footer-inner">
          <div className="status">
            <strong>{strings.systemStatus}</strong>
            <ul>
              <li className="ok">
                <i />{strings.statusRules}: <span>{strings.statusOn}</span>
              </li>
              <li className={capabilities.voice ? 'ok' : 'off'}>
                <i />{strings.statusVoice}: <span>{capabilities.voice ? strings.statusOn : strings.statusOff}</span>
              </li>
              <li className={capabilities.ocr ? 'ok' : 'off'}>
                <i />{strings.statusOcr}: <span>{capabilities.ocr ? strings.statusOn : strings.statusOff}</span>
              </li>
              <li className={capabilities.llm ? 'ok' : 'off'}>
                <i />{strings.statusLlm}: <span>{capabilities.llm ? strings.statusOn : strings.statusOff}</span>
              </li>
            </ul>
            {(!capabilities.voice || !capabilities.ocr) && (
              <code className="status-hint">{strings.statusInstallHint}</code>
            )}
          </div>
          <p className="footer-note">{strings.disclaimerBody}</p>
        </div>
      </footer>
    </div>
  );
}
