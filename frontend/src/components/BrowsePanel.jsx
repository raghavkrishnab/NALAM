import { useMemo, useState } from 'react';
import { fill } from '../i18n.js';

export default function BrowsePanel({ schemes, strings }) {
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');

  const categories = useMemo(() => {
    const found = new Set();
    schemes.forEach((scheme) => scheme.categories.forEach((c) => found.add(c)));
    return [...found].sort();
  }, [schemes]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return schemes.filter((scheme) => {
      if (category && !scheme.categories.includes(category)) return false;
      if (!needle) return true;
      return (
        scheme.name.toLowerCase().includes(needle) ||
        scheme.summary.toLowerCase().includes(needle) ||
        scheme.department.toLowerCase().includes(needle)
      );
    });
  }, [schemes, query, category]);

  return (
    <div className="panel browse">
      <div className="panel-head">
        <h2>{strings.browseTitle}</h2>
        <p>{fill(strings.browseCount, { count: visible.length })}</p>
      </div>

      <div className="browse-controls">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={strings.browseSearch}
        />
        <select value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="">{strings.browseAll}</option>
          {categories.map((item) => (
            <option key={item} value={item}>
              {strings.categories[item] || item}
            </option>
          ))}
        </select>
      </div>

      <div className="browse-list">
        {visible.map((scheme) => (
          <article key={scheme.id} className="browse-item">
            <div className="browse-item-head">
              <h4>{scheme.name}</h4>
              <span className={`tag tag--${scheme.level}`}>
                {scheme.level === 'state' ? strings.levelState : strings.levelCentral}
              </span>
            </div>
            <p>{scheme.summary}</p>
            <div className="browse-item-foot">
              <span className="browse-benefit">{scheme.benefit}</span>
              {scheme.apply_url && (
                <a href={scheme.apply_url} target="_blank" rel="noopener noreferrer">
                  {strings.applyOnline} ↗
                </a>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
