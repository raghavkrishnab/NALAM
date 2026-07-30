import { useState } from 'react';

const CHECK_ICON = { pass: '✓', fail: '✕', unknown: '?' };

function SchemeCard({ scheme, strings, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <article className={`scheme scheme--${scheme.status}`}>
      <header className="scheme-head">
        <div className="scheme-title">
          <h4>{scheme.name}</h4>
          <div className="scheme-meta">
            <span className={`tag tag--${scheme.level}`}>
              {scheme.level === 'state' ? strings.levelState : strings.levelCentral}
            </span>
            {scheme.categories.slice(0, 2).map((category) => (
              <span key={category} className="tag tag--soft">
                {strings.categories[category] || category}
              </span>
            ))}
          </div>
        </div>
        <div className="scheme-score" title={strings.matchScore}>
          <strong>{scheme.score}</strong>
          <small>{strings.matchScore}</small>
        </div>
      </header>

      <p className="scheme-summary">{scheme.summary}</p>

      <div className="scheme-benefit">
        <span className="label">{strings.benefitLabel}</span>
        <strong>{scheme.benefit}</strong>
      </div>

      <div className="check-bar" aria-hidden="true">
        {scheme.passed_count > 0 && (
          <span className="check-bar-seg seg-pass" style={{ flex: scheme.passed_count }} />
        )}
        {scheme.unknown_count > 0 && (
          <span className="check-bar-seg seg-unknown" style={{ flex: scheme.unknown_count }} />
        )}
        {scheme.failed_count > 0 && (
          <span className="check-bar-seg seg-fail" style={{ flex: scheme.failed_count }} />
        )}
      </div>
      <div className="check-counts">
        <span className="c-pass">{scheme.passed_count} {strings.checkPass}</span>
        {scheme.unknown_count > 0 && (
          <span className="c-unknown">{scheme.unknown_count} {strings.checkUnknown}</span>
        )}
        {scheme.failed_count > 0 && (
          <span className="c-fail">{scheme.failed_count} {strings.checkFail}</span>
        )}
      </div>

      <button type="button" className="disclose" onClick={() => setOpen(!open)}>
        {open ? strings.hideWhy : strings.showWhy}
        <span className={`caret ${open ? 'is-open' : ''}`} aria-hidden="true">▾</span>
      </button>

      {open && (
        <div className="scheme-detail">
          <h5>{strings.whyMatch}</h5>
          <ul className="checks">
            {scheme.checks.map((check, index) => (
              <li key={index} className={`check check--${check.status}`}>
                <span className="check-icon" aria-hidden="true">{CHECK_ICON[check.status]}</span>
                <div>
                  <strong>{check.label}</strong>
                  <span>{check.detail}</span>
                </div>
              </li>
            ))}
          </ul>

          {scheme.documents.length > 0 && (
            <>
              <h5>{strings.documentsNeeded}</h5>
              <ul className="docs">
                {scheme.documents.map((doc, index) => (
                  <li key={index}>{doc}</li>
                ))}
              </ul>
            </>
          )}

          <h5>{strings.whereToApply}</h5>
          <p className="apply-office">{scheme.apply_office}</p>
          <p className="scheme-dept">
            <span className="label">{strings.departmentLabel}:</span> {scheme.department}
          </p>
          {scheme.apply_url && (
            <a
              className="btn btn-link"
              href={scheme.apply_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              {strings.applyOnline} ↗
            </a>
          )}
        </div>
      )}
    </article>
  );
}

function Group({ id, heading, sub, schemes, strings, tone, defaultOpenFirst }) {
  if (!schemes.length) return null;
  return (
    <section className={`group group--${tone}`} id={id}>
      <header className="group-head">
        <h3>
          {heading}
          <span className="group-count">{schemes.length}</span>
        </h3>
        <p>{sub}</p>
      </header>
      <div className="group-body">
        {schemes.map((scheme, index) => (
          <SchemeCard
            key={scheme.id}
            scheme={scheme}
            strings={strings}
            defaultOpen={defaultOpenFirst && index === 0}
          />
        ))}
      </div>
    </section>
  );
}

export default function ResultsPanel({ results, strings, loading, error }) {
  if (error) {
    return (
      <div className="panel results">
        <div className="empty empty--error">
          <strong>{error}</strong>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="panel results">
        <div className="empty">
          <div className="spinner" aria-hidden="true" />
          <strong>{strings.submitting}</strong>
        </div>
      </div>
    );
  }

  if (!results) {
    return (
      <div className="panel results">
        <div className="panel-head">
          <h2>{strings.resultsTitle}</h2>
        </div>
        <div className="empty">
          <div className="empty-mark" aria-hidden="true">◎</div>
          <strong>{strings.resultsEmpty}</strong>
          <span>{strings.resultsEmptyHint}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="panel results">
      <div className="panel-head panel-head--split">
        <div>
          <h2>{strings.resultsTitle}</h2>
          <p className="summary-text">{results.summary_text}</p>
        </div>
        <button type="button" className="btn btn-ghost" onClick={() => window.print()}>
          ⭳ {strings.downloadPdf}
        </button>
      </div>
      <p className="print-hint">{strings.printHint}</p>

      <Group
        id="eligible"
        tone="pass"
        heading={strings.eligibleHeading}
        sub={strings.eligibleSub}
        schemes={results.eligible}
        strings={strings}
        defaultOpenFirst
      />
      <Group
        id="likely"
        tone="unknown"
        heading={strings.likelyHeading}
        sub={strings.likelySub}
        schemes={results.likely}
        strings={strings}
      />
      <Group
        id="rejected"
        tone="fail"
        heading={strings.notEligibleHeading}
        sub={strings.notEligibleSub}
        schemes={results.not_eligible}
        strings={strings}
      />

      <aside className="disclaimer">
        <strong>{strings.disclaimerTitle}</strong>
        <p>{strings.disclaimerBody}</p>
      </aside>
    </div>
  );
}
