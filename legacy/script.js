const form = document.getElementById('scheme-form');
const resultsEl = document.getElementById('results');
const documentUpload = document.getElementById('document-upload');
const documentListEl = document.getElementById('document-list');
const demoBtn = document.getElementById('demo-btn');

const uploadedDocs = [];

const schemes = [
  {
    id: 'cmchis',
    title: 'Chief Minister’s Comprehensive Health Insurance Scheme',
    summary: 'Covers hospital and treatment costs for low-income families in Tamil Nadu.',
    fit: 'Best for health emergencies, surgeries, and chronic treatment needs.',
    requiredDocs: ['Aadhaar card', 'income certificate', 'medical report', 'ration card'],
    tags: ['Health', 'Insurance', 'Hospital care'],
    keywords: ['health', 'medical', 'hospital', 'surgery', 'medicine', 'doctor', 'treatment', 'disease'],
    weight: 96,
  },
  {
    id: 'pmkisan',
    title: 'PM-KISAN Farmer Support',
    summary: 'Helps small and marginal farmers with direct financial support.',
    fit: 'Ideal for agriculture-related issues, crop loss, seed purchase, or income support.',
    requiredDocs: ['Aadhaar card', 'land records', 'bank passbook', 'ration card'],
    tags: ['Farmer', 'Agriculture', 'Income support'],
    keywords: ['farmer', 'agriculture', 'crop', 'land', 'seed', 'irrigation', 'farming'],
    weight: 94,
  },
  {
    id: 'mgnrega',
    title: 'MGNREGA Rural Employment Guarantee',
    summary: 'Provides work and wages for rural households facing unemployment or no regular income.',
    fit: 'Useful when someone needs livelihood support, job cards, or daily wage work.',
    requiredDocs: ['Aadhaar card', 'job card', 'ration card'],
    tags: ['Livelihood', 'Rural work', 'Employment'],
    keywords: ['job', 'unemployed', 'work', 'wage', 'livelihood', 'daily wage', 'employment', 'income'],
    weight: 92,
  },
  {
    id: 'pm-awas',
    title: 'PM Awas Yojana',
    summary: 'Supports housing for low-income households and homeless families.',
    fit: 'Best for people who need shelter, housing repair, or a new home.',
    requiredDocs: ['Aadhaar card', 'income certificate', 'ration card', 'address proof'],
    tags: ['Housing', 'Shelter', 'Home'],
    keywords: ['house', 'home', 'shelter', 'roof', 'housing', 'homeless'],
    weight: 90,
  },
  {
    id: 'scholarship',
    title: 'State Scholarship Support',
    summary: 'Offers educational support for students from low-income households.',
    fit: 'Suitable for school, college, tuition fees, or study expenses.',
    requiredDocs: ['Aadhaar card', 'income certificate', 'student ID', 'bonafide certificate'],
    tags: ['Education', 'Student support', 'Fees'],
    keywords: ['student', 'school', 'college', 'fee', 'education', 'scholarship', 'tuition'],
    weight: 88,
  },
  {
    id: 'old-age',
    title: 'Old Age / Pension Support',
    summary: 'Provides pension support for senior citizens who need monthly assistance.',
    fit: 'Best when the applicant is elderly and lacks regular family support.',
    requiredDocs: ['Aadhaar card', 'age proof', 'ration card', 'bank passbook'],
    tags: ['Senior citizen', 'Pension', 'Support'],
    keywords: ['elderly', 'senior', 'old age', 'pension', 'retired', 'age'],
    weight: 86,
  },
  {
    id: 'widow',
    title: 'Widow / Dependent Support Scheme',
    summary: 'Supports widows and dependents with financial aid and pension benefits.',
    fit: 'Useful in cases of loss of earning member or dependence on family support.',
    requiredDocs: ['Aadhaar card', 'death certificate', 'ration card', 'income certificate'],
    tags: ['Widow', 'Family support', 'Pension'],
    keywords: ['widow', 'death', 'dependent', 'family support', 'single mother'],
    weight: 84,
  },
  {
    id: 'svanidhi',
    title: 'PM SVANidhi Street Vendor Support',
    summary: 'Offers small business loans and support for street vendors and self-employed workers.',
    fit: 'Great for women, vendors, and those in small trading or daily business work.',
    requiredDocs: ['Aadhaar card', 'vendor certificate', 'shop proof', 'bank passbook'],
    tags: ['Business', 'Vendor', 'Loan'],
    keywords: ['vendor', 'shop', 'business', 'trade', 'self-employed', 'woman entrepreneur'],
    weight: 82,
  },
];

function renderDocumentList() {
  documentListEl.innerHTML = '';
  uploadedDocs.forEach((doc) => {
    const li = document.createElement('li');
    li.textContent = doc;
    documentListEl.appendChild(li);
  });
}

documentUpload.addEventListener('change', (event) => {
  const files = Array.from(event.target.files || []);
  files.forEach((file) => {
    if (!uploadedDocs.includes(file.name)) {
      uploadedDocs.push(file.name);
    }
  });
  renderDocumentList();
});

form.addEventListener('submit', (event) => {
  event.preventDefault();
  analyzeCase();
});

demoBtn.addEventListener('click', () => {
  document.getElementById('name').value = 'Ravi';
  document.getElementById('location').value = 'Madurai';
  document.getElementById('category').value = 'health';
  document.getElementById('age').value = '58';
  document.getElementById('income').value = '18000';
  document.getElementById('family').value = '4';
  document.getElementById('issue').value = 'My father needs a heart surgery and we cannot afford the hospital bill.';
  uploadedDocs.length = 0;
  uploadedDocs.push('medical-report.pdf', 'income-certificate.pdf', 'aadhaar.pdf');
  renderDocumentList();
  analyzeCase();
});

function analyzeCase() {
  const name = document.getElementById('name').value.trim();
  const location = document.getElementById('location').value.trim();
  const category = document.getElementById('category').value;
  const age = Number(document.getElementById('age').value);
  const income = Number(document.getElementById('income').value || 0);
  const family = Number(document.getElementById('family').value || 1);
  const issue = document.getElementById('issue').value.toLowerCase();

  const scored = schemes
    .map((scheme) => {
      let score = scheme.weight;
      const text = `${category} ${issue}`.toLowerCase();
      const matches = scheme.keywords.filter((keyword) => text.includes(keyword));
      score += matches.length * 4;

      if (scheme.id === 'old-age' && age >= 60) {
        score += 8;
      }
      if (scheme.id === 'widow' && /widow|death|single mother|dependent/.test(issue)) {
        score += 8;
      }
      if (scheme.id === 'pm-awas' && /house|home|shelter|roof|homeless/.test(issue)) {
        score += 8;
      }
      if ((scheme.id === 'mgnrega' || scheme.id === 'svanidhi') && income < 25000) {
        score += 4;
      }
      if (income < 20000) {
        score += 3;
      }
      if (family > 4) {
        score += 2;
      }

      const docMatches = uploadedDocs.filter((name) =>
        scheme.requiredDocs.some((doc) => name.toLowerCase().includes(doc.toLowerCase().split(' ')[0]))
      );
      const docBoost = docMatches.length * 2;
      score += docBoost;

      return {
        ...scheme,
        score: Math.min(score, 99),
        docMatches,
      };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, 3);

  const top = scored[0];

  resultsEl.innerHTML = `
    <div class="result-card">
      <h3>${name || 'Guest'} — NALAM sees a strong fit</h3>
      <p><strong>Location:</strong> ${location || 'Tamil Nadu'}</p>
      <p>${top.summary}</p>
      <div class="badge">Confidence ${top.score}%</div>
      <div class="tag-list">
        <span>${top.fit}</span>
        <span>${top.tags[0]}</span>
        <span>${top.tags[1]}</span>
      </div>
    </div>
    ${scored
      .map(
        (scheme) => `
          <div class="result-card">
            <h3>${scheme.title}</h3>
            <p>${scheme.summary}</p>
            <p><strong>Why it matches:</strong> ${scheme.fit}</p>
            <p><strong>Uploaded documents matched:</strong> ${scheme.docMatches.length > 0 ? scheme.docMatches.join(', ') : 'No direct matches yet'}</p>
            <p><strong>Required docs:</strong> ${scheme.requiredDocs.join(' • ')}</p>
            <div class="badge">Match score ${scheme.score}%</div>
          </div>
        `
      )
      .join('')}
  `;
}

resultsEl.innerHTML = `
  <div class="empty-state">
    <strong>Welcome to NALAM.</strong><br />
    Complete the form, upload your documents, and the AI will suggest the most relevant government schemes for your case.
  </div>
`;
